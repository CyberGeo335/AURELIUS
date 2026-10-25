"""Native workspace HTTP contracts on the explicitly configured synthetic V2."""
import base64
from datetime import timedelta
from uuid import uuid4
import pytest
from .test_integrated_web import Client, prepare, pytestmark
from personalCab.prom_v2.models import utcnow


def test_database_catalog_keeps_sixteen_directions_and_exposes_approval_and_models():
    status,catalog=Client('client01').call('catalog')
    assert status==200 and len(catalog['candidates'])==16
    database=[c for c in catalog['candidates'] if c['database_supported']]
    assert {c['product_id'] for c in database}=={'term','rcl','overdraft'}
    assert all(c['source_conditions']['validity'] in {'APPROVED','UNKNOWN'} for c in database)
    assert all(c['source_conditions']['terms'] for c in database)
    assert catalog['model_registry']['version']=='DEMO-REGISTRY-1'
    assert all('path' not in m for m in catalog['model_registry']['models'])


def test_early_profile_requires_consent_and_never_prefills_previous_loan():
    client=Client('client01');case=client.command('CREATE')
    client.action({'kind':'consent','scope':'EVIDENCE_COLLECTION','granted':False})
    status,denied=client.action({'kind':'command','command':{'request_id':uuid4().hex,'action':'LOOKUP_PROFILE','case_id':case['case_id'],'expected_version':case['version']}})
    assert status==200 and denied['error_code']=='CONSENT_REQUIRED'
    assert 'LOOKUP_PROFILE' not in client.current(case['case_id'])['allowed_actions']
    client.action({'kind':'consent','scope':'EVIDENCE_COLLECTION','granted':True})
    case=client.command('LOOKUP_PROFILE',denied)
    assert case['business_profile']['company_id']==40
    assert case['request']['amount_rub'] is None and case['request']['term_months'] is None
    for fact in case['business_profile']['verified_facts']:
        assert fact['field']=='legal_form' and fact['source_ref'] and fact['company_id']==40


def test_documents_remain_current_before_snapshot_and_after_request_revision():
    client,_,case=prepare()
    doc={'kind':'document','filename':'before-snapshot.csv','content_base64':base64.b64encode(b'month,incoming_rub\n2026-09,123\n2026-09,123\n').decode()}
    assert client.action({**doc,'case_id':case['case_id'],'expected_version':case['version']})[0]==200
    case=client.current(case['case_id'])
    assert case['data_context'] is None
    assert case['current_data']['documents'][0]['statement']['duplicate_months']==['2026-09']
    case=client.command('UPDATE_REQUEST',case,{'patch':{'amount_rub':2000000}})
    current=client.current(case['case_id'])
    assert current['data_context'] is None and current['current_data']['documents'][0]['filename']=='before-snapshot.csv'
    status,summary=client.call('state?summary=1&detail='+case['case_id'])
    assert status==200
    assert next(c for c in summary['cases'] if c['case_id']==case['case_id'])['current_data']['documents']
    assert all(c['current_data'] is None and c['history']==[] for c in summary['cases'] if c['case_id']!=case['case_id'])


def test_bank_assignment_authority_preview_audit_and_explicit_confirmation():
    client,bank,case=prepare();other=Client('client02')
    case=client.command('REFRESH_EVIDENCE',case)
    case=client.command('ASSESS',case);case=client.command('SUBMIT',case)
    def bank_action(kind,args):
        nonlocal case
        result=bank.action({'kind':kind,'case_id':case['case_id'],'expected_version':case['version'],'arguments':args})
        assert result[0]==200,result
        case=client.current(case['case_id'])
        return result
    bank_action('claim',{})
    assert case['review_owner']=='analyst'
    bank_action('authority',{'verified':True,'source_ref':'Synthetic delegated authority document','available_at':(utcnow()-timedelta(days=1)).isoformat()})
    assert case['authority_evidence']['verified'] is True
    changes=bank.current(case['case_id'])['client_changes']
    bank_action('review_changes',{'fields':list({c['field'] for c in changes}),'source_ref':'Synthetic registry check'})
    assert all(c['review_status']=='REVIEWED' for c in bank.current(case['case_id'])['client_changes'])
    args={'decision':'OFFERED','reason':'Explicit synthetic counteroffer preview',
          'offer':{'amount_rub':'2000000','term_months':12,'annual_rate_fraction':'0.23','repayment_type':'ANNUITY','fees_rub':['111.00'],'conditions':['Synthetic only'],'expires_at':(utcnow()+timedelta(hours=1)).isoformat()}}
    body={'case_id':case['case_id'],'expected_version':case['version'],'arguments':args}
    before=case['version']
    status,preview=bank.call('review-preview',body)
    assert status==200 and len(preview['offer']['schedule'])==12 and preview['offer']['assessment_matches_offer'] is False
    assert client.current(case['case_id'])['version']==before
    assert client.call('review-preview',body)[0]==403
    assert bank.call('review-preview',{**body,'expected_version':before-1})[0]==409
    bank_action('review',args)
    assert case['status']=='OFFERED' and case['offer_history'][0]['offer']['fees_rub']==['111.00']
    status,audit=bank.call('audit?case_id='+case['case_id'])
    assert status==200 and {'review','claim','authority','review_changes'}<={e['action'] for e in audit['events']}
    review=next(e for e in audit['events'] if e['action']=='review')
    assert review['metadata']['reason']==args['reason'] and review['metadata']['snapshot_ids']
    assert other.call('audit?case_id='+case['case_id'])[0]==403
    doc={'kind':'document','filename':'superseding.csv','content_base64':base64.b64encode(b'month,incoming_rub\n2026-09,123\n').decode()}
    assert client.action({**doc,'case_id':case['case_id'],'expected_version':case['version']})[0]==200
    case=client.current(case['case_id'])
    assert case['offer_history'][0]['invalidated_at'] and case['bank_application'] is None


def test_operator_field_verification_resolves_old_revision_changes():
    client,bank,case=prepare();case=client.command('REFRESH_EVIDENCE',case)
    field=next(q for q in case['data_context']['questionnaire'] if q['editable'] and q['data_type']=='text' and q['value'] is None)
    assert client.action({'kind':'fields','case_id':case['case_id'],'expected_version':case['version'],'answers':[{'product_code':field['product_code'],'field_code':field['field_code'],'value':'Synthetic evidence change'}]})[0]==200
    case=client.command('REFRESH_EVIDENCE',client.current(case['case_id']))
    assert bank.action({'kind':'verify','case_id':case['case_id'],'expected_version':case['version'],'arguments':{'field_code':field['field_code'],'value':'Synthetic evidence change','source_ref':'Synthetic verified document'}})[0]==200
    current=bank.current(case['case_id'])
    changes=[c for c in current['field_changes'] if c['field_code']==field['field_code']]
    assert changes and all(c['review_status']=='REVIEWED' for c in changes)


def test_borrower_cannot_claim_or_resolve_profile_and_version_is_strict():
    client,_,case=prepare()
    for kind in ('claim','authority','profile_resolution','review_changes'):
        assert client.action({'kind':kind,'case_id':case['case_id'],'expected_version':case['version'],'arguments':{}})[0]==403
    assert client.action({'kind':'document','case_id':case['case_id'],'expected_version':float(case['version']),'filename':'x.csv','content_base64':'x'})[0]==400


def test_actual_model_explanation_is_scoped_and_separate_from_cumulative_probability():
    from personalCab.prom.prom_lab.ai_agents_lab.tests.test_cabinet_modules import feature_bundle
    client,bank,case=prepare();case=client.command('REFRESH_EVIDENCE',case)
    bundle=feature_bundle();bundle['features']['entity_type']='IP'
    assert bank.action({'kind':'features','case_id':case['case_id'],'expected_version':case['version'],'arguments':bundle})[0]==200
    case=client.command('ASSESS',client.current(case['case_id']))
    explanation=case['assessment']['explanation']
    assert explanation['status']=='AVAILABLE' and explanation['space']=='RAW_MONTHLY_LOGIT'
    assert len(explanation['contributions'])==16 and case['assessment']['horizon_months']==12
    assert explanation['model_sha256']==case['assessment']['model_sha256']


def test_source_format_conflict_is_visible_without_rewriting_immutable_snapshot():
    client,_,case=prepare();case=client.command('REFRESH_EVIDENCE',case)
    snapshot=case['data_context']
    current=client.current(case['case_id'])
    q=next(q for q in current['current_data']['questionnaire'] if q['target']=='companies.inn')
    assert q['status']=='CONFLICT' and q['validation_error'] and q['source_ref'].startswith('snapshot:')
    assert current['data_context']==snapshot and current['request']['inn'] is None
