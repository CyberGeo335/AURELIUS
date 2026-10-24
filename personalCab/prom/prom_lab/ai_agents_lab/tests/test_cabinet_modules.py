"""Regression and service contract tests. No real lender or Ollama required."""
import base64
from datetime import timedelta
from pathlib import Path

import pytest

from ..agents.factory import OllamaExtractor
from ..agents.workflow import WorkflowApp
from ..schemas.models import Case,Extraction,LoanRequest,MessageInput,utcnow
from ..schemas.resolution import FieldProblem
from ..services.assessment import AssessmentService,FeatureInput,annuity_schedule
from ..services.data_preparation import build_evidence,DataPreparationService
from ..services.database_modules import DatabaseModules
from ..services.documents import parse_document
from ..services.extraction_validation import merge_repair,validate_extraction
from ..services.product_matching import ProductMatcher,database_rule_check
from ..services.questionnaire import build_questionnaire,validate_answer
from .test_data_resolution import actor


def raw(values,text):
    return {'intent':'PROVIDE_DETAILS','patch':values,'clear_fields':[],
            'evidence':{key:text for key in values},'ambiguous_subjects':[],'multiple_purposes':[]}


def feature_bundle(kind='baseline'):
    features=dict(age_months=60,industry='retail',entity_type='OOO',monthly_revenue=1200000,
                  revenue_trend_12m=0.03,revenue_volatility=0.15,operating_margin=0.2,cash_buffer_months=2,
                  dscr=1.5,debt_to_revenue=0.4,prior_overdue_30d=0,requested_amount=3000000,
                  term_months=24,annual_rate=0.24,macro_stress=0.2,month_on_book=1)
    if kind=='dynamic':
        features.update(current_monthly_revenue=1200000,current_operating_margin=0.2,current_cash_buffer_months=2,
                        current_dscr=1.5,current_debt_to_revenue=0.4,current_revenue_trend_3m=0.03,current_macro_stress=0.2)
    return {'schema_version':f'CATBOOST-V2-{len(features)}','kind':kind,'source_ref':'synthetic:test-fixture',
            'features':features,'currency':'RUB','annual_rate_unit':'fraction','population':'synthetic_sme'}


def test_same_value_confirmation_is_validated_and_clears_issue(tmp_path):
    case=Case(owner_id='a',request=LoanRequest(amount_rub=3000000),pending_clarifications=[FieldProblem(field='amount_rub',code='INVALID_VALUE')])
    text='Оставь прежнюю сумму 3000000 рублей'
    result=validate_extraction(raw({'amount_rub':3000000},text),text,case)
    assert result.patch.amount_rub==3000000 and not result.diagnostics
    bad=raw({'amount_rub':3000000},text);bad['evidence']['amount_rub']='другой текст'
    assert validate_extraction(bad,text,case).diagnostics


def test_reaffirming_saved_amount_unblocks_full_workflow_without_revision(tmp_path):
    class Chain:
        response=None
        def invoke(self,messages):return self.response
    parser=object.__new__(OllamaExtractor);parser.chain=Chain()
    with WorkflowApp(tmp_path/'same.db',extractor=parser) as app:
        text='Я ООО, нужно 3000000 рублей на товар на 24 месяца'
        parser.chain.response=raw(dict(legal_form='OOO',purpose='INVENTORY',amount_rub=3000000,term_months=24),text)
        first=app.handle(MessageInput(session_id='s',message_id='1',text=text),actor(consent=True))
        text='Измени сумму на −100 рублей'
        parser.chain.response=raw({},text)
        invalid=app.handle(MessageInput(session_id='s',message_id='2',text=text),actor(consent=True))
        assert invalid.next_action=='ASK_FIELDS' and invalid.request.amount_rub==3000000
        text='Оставь прежнюю сумму 3000000 рублей'
        parser.chain.response=raw({'amount_rub':3000000},text)
        confirmed=app.handle(MessageInput(session_id='s',message_id='3',text=text),actor(consent=True))
        assert confirmed.revision==first.revision and confirmed.next_action!='ASK_FIELDS'
        assert not any(gap.field=='amount_rub' for gap in confirmed.data_resolution.gaps)


def test_pending_clarification_blocks_financial_commands(tmp_path):
    from ..repositories.case_repository import CaseRepository
    from ..services.workflow_service import ToolSession
    from ..schemas.models import Status
    identity=actor(consent=True)
    case=Case(owner_id=identity.actor_id,company_id=identity.company_id,status=Status.WAITING_DOCUMENTS,
              request=LoanRequest(borrower_id=identity.active_borrower_id,legal_form='OOO',purpose='INVENTORY',amount_rub=3000000,term_months=24),
              pending_clarifications=[FieldProblem(field='amount_rub',code='INVALID_VALUE')])
    result=ToolSession(case,identity,CaseRepository(tmp_path/'guard.db'),FakeDatabaseModules()).execute('run_assessment',{})
    assert not result.ok and result.code=='UNRESOLVED_CLARIFICATIONS'


def test_repair_cannot_drop_unresolved_error():
    case=Case(owner_id='a')
    text='Сумма минус сто рублей, срок 24 месяца'
    first=validate_extraction(raw({'amount_rub':-100,'term_months':24},text),text,case)
    second=validate_extraction(raw({'term_months':24},text),text,case)
    result=merge_repair(first,second)
    assert result.patch.term_months==24
    assert [(issue.field,issue.code) for issue in result.diagnostics]==[('amount_rub','INVALID_VALUE')]


def test_conflicting_address_does_not_invalidate_legal_form():
    at=utcnow().isoformat()
    envelope={'request':{'legal_form':'OOO'},'decision_at':at,'case_id':'c','revision':1,'borrower_id':'b','company_id':40,'result_refs':{}}
    data={'company':{'company_id':40,'entity_type':'LEGAL_ENTITY','legal_form':'ООО','source_checked_at':at},
          'financial_statements':[],'bank_transactions':[],
          'provenance':[{'target_table':'companies','target_record_pk':{'company_id':40},'target_field':'legal_address','verification_status':'CONFLICT'}]}
    assert 'LEGAL_FORM_SOURCE_CONFLICT' not in build_evidence(envelope,data)['data_quality']['blocking_issues']


class FakeBusiness:
    reads=0
    def collect(self,company,cutoff):
        self.reads+=1
        at=cutoff.isoformat()
        return {'company':{'company_id':40,'entity_type':'LEGAL_ENTITY','legal_form':'ООО','source_checked_at':at},
                'provenance':[{'provenance_id':1,'target_table':'companies','target_record_pk':{'company_id':40},'target_field':'legal_form',
                               'verification_status':'VERIFIED','observed_value':'ООО','obtained_at':at,'verified_at':at}],
                'financial_statements':[],'bank_transactions':[]}
    def save_snapshot(self,envelope,code,payload):
        return self.reads*100+int(code[-1]),self.reads*1000+int(code[-1])


class FakeDatabaseModules(DatabaseModules):
    def __init__(self):
        self.repository=FakeBusiness();self.preparation=DataPreparationService(self.repository)
    def matcher(self,cutoff,legal_form=None):
        return ProductMatcher()


class Details:
    def extract(self,message,case):
        if message.text=='Статус':return Extraction(intent='STATUS')
        return Extraction(patch=LoanRequest(legal_form='OOO',purpose='INVENTORY',amount_rub=3000000,term_months=24),
                          evidence={key:message.text for key in ['legal_form','purpose','amount_rub','term_months']})


def test_evidence_origin_is_immutable_and_recheck_is_explicit(tmp_path):
    adapter=FakeDatabaseModules()
    with WorkflowApp(tmp_path/'test.db',extractor=Details(),adapter=adapter) as app:
        first=app.handle(MessageInput(session_id='s',message_id='1',text='Я ООО, нужно 3000000 рублей на товар на 24 месяца'),actor(consent=True))
        origin=first.data_context['product_selection_ref']
        assert first.evidence_recheck['snapshot_product_selection_ref']==origin
        assert first.evidence_recheck['current_product_selection_ref']==first.result_refs['products']
        again=app.handle(MessageInput(session_id='s',message_id='2',text='Статус'),actor(consent=True))
        assert again.data_context['product_selection_ref']==origin and adapter.repository.reads==1
        refreshed=app.handle(MessageInput(session_id='s',message_id='3',text='Обновить данные',command='REFRESH_EVIDENCE'),actor(consent=True))
        assert adapter.repository.reads==2
        assert refreshed.data_context['snapshot_ids']!=first.data_context['snapshot_ids']
        assert refreshed.data_context['decision_at']>first.data_context['decision_at']


@pytest.mark.parametrize('kind', ['baseline','dynamic'])
def test_real_registered_catboost_has_correct_horizon_and_semantics(kind):
    result=AssessmentService().assess(feature_bundle(kind),product_code='R01',request={'amount_rub':3000000,'term_months':24,'legal_form':'OOO'})
    assert result['status']=='DEMO_ESTIMATE'
    assert 0<=result['probability']<=1
    assert len(result['hazards'])==(12 if kind=='baseline' else 1)
    assert result['kind']==('CUMULATIVE_PD' if kind=='baseline' else 'ONE_MONTH_HAZARD')
    assert result['validated_for_real_lending'] is False and result['calibrator'] is None


def test_model_refuses_missing_wrong_or_unsupported_inputs():
    service=AssessmentService();request={'amount_rub':3000000,'term_months':24,'legal_form':'OOO'}
    assert service.assess(None,product_code='R01',request=request)['probability'] is None
    assert service.assess(feature_bundle(),product_code='R02',request=request)['status']=='UNSUPPORTED_MODEL'
    assert service.assess(feature_bundle(),product_code='R01',request={**request,'amount_rub':1})['status']=='INSUFFICIENT_DATA'
    outside=feature_bundle();outside['features']['term_months']=600
    assert service.assess(outside,product_code='R01',request={**request,'term_months':600})['status']=='UNSUPPORTED_MODEL'
    for key,value in [('annual_rate',24),('dscr',float('nan')),('entity_type','LEGAL_ENTITY')]:
        bundle=feature_bundle();bundle['features'][key]=value
        with pytest.raises(ValueError):FeatureInput.model_validate(bundle)


def test_registry_or_artifact_failure_is_a_technical_status():
    import copy
    request={'amount_rub':3000000,'term_months':24,'legal_form':'OOO'}
    broken=AssessmentService(registry={'invalid':'manifest'})
    assert broken.assess(feature_bundle(),product_code='R01',request=request)['status']=='TECHNICAL_ERROR'
    registry=copy.deepcopy(AssessmentService().registry)
    registry['models'][0]['sha256']='0'*64
    result=AssessmentService(registry=registry).assess(feature_bundle(),product_code='R01',request=request)
    assert result['status']=='TECHNICAL_ERROR' and result['probability'] is None


def test_annuity_rounding_reconciles_principal_and_zero_rate():
    from decimal import Decimal
    for rate in [0,0.24]:
        rows=annuity_schedule(3000000,rate,24)
        assert sum(Decimal(row['principal']) for row in rows)==Decimal('3000000')
        assert rows[-1]['balance']=='0.00'
        assert all(Decimal(row['payment'])==Decimal(row['principal'])+Decimal(row['interest']) for row in rows)


def test_cashflow_calculation_uses_explicit_cfads_and_no_invented_policy():
    bundle=feature_bundle()
    bundle['cashflow_scenario']={'cfads_monthly_rub':'500000','existing_debt_service_monthly_rub':'180000',
                                 'stress_cfads_monthly_rub':['400000'],'source_ref':'test:cashflow','basis_version':'explicit-test-1'}
    result=AssessmentService().assess(bundle,product_code='R01',request={'amount_rub':3000000,'term_months':24,'legal_form':'OOO'})
    calculation=result['calculation']
    assert 1.47<float(calculation['dscr'])<1.49
    assert calculation['fees_rub'] is None and calculation['threshold_applied'] is None
    assert float(calculation['stress_dscr'][0])<float(calculation['dscr'])


def test_questionnaire_filters_entity_and_does_not_verify_client_data():
    envelope={'request':{'legal_form':'IP','amount_rub':100},'product_routes':[{'product_id':'term'}],'decision_at':utcnow().isoformat()}
    fields=[{'product_code':'R01','field_code':'ooo','required_ip':False,'required_ooo':True,'target_db_field':'companies.name','field_label':'ООО'},
            {'product_code':'R01','field_code':'ip','required_ip':True,'required_ooo':False,'target_db_field':'companies.inn','field_label':'ИНН'}]
    result=build_questionnaire(envelope,{'company':{}},fields,{('R01','ip'):{'field_value':'123','value_source':'CLIENT','verification_status':'UNVERIFIED'}})
    assert len(result)==1 and result[0]['status']=='REPORTED'
    with pytest.raises(ValueError):validate_answer(True,'integer')


def test_document_csv_is_extracted_but_never_verified():
    content,media,digest,data=parse_document('report.csv',base64.b64encode('дата;сумма\n2026-10-01;100\n'.encode()).decode())
    assert data['status']=='EXTRACTED_UNVERIFIED' and data['is_verified'] is False
    assert data['tables'][0]['rows'][1][1]=='100'
    with pytest.raises(ValueError):parse_document('../report.csv',base64.b64encode(b'x').decode())


def test_only_reviewed_product_rule_mapping_executes():
    rule={'rule_code':'MIN','rule_description':'Сумма','comparison_operator':'GTE','threshold_value':100}
    request=LoanRequest(amount_rub=50)
    assert database_rule_check(rule,{},request,{},True).status=='UNKNOWN'
    assert database_rule_check(rule,{'field':'amount_rub','verified_only':False},request,{},True).status=='NO_MATCH'
