"""Partial extraction, targeted questions and trusted profile lookup boundaries."""
from datetime import timedelta
import pytest
from pydantic import ValidationError
from ..agents.factory import OllamaExtractor
from ..agents.workflow import WorkflowApp
from ..schemas.models import ActorContext, Case, Consent, Extraction, LoanRequest, MessageInput, ModuleResult, Scope, utcnow
from ..schemas.resolution import BusinessProfileResult
from ..services.extraction_validation import validate_extraction
from ..services.data_resolution import build_resolution

TEXT = 'Я ООО, нужно 3000000 рублей на товар на 24 месяца.'


def raw(**values):
    return {'intent':'PROVIDE_DETAILS', 'patch':values, 'clear_fields':[],
            'evidence':{field:TEXT for field in values}, 'ambiguous_subjects':[], 'multiple_purposes':[]}


class Chain:
    def __init__(self,response): self.response=response
    def invoke(self,messages): return self.response


def extractor(response):
    result=object.__new__(OllamaExtractor)
    result.chain=Chain(response)
    return result


def test_invalid_field_does_not_discard_valid_siblings():
    response=raw(legal_form='OOO',amount_rub=-10,purpose='INVENTORY',term_months=24)
    result=extractor(response).extract(MessageInput(session_id='s',message_id='m',text=TEXT),Case(owner_id='a'))
    assert result.patch.amount_rub is None
    assert result.patch.purpose == 'INVENTORY' and result.patch.term_months == 24
    assert [(issue.field,issue.code) for issue in result.diagnostics] == [('amount_rub','INVALID_VALUE')]


@pytest.mark.parametrize('value', [True,'3000000',1.5,0,-1])
def test_amount_requires_positive_integer(value):
    result=validate_extraction(raw(amount_rub=value),TEXT,Case(owner_id='a'))
    assert result.patch.amount_rub is None
    assert result.diagnostics[0].code == 'INVALID_VALUE'


def test_bad_quote_and_invented_recurrence_stay_unknown():
    response=raw(amount_rub=3000000,recurring=False)
    response['evidence']['amount_rub']='Иной текст'
    result=validate_extraction(response,TEXT,Case(owner_id='a'))
    assert result.patch.amount_rub is None and result.patch.recurring is None
    assert {issue.code for issue in result.diagnostics} == {'UNGROUNDED_QUOTE','UNSUPPORTED_ASSERTION'}


def actor(consent=False):
    now=utcnow()
    return ActorContext(actor_id='a',company_id=40,active_borrower_id='test-company',allowed_borrower_ids=['test-company'],
        consents=[Consent(consent_id='test',borrower_id='test-company',scope=Scope.EVIDENCE_COLLECTION,
                          granted_at=now-timedelta(minutes=1),expires_at=now+timedelta(hours=1))] if consent else [])


class ProfileAdapter:
    def __init__(self, *, empty=False, fail=False, foreign=False):
        self.calls=0;self.empty=empty;self.fail=fail;self.foreign=foreign
    def supports(self,operation): return operation == 'lookup_business_profile'
    def call(self,operation,envelope,key):
        self.calls+=1
        if self.fail: raise ConnectionError('private connection details')
        at=envelope['decision_at']
        fact={'field':'legal_form','value':'OOO','borrower_id':envelope['borrower_id'],'company_id':40,
              'confirmed':True,'scope':'PRODUCT_MATCHING','source_ref':'postgres:test',
              'verified_at':at,'available_at':at,'snapshot_as_of':at,'validity':'AS_OF_SNAPSHOT'}
        return ModuleResult(ok=True,code='PROFILE_LOOKUP_COMPLETE',case_id=envelope['case_id'],revision=envelope['revision'],
            borrower_id=envelope['borrower_id'],result_ref='test-profile',data={'profile':{'company_id':41 if self.foreign else 40,
            'borrower_id':envelope['borrower_id'],'decision_at':at,'verified_facts':[] if self.empty else [fact]}})


def msg(mid='m',text=TEXT): return MessageInput(session_id='s',message_id=mid,text=text)


def test_partial_extraction_questions_survive_status_and_accept_correction(tmp_path):
    with WorkflowApp(tmp_path/'case.db',extractor=extractor(raw(legal_form='OOO',purpose='INVENTORY',amount_rub=-1,term_months=24))) as app:
        first=app.handle(msg(),actor())
        assert first.request.purpose == 'INVENTORY'
        assert first.next_action == 'ASK_FIELDS'
        assert 'сумма' in first.message and 'срок' not in first.message
        app.workflow.extractor=type('StatusExtractor',(),{'extract':lambda self,message,case:Extraction(intent='STATUS')})()
        status=app.handle(msg('status','Что дальше?'),actor())
        assert status.data_resolution.gaps[0].field == 'amount_rub'
        app.workflow.extractor=extractor(raw(amount_rub=3000000))
        corrected=app.handle(msg('correct'),actor())
        assert corrected.request.amount_rub == 3000000
        assert not any(gap.field=='amount_rub' for gap in corrected.data_resolution.gaps)


def test_profile_fills_only_verified_missing_form(tmp_path):
    adapter=ProfileAdapter()
    with WorkflowApp(tmp_path/'case.db',extractor=extractor(raw(amount_rub=3000000)),adapter=adapter) as app:
        result=app.handle(msg(),actor(consent=True))
        assert result.request.legal_form == 'OOO'
        assert result.request.amount_rub == 3000000 and result.request.term_months is None
        assert result.data_resolution.database_lookup == 'FOUND'
        assert all(gap.field!='legal_form' for gap in result.data_resolution.gaps)
        assert adapter.calls == 1
        assert app.handle(msg(),actor(consent=True)) == result
        assert adapter.calls == 1


@pytest.mark.parametrize('kwargs,expected', [({'empty':True},'NOT_FOUND'),({'fail':True},'UNAVAILABLE'),({'foreign':True},'UNAVAILABLE')])
def test_profile_failure_or_unverified_data_asks_user(tmp_path,kwargs,expected):
    with WorkflowApp(tmp_path/'case.db',extractor=extractor(raw()),adapter=ProfileAdapter(**kwargs)) as app:
        result=app.handle(msg(),actor(consent=True))
        assert result.request.legal_form is None
        assert result.data_resolution.database_lookup == expected
        assert 'форма бизнеса' in result.message
        assert 'private' not in result.model_dump_json()


def test_profile_never_reads_without_consent(tmp_path):
    adapter=ProfileAdapter()
    with WorkflowApp(tmp_path/'case.db',extractor=extractor(raw()),adapter=adapter) as app:
        result=app.handle(msg(),actor())
        assert adapter.calls == 0
        assert result.data_resolution.database_lookup == 'CONSENT_REQUIRED'
        assert result.next_action == 'ASK_FIELDS'


def test_ml_mapping_gap_is_not_a_customer_question():
    case=Case(owner_id='a',data_context={'data_quality':{'blocking_issues':['ML_MAPPING_AND_FORMULAS_NOT_APPROVED']}})
    gap=build_resolution(case).gaps[-1]
    assert gap.resolution == 'ENGINEERING' and gap.question is None


def test_partial_survives_failed_repair_transport():
    response=raw(amount_rub=-1,term_months=24)
    class FailedRepair:
        calls=0
        def invoke(self,messages):
            self.calls+=1
            if self.calls==2: raise ConnectionError('provider unavailable')
            return response
    parser=object.__new__(OllamaExtractor);parser.chain=FailedRepair()
    result=parser.extract(msg(),Case(owner_id='a'))
    assert result.patch.term_months==24 and result.patch.amount_rub is None


def test_future_profile_fact_rejected_by_pydantic():
    now=utcnow()
    with pytest.raises(ValidationError):
        BusinessProfileResult.model_validate({'company_id':40,'borrower_id':'b','decision_at':now,
            'verified_facts':[{'field':'legal_form','value':'OOO','company_id':40,'borrower_id':'b','confirmed':True,
            'scope':'PRODUCT_MATCHING','source_ref':'test','verified_at':now+timedelta(days=1),
            'available_at':now,'snapshot_as_of':now,'validity':'AS_OF_SNAPSHOT'}]})


def test_digits_with_units_must_agree_with_extracted_values():
    result=validate_extraction(raw(amount_rub=5000000,term_months=12,legal_form='OOO'),TEXT,Case(owner_id='a'))
    assert result.patch.amount_rub is None and result.patch.term_months is None
    assert result.patch.legal_form == 'OOO'
    assert {issue.field for issue in result.diagnostics} == {'amount_rub','term_months'}


def test_generic_inventory_does_not_imply_one_time_need():
    result=validate_extraction(raw(financing_need='ONE_TIME_PURCHASE'),TEXT,Case(owner_id='a'))
    assert result.patch.financing_need is None


def test_repair_keeps_previously_valid_siblings():
    from ..services.extraction_validation import merge_repair
    before=validate_extraction(raw(legal_form='OOO',amount_rub=-1),TEXT,Case(owner_id='a'))
    after=validate_extraction(raw(amount_rub=3000000),TEXT,Case(owner_id='a'))
    merged=merge_repair(before,after)
    assert merged.patch.legal_form=='OOO' and merged.patch.amount_rub==3000000
    assert not merged.diagnostics


def test_invalid_explicit_change_cannot_disappear_as_model_null():
    text='Измени сумму на -100 рублей.'
    result=validate_extraction(raw(),text,Case(owner_id='a',request=LoanRequest(amount_rub=3000000)))
    assert result.patch.amount_rub is None
    assert result.diagnostics[0].field == 'amount_rub'
    assert result.diagnostics[0].code == 'INVALID_VALUE'


def test_invalid_update_preserves_old_value_even_when_provider_fails(tmp_path):
    with WorkflowApp(tmp_path/'case.db',extractor=extractor(raw(legal_form='OOO',purpose='INVENTORY',amount_rub=3000000,term_months=24))) as app:
        original=app.handle(msg(),actor())
        app.workflow.extractor=type('Unavailable',(),{'extract':lambda *args:(_ for _ in ()).throw(ConnectionError('provider failure'))})()
        result=app.handle(msg('invalid','Измени сумму на -100 рублей.'),actor())
        assert result.request.amount_rub==3000000
        assert result.revision==original.revision
        assert result.next_action=='ASK_FIELDS' and result.status=='NEEDS_INPUT'
        assert result.data_resolution.gaps[0].field=='amount_rub'
        assert 'положительное целое' in result.message


def test_invalid_quote_type_does_not_discard_valid_field():
    response=raw(legal_form='OOO',amount_rub=3000000)
    response['evidence']['amount_rub']=123
    result=validate_extraction(response,TEXT,Case(owner_id='a'))
    assert result.patch.legal_form=='OOO' and result.patch.amount_rub is None
