"""Opt-in HTTP acceptance against an isolated V2 DEMO deployment."""
import os
import json
import base64
from datetime import timedelta
from uuid import uuid4
from http.cookiejar import CookieJar
from urllib.request import build_opener,HTTPCookieProcessor,Request
from urllib.error import HTTPError
import pytest
from personalCab.prom_v2.models import utcnow

pytestmark=pytest.mark.skipif(not os.getenv('AURELIUS_V2_TEST_URL'),reason='Isolated V2 deployment not configured')


class Client:
    sessions={}
    def __init__(self,login):
        if login in self.sessions:
            self.http=self.sessions[login]
            if self.call('session')[0]==200:return
        self.http=build_opener(HTTPCookieProcessor(CookieJar()))
        assert self.call('login',{'login':login,'password':'Aurelius2026!'})[0]==200
        self.sessions[login]=self.http
    def call(self,path,body=None):
        request=Request(os.environ['AURELIUS_V2_TEST_URL']+'/api/v2/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:response=self.http.open(request,timeout=180)
        except HTTPError as e:response=e
        with response:return response.status,json.load(response)
    def action(self,body):
        return self.call('action',{'request_id':uuid4().hex,**body})
    def command(self,action,case=None,arguments=None,text=None):
        cmd={'request_id':uuid4().hex,'action':action,'expected_version':case['version'] if case else 0,'arguments':arguments or {}}
        if case:cmd['case_id']=case['case_id']
        if text:cmd['text']=text
        status,result=self.action({'kind':'command','command':cmd})
        assert status==200,result
        assert not result.get('error_code'),result
        return result
    def current(self,id):
        return next(c for c in self.call('state')[1]['cases'] if c['case_id']==id)


def prepare():
    client=Client('client01');bank=Client('analyst')
    case=client.command('CREATE')
    case=client.command('UPDATE_REQUEST',case,{'patch':{'legal_form':'IP','purpose':'INVENTORY','amount_rub':3000000,'term_months':24}})
    case=client.command('SELECT_PRODUCT',case,{'product_id':'term'})
    for scope in ('EVIDENCE_COLLECTION','CREDIT_ASSESSMENT','BANK_STATUS','APPLICATION_SUBMISSION','DEMO_EXECUTION'):
        assert client.action({'kind':'consent','scope':scope,'granted':True})[0]==200
    return client,bank,case


def test_session_isolation_rag_snapshot_and_missing_features():
    client,bank,case=prepare();other=Client('client02')
    assert case['case_id'] not in [c['case_id'] for c in other.call('state')[1]['cases']]
    assert other.action({'kind':'command','command':{'request_id':uuid4().hex,'action':'CANCEL','case_id':case['case_id'],'expected_version':case['version']}})[0]==403
    assert client.action({'kind':'review','case_id':case['case_id'],'expected_version':case['version'],'arguments':{}})[0]==403
    answer=client.command('CHAT',case,text='Какой формат ИНН для R01 ООО?')
    assert answer['knowledge_answer']['status']=='FOUND' and answer['request']==case['request']
    snapshot=client.command('REFRESH_EVIDENCE',answer)
    assert snapshot['data_context']['snapshot_ids']['R01']
    field=next(q for q in snapshot['data_context']['questionnaire'] if q['editable'] and q['data_type']=='text' and q['value'] is None)
    status,result=client.action({'kind':'fields','case_id':snapshot['case_id'],'expected_version':snapshot['version'],
                                 'answers':[{'product_code':field['product_code'],'field_code':field['field_code'],'value':'Synthetic answer'}]})
    assert status==200,result
    snapshot=client.current(case['case_id'])
    status,result=client.action({'kind':'document','case_id':snapshot['case_id'],'expected_version':snapshot['version'],'filename':'test.csv','content_base64':base64.b64encode(b'month,incoming_rub\n2026-09,100000\n').decode()})
    assert status==200,result
    snapshot=client.command('REFRESH_EVIDENCE',client.current(case['case_id']))
    assert any(d['filename']=='test.csv' for d in snapshot['data_context']['documents'])
    assessed=client.command('ASSESS',snapshot)
    assert assessed['assessment']['status']=='INSUFFICIENT_DATA' and assessed['assessment']['probability'] is None
    client.action({'kind':'consent','scope':'CREDIT_ASSESSMENT','granted':False})
    status,denied=client.action({'kind':'command','command':{'request_id':uuid4().hex,'action':'ASSESS','case_id':assessed['case_id'],'expected_version':assessed['version']}})
    assert status==200 and denied['error_code']=='CONSENT_REQUIRED'
    assert client.call('logout',{})[0]==200 and client.call('state')[0]==401


def test_reviewed_model_manual_offer_acceptance_and_execution():
    from personalCab.prom.prom_lab.ai_agents_lab.tests.test_cabinet_modules import feature_bundle
    client,bank,case=prepare()
    case=client.command('REFRESH_EVIDENCE',case)
    bundle=feature_bundle();bundle['features']['entity_type']='IP'
    status,result=bank.action({'kind':'features','case_id':case['case_id'],'expected_version':case['version'],'arguments':bundle})
    assert status==200,result
    case=client.command('ASSESS',client.current(case['case_id']))
    assert case['assessment']['status']=='DEMO_ESTIMATE',case['assessment']
    case=client.command('SUBMIT',case)
    status,result=bank.action({'kind':'review','case_id':case['case_id'],'expected_version':case['version'],'arguments':{'decision':'OFFERED','reason':'Explicit synthetic acceptance test','offer':{'amount_rub':'3000000','term_months':24,'annual_rate_fraction':'0.24','repayment_type':'ANNUITY','fees_rub':[],'conditions':['DEMO only'],'expires_at':(utcnow()+timedelta(hours=1)).isoformat()}}})
    assert status==200,result
    case=client.current(case['case_id']);assert case['status']=='OFFERED'
    args={'offer_id':case['bank_application']['offer']['offer_id'],'acknowledge_demo':True}
    case=client.command('ACCEPT_OFFER',case,args)
    case=client.command('EXECUTE_DEMO',case,args)
    assert case['status']=='EXECUTED_DEMO' and case['bank_application']['execution']['kind']=='DISBURSEMENT'
    case=client.command('CHAT',case,text='Какой статус решения?')
    assert 'Симуляция исполнения подтверждена' in case['message']
    payment={'request_id':uuid4().hex,'kind':'payment','case_id':case['case_id'],'expected_version':case['version'],'operation_id':uuid4().hex,'amount_rub':'1000.00'}
    first=client.call('action',payment);assert first[0]==200,first
    assert client.call('action',payment)==first


def test_revision_conflict_and_request_id_replay():
    client=Client('client01');case=client.command('CREATE')
    body={'request_id':uuid4().hex,'kind':'command','command':{'request_id':uuid4().hex,'action':'UPDATE_REQUEST','case_id':case['case_id'],'expected_version':case['version'],'arguments':{'patch':{'amount_rub':1500000}}}}
    first=client.call('action',body);assert first[0]==200
    assert client.call('action',body)==first
    body={**body,'request_id':uuid4().hex,'command':{**body['command'],'request_id':uuid4().hex}}
    conflict=client.call('action',body)
    assert conflict[0]==409 and conflict[1]['code']=='STALE_CASE_VERSION'


@pytest.mark.parametrize('kind',['document','fields'])
def test_new_evidence_revokes_offer_until_fresh_snapshot_and_review(kind):
    client,bank,case=prepare()
    case=client.command('REFRESH_EVIDENCE',case)
    previous_snapshot=case['data_context']
    field=next(q for q in previous_snapshot['questionnaire'] if q['editable'] and q['data_type']=='text' and q['value'] is None)
    case=client.command('ASSESS',case)
    case=client.command('SUBMIT',case)
    old_lender=case['bank_application']['lender_case_id']
    offer={'amount_rub':'3000000','term_months':24,'annual_rate_fraction':'0.24',
           'repayment_type':'ANNUITY','fees_rub':['12345.67'],'conditions':['Synthetic regression only'],
           'expires_at':(utcnow()+timedelta(hours=1)).isoformat()}
    assert bank.action({'kind':'review','case_id':case['case_id'],'expected_version':case['version'],
                        'arguments':{'decision':'OFFERED','reason':'Explicit synthetic regression review','offer':offer}})[0]==200
    case=client.current(case['case_id'])
    old_offer=case['bank_application']['offer']['offer_id']
    revision=case['revision']
    payload={'request_id':uuid4().hex,'kind':kind,'case_id':case['case_id'],'expected_version':case['version']}
    if kind=='document':
        payload.update(filename='new-evidence.csv',content_base64=base64.b64encode(b'month,incoming_rub\n2026-09,777\n').decode())
    else:
        payload['answers']=[{'product_code':field['product_code'],'field_code':field['field_code'],'value':'New synthetic answer'}]
    first=client.call('action',payload)
    assert first[0]==200,first
    assert client.call('action',payload)==first
    case=client.current(case['case_id'])
    assert case['revision']==revision+1 and case['status']=='NEEDS_INFO'
    assert case['data_context']==previous_snapshot
    assert case['assessment'] is None and case['bank_application'] is None and case['evidence_stale']
    for action in ('ASSESS','SUBMIT','POLL_STATUS','ACCEPT_OFFER'):
        command={'request_id':uuid4().hex,'action':action,'case_id':case['case_id'],'expected_version':case['version']}
        if action=='ACCEPT_OFFER':command['arguments']={'offer_id':old_offer,'acknowledge_demo':True}
        status,denied=client.action({'kind':'command','command':command})
        assert status==200 and denied['error_code']=='EVIDENCE_STALE',denied
        case=client.current(case['case_id'])
    assert bank.action({'kind':'review','case_id':case['case_id'],'expected_version':case['version'],
                        'arguments':{'decision':'OFFERED','reason':'Must not review stale evidence','offer':offer}})[0]==409
    case=client.command('REFRESH_EVIDENCE',case)
    assert not case['evidence_stale'] and case['revision']==revision+1
    assert case['data_context']['snapshot_ids']!=previous_snapshot['snapshot_ids']
    if kind=='document':
        assert any(d['filename']=='new-evidence.csv' for d in case['data_context']['documents'])
    else:
        assert next(q['value'] for q in case['data_context']['questionnaire'] if q['field_code']==field['field_code'])=='New synthetic answer'
    case=client.command('ASSESS',case)
    case=client.command('SUBMIT',case)
    assert case['bank_application']['lender_case_id']!=old_lender
    assert bank.action({'kind':'review','case_id':case['case_id'],'expected_version':case['version'],
                        'arguments':{'decision':'OFFERED','reason':'Reviewed again on the fresh snapshot','offer':offer}})[0]==200
    case=client.current(case['case_id'])
    assert case['bank_application']['offer']['offer_id']!=old_offer
    case=client.command('ACCEPT_OFFER',case,{'offer_id':case['bank_application']['offer']['offer_id'],'acknowledge_demo':True})
    assert case['status']=='ACCEPTED'


def test_duplicate_document_does_not_revoke_current_offer():
    client,bank,case=prepare()
    content=base64.b64encode(b'month,incoming_rub\n2026-09,777\n').decode()
    document={'kind':'document','filename':'same.csv','content_base64':content}
    assert client.action({**document,'case_id':case['case_id'],'expected_version':case['version']})[0]==200
    case=client.command('REFRESH_EVIDENCE',client.current(case['case_id']))
    case=client.command('ASSESS',case)
    case=client.command('SUBMIT',case)
    assert bank.action({'kind':'review','case_id':case['case_id'],'expected_version':case['version'],
                        'arguments':{'decision':'OFFERED','reason':'Explicit synthetic duplicate regression',
                                     'offer':{'amount_rub':'3000000','term_months':24,'annual_rate_fraction':'0.24',
                                              'repayment_type':'ANNUITY','fees_rub':[],'conditions':[],
                                              'expires_at':(utcnow()+timedelta(hours=1)).isoformat()}}})[0]==200
    case=client.current(case['case_id'])
    assert client.action({**document,'case_id':case['case_id'],'expected_version':case['version']})[0]==200
    unchanged=client.current(case['case_id'])
    assert unchanged['revision']==case['revision'] and unchanged['status']=='OFFERED'
    assert unchanged['bank_application']==case['bank_application'] and not unchanged['evidence_stale']


@pytest.mark.parametrize('product,need',[('rcl','REPEATED_PURCHASES'),('overdraft','CASH_GAP')])
def test_limit_products_open_limit_without_disbursing(product,need):
    client,bank,case=prepare()
    case=client.command('UPDATE_REQUEST',case,{'patch':{'financing_need':need}})
    case=client.command('SELECT_PRODUCT',case,{'product_id':product})
    case=client.command('REFRESH_EVIDENCE',case)
    case=client.command('ASSESS',case)
    assert case['assessment']['probability'] is None
    case=client.command('SUBMIT',case)
    status,result=bank.action({'kind':'review','case_id':case['case_id'],'expected_version':case['version'],'arguments':{'decision':'OFFERED','reason':'Explicit synthetic limit-only manual review','offer':{'amount_rub':'3000000','term_months':24,'annual_rate_fraction':'0.24','repayment_type':'LIMIT_ONLY','fees_rub':[],'conditions':['DEMO only'],'expires_at':(utcnow()+timedelta(hours=1)).isoformat()}}})
    assert status==200,result
    case=client.current(case['case_id'])
    assert case['bank_application']['offer']['schedule']==[]
    args={'offer_id':case['bank_application']['offer']['offer_id'],'acknowledge_demo':True}
    case=client.command('ACCEPT_OFFER',case,args)
    case=client.command('EXECUTE_DEMO',case,args)
    assert case['bank_application']['execution']['kind']=='LIMIT_OPENED'
