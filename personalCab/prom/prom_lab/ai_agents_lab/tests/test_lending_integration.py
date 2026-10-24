"""Opt-in end-to-end M1--M5 checks against a dedicated seeded PostgreSQL."""
from datetime import timedelta
from uuid import uuid4

import pytest

from .test_postgres_integration import config,identity,command
from .test_cabinet_modules import Details,feature_bundle
from ..agents.workflow import WorkflowApp
from ..operator import approve_features
from ..operator import resolve_profile
from ..repositories.business_repository import BusinessRepository
from ..repositories.case_repository import ConflictError
from ..schemas.models import Consent,MessageInput,Scope,utcnow
from ..services.lending import LendingService


def grant_all(actor):
    now=utcnow()
    actor.consents=[Consent(consent_id='test:'+scope.value,borrower_id=actor.active_borrower_id,scope=scope,
                           granted_at=now-timedelta(minutes=1),expires_at=now+timedelta(hours=1)) for scope in Scope]
    return actor


def action(name,arguments=None):
    return MessageInput(session_id='test',message_id=uuid4().hex,text=name,command=name,arguments=arguments or {})


def test_real_assessment_manual_offer_acceptance_and_idempotent_simulation(config):
    actor=grant_all(identity(config))
    with WorkflowApp(config,extractor=Details()) as app:
        first=app.handle(command(),actor)
        assert first.data_context and first.evidence_recheck
        approve_features(config,first.case_id,'R01',feature_bundle(),'test-reviewer')
        assessed=app.handle(action('ASSESS'),actor)
        assert assessed.assessment['status']=='DEMO_ESTIMATE',assessed.model_dump()
        again=app.handle(action('ASSESS'),actor)
        assert again.assessment['assessment_id']==assessed.assessment['assessment_id']
        submitted=app.handle(action('SUBMIT'),actor)
        assert submitted.bank_application['status']=='MANUAL_REVIEW'
        lender_id=submitted.bank_application['lender_case_id']
        service=LendingService(config)
        offered=service.review(lender_id,reviewer='test-reviewer',decision='OFFERED',reason='Explicit synthetic test case',
                               offer={'amount_rub':'3000000','term_months':24,'annual_rate_fraction':'0.24','repayment_type':'ANNUITY',
                                      'fees_rub':[],'conditions':['DEMO only'], 'expires_at':(utcnow()+timedelta(hours=1)).isoformat()})
        request={'offer_id':offered['offer']['offer_id'],'acknowledge_demo':True}
        # Fetch reviewer result without allowing the borrower to approve it.
        polled=app.handle(MessageInput(session_id='test',message_id=uuid4().hex,text='Статус'),actor)
        assert polled.bank_application['status']=='OFFERED'
        accepted=app.handle(action('ACCEPT_OFFER',request),actor)
        assert accepted.bank_application['status']=='ACCEPTED'
        execute=action('EXECUTE_DEMO',request)
        completed=app.handle(execute,actor)
        assert completed.status=='COMPLETED'
        assert completed.bank_application['execution']['simulated'] is True
        assert app.handle(execute,actor)==completed
        case=app.repository.load(completed.case_id,actor)
        paid=service.record_demo_payment(case,actor,'payment-1','1000.00')
        assert service.record_demo_payment(case,actor,'payment-1','1000.00')==paid
        assert paid['servicing']['no_real_money'] is True
        assert len(paid['payments'])==1
        with pytest.raises(ConflictError):service.record_demo_payment(case,actor,'payment-1','2000.00')
        with pytest.raises(ValueError):service.record_demo_payment(case,actor,'overpay','999999999.00')
        with config.connect(workflow=True) as db:
            assert db.execute("SELECT count(*) AS n FROM lender_events WHERE lender_case_id=%s AND event_type='EXECUTED_DEMO'",(lender_id,)).fetchone()['n']==1
            assert db.execute('SELECT pd FROM public.scoring_results WHERE scoring_result_id=%s',(assessed.assessment['scoring_result_id'],)).fetchone()['pd'] is not None


def test_missing_features_and_revoked_consent_do_not_invent_estimate(config):
    actor=grant_all(identity(config))
    with WorkflowApp(config,extractor=Details()) as app:
        first=app.handle(command(),actor)
        result=app.handle(action('ASSESS'),actor)
        assert result.assessment['status']=='INSUFFICIENT_DATA'
        assert result.assessment['probability'] is None
        actor.denied_scopes=[Scope.CREDIT_ASSESSMENT]
        denied=app.handle(action('ASSESS'),actor)
        assert denied.error_code=='CONSENT_DENIED'
        actor.denied_scopes=[]
        resumed=app.handle(action('ASSESS'),actor)
        assert resumed.assessment['assessment_id']==result.assessment['assessment_id']
        assert resumed.next_action=='ASSESSMENT_READY' and resumed.status=='WAITING_DOCUMENTS'
        with config.connect(workflow=True) as db:
            assert db.execute('SELECT count(*) AS n FROM assessments WHERE case_id=%s',(first.case_id,)).fetchone()['n']==1


def test_refreshed_request_rejects_old_offer(config):
    actor=grant_all(identity(config))
    with WorkflowApp(config,extractor=Details()) as app:
        first=app.handle(command(),actor)
        app.handle(action('ASSESS'),actor)
        submitted=app.handle(action('SUBMIT'),actor)
        app.handle(action('REFRESH_EVIDENCE'),actor)
        with pytest.raises(ConflictError):
            LendingService(config).review(submitted.bank_application['lender_case_id'],reviewer='test-reviewer',decision='DECLINED',reason='stale')


def test_manual_decline_closes_case_without_simulated_disbursement(config):
    actor=grant_all(identity(config))
    with WorkflowApp(config,extractor=Details()) as app:
        app.handle(command(),actor)
        app.handle(action('ASSESS'),actor)
        submitted=app.handle(action('SUBMIT'),actor)
        LendingService(config).review(submitted.bank_application['lender_case_id'],reviewer='test-reviewer',decision='DECLINED',reason='Synthetic manual decision')
        result=app.handle(action('POLL_STATUS'),actor)
        assert result.status=='COMPLETED' and result.bank_application['status']=='DECLINED'
        assert result.bank_application['execution'] is None


def test_changed_reviewed_vector_requires_a_new_assessment(config):
    actor=grant_all(identity(config))
    with WorkflowApp(config,extractor=Details()) as app:
        first=app.handle(command(),actor)
        approve_features(config,first.case_id,'R01',feature_bundle(),'test-reviewer')
        initial=app.handle(action('ASSESS'),actor)
        changed=feature_bundle();changed['features']['dscr']=2.0
        approve_features(config,first.case_id,'R01',changed,'test-reviewer')
        stale=app.handle(action('SUBMIT'),actor)
        assert stale.error_code=='STALE_PROCESS' and stale.bank_application is None
        reassessed=app.handle(action('ASSESS'),actor)
        assert reassessed.assessment['assessment_id']!=initial.assessment['assessment_id']
        assert app.handle(action('SUBMIT'),actor).bank_application['status']=='MANUAL_REVIEW'


@pytest.mark.parametrize('code,need',[('R02','REPEATED_PURCHASES'),('R03','CASH_GAP')])
def test_manual_line_opens_limit_without_disbursing_it(config,code,need):
    from ..schemas.models import Extraction,LoanRequest
    class RouteDetails:
        def extract(self,message,case):
            values=dict(legal_form='OOO',purpose='WORKING_CAPITAL',amount_rub=3000000,term_months=24,financing_need=need)
            return Extraction(patch=LoanRequest(**values),evidence={field:message.text for field in values})
    actor=grant_all(identity(config))
    with WorkflowApp(config,extractor=RouteDetails()) as app:
        app.handle(command(),actor)
        assessed=app.handle(action('ASSESS',{'product_code':code}),actor)
        assert assessed.assessment['status']=='UNSUPPORTED_MODEL' and assessed.assessment['probability'] is None
        submitted=app.handle(action('SUBMIT',{'product_code':code}),actor)
        offered=LendingService(config).review(submitted.bank_application['lender_case_id'],reviewer='test-reviewer',decision='OFFERED',reason='Synthetic limit example',
                                               offer={'amount_rub':'3000000','term_months':24,'annual_rate_fraction':'0.24',
                                                      'repayment_type':'LIMIT_ONLY','fees_rub':[],'conditions':[],
                                                      'expires_at':(utcnow()+timedelta(hours=1)).isoformat()})
        arguments={'offer_id':offered['offer']['offer_id'],'acknowledge_demo':True}
        app.handle(action('ACCEPT_OFFER',arguments),actor)
        completed=app.handle(action('EXECUTE_DEMO',arguments),actor)
        assert completed.bank_application['execution']['kind']=='LIMIT_OPENED'
        assert completed.bank_application['execution']['amount_rub']=='0'
        assert completed.bank_application['execution']['credit_limit_rub']=='3000000'


def test_questionnaire_and_documents_enter_a_new_snapshot_only(config):
    import base64
    from personalCab.frontend.server import ChatService,ChatCommand,CaseCommand
    from personalCab.prom.prom_lab.ai_agents_lab.repositories.postgres_config import PostgresConfig as RuntimeConfig
    company=identity(config).company_id
    class RuntimeDetails:
        def extract(self,message,case):
            return Details().extract(message,case).model_dump(mode='json')
    service=ChatService(RuntimeConfig(conninfo=config.conninfo),company_id=company,evidence_consent=True,extractor=RuntimeDetails(),require_login=False)
    _,actor,session,_=service.client(None)
    initial=service.handle(ChatCommand(message_id=uuid4().hex,text='Я ООО, нужно 3000000 рублей на товар на 24 месяца.'),actor,session)['result']
    case=service.repository.load(initial['case_id'],actor)
    field=next(item for item in initial['data_context']['questionnaire'] if item['status']=='MISSING' and item['data_type'] in {'text','character varying'})
    BusinessRepository(config).answer_fields(case,actor,[{'product_code':field['product_code'],'field_code':field['field_code'],'value':'Synthetic answer'}])
    encoded=base64.b64encode(b'date,amount\n2026-10-01,100\n').decode()
    documents=service.controls.upload(case,actor,'test.csv',encoded)
    assert service.controls.upload(case,actor,'test.csv',encoded)==documents
    refreshed=service.handle(CaseCommand(message_id=uuid4().hex,text='Обновить данные',command='REFRESH_EVIDENCE'),actor,session)['result']
    result=next(item for item in refreshed['data_context']['questionnaire'] if (item['product_code'],item['field_code'])==(field['product_code'],field['field_code']))
    assert result['value']=='Synthetic answer' and result['status']=='REPORTED'
    assert refreshed['data_context']['documents'][0]['document_id']==documents[0]['document_id']
    assert 'extracted_data' not in refreshed['data_context']['documents'][0]
    assert refreshed['data_context']['snapshot_ids']!=initial['data_context']['snapshot_ids']
    with config.connect() as db:
        status=db.execute('SELECT request_status FROM public.application_data_requests WHERE application_id=%s AND field_code=%s',
                          (initial['data_context']['application_ids'][field['product_code']],field['field_code'])).fetchone()['request_status']
        assert status=='ANSWERED'


def test_operator_profile_resolution_is_cutoff_bound_and_keeps_sources(config):
    from psycopg.types.json import Jsonb
    from ..services.data_preparation import build_evidence
    with config.connect() as db:
        company=db.execute("INSERT INTO public.companies(entity_type,inn,name,source_checked_at) VALUES('LEGAL_ENTITY',%s,'Synthetic profile resolution',CURRENT_TIMESTAMP) RETURNING company_id",
                           ('9'+str(uuid4().int%1000000000).zfill(9),)).fetchone()['company_id']
        db.execute("INSERT INTO public.company_data_provenance(company_id,target_table,target_record_pk,target_field,observed_value,source_type,source_reference,obtained_at,verification_status) VALUES(%s,'companies',%s,'legal_form',%s,'OTHER','test-conflict',CURRENT_TIMESTAMP,'CONFLICT')",
                   (company,Jsonb({'company_id':company}),Jsonb('conflict')))
    # Use a historical cutoff; host and container clocks may differ by milliseconds.
    before=utcnow()-timedelta(seconds=1)
    resolve_profile(config,company,{'legal_form':'OOO','source_ref':'test:manual-proof','available_at':before.isoformat()},'test-reviewer')
    repository=BusinessRepository(config)
    old=repository.company_profile(company,before)
    assert old['profile_resolution'] is None
    at=utcnow()
    raw=repository.company_profile(company,at)
    envelope={'request':{'legal_form':'OOO'},'decision_at':at.isoformat(),'case_id':'test','revision':1,'borrower_id':'b','company_id':company,'result_refs':{}}
    evidence=build_evidence(envelope,raw)
    assert evidence['verified_facts'][0]['value']=='OOO'
    assert 'LEGAL_FORM_SOURCE_CONFLICT' not in evidence['data_quality']['blocking_issues']
    assert raw['provenance'][0]['verification_status']=='CONFLICT'
