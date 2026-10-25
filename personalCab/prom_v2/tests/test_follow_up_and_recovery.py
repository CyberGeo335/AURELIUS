"""Opt-in acceptance on the dedicated synthetic V2 deployment."""
import base64
from datetime import timedelta
from uuid import uuid4
from personalCab.prom_v2.models import utcnow
from .test_integrated_web import Client, prepare, pytestmark


def answer(client,case,fields):
    return client.action({'kind':'fields','case_id':case['case_id'],'expected_version':case['version'],
                          'answers':[{'product_code':q['product_code'],'field_code':q['field_code'],'value':'Synthetic response '+str(i)} for i,q in enumerate(fields)]})


def test_latest_answers_and_files_are_visible_without_mutating_the_snapshot():
    client,_,case=prepare();other=Client('client02')
    case=client.command('REFRESH_EVIDENCE',case)
    original=case['data_context']
    fields=[q for q in original['questionnaire'] if q['editable'] and q['data_type']=='text' and q['value'] is None][:2]
    assert answer(client,case,fields[:1])[0]==200
    latest=client.current(case['case_id'])
    assert latest['data_context']==original and latest['evidence_stale']
    assert next(q['value'] for q in latest['current_data']['questionnaire'] if q['field_code']==fields[0]['field_code'])=='Synthetic response 0'
    assert answer(client,latest,fields[1:])[0]==200  # Another reply while a previous snapshot is stale.
    latest=client.current(case['case_id'])
    assert client.action({'kind':'document','case_id':case['case_id'],'expected_version':latest['version'],'filename':'latest.csv',
                          'content_base64':base64.b64encode(b'month,total\n2026-10,42\n').decode()})[0]==200
    latest=client.current(case['case_id'])
    assert latest['data_context']==original
    assert any(d['filename']=='latest.csv' for d in latest['current_data']['documents'])
    assert case['case_id'] not in [c['case_id'] for c in other.call('state')[1]['cases']]


def test_addressed_follow_up_waits_for_all_replies_then_reenters_checking():
    client,bank,case=prepare();case=client.command('REFRESH_EVIDENCE',case)
    original=case['data_context']
    fields=[q for q in original['questionnaire'] if q['editable'] and q['data_type']=='text' and q['value'] is None][:2]
    assert len(fields)==2
    case=client.command('ASSESS',case);case=client.command('SUBMIT',case)
    old_lender=case['bank_application']['lender_case_id']
    assert bank.action({'kind':'review','case_id':case['case_id'],'expected_version':case['version'],'arguments':{
        'decision':'REQUEST_DATA','reason':'Provide the two addressed fields and a statement',
        'requested_fields':[q['field_code'] for q in fields],'requested_documents':['statement.csv'],
        'due_at':(utcnow()+timedelta(days=2)).isoformat()}})[0]==200
    case=client.current(case['case_id']);revision=case['revision']
    assert answer(client,case,fields)[0]==200
    case=client.current(case['case_id'])
    assert case['revision']==revision+1 and case['status']=='NEEDS_INFO' and case['follow_ups'][-1]['status']=='OPEN'
    body={'request_id':uuid4().hex,'kind':'document','case_id':case['case_id'],'expected_version':case['version'],
          'filename':'statement.csv','content_base64':base64.b64encode(b'month,total\n2026-10,42\n').decode()}
    first=client.call('action',body);assert first[0]==200,first
    case=client.current(case['case_id'])
    assert case['revision']==revision+2 and case['status']=='CHECKING',case.get('checking_error')
    assert not case['evidence_stale'] and not case['checking_error']
    assert case['follow_ups'][-1]['status']=='ANSWERED'
    assert case['data_context']['snapshot_ids']!=original['snapshot_ids']
    assert case['assessment'] is None and case['bank_application'] is None
    assert 'ASSESS' in case['allowed_actions'] and 'ACCEPT_OFFER' not in case['allowed_actions']
    assert client.call('action',body)==first
    assert client.current(case['case_id'])['revision']==revision+2
    case=client.command('ASSESS',case);case=client.command('SUBMIT',case)
    assert case['bank_application']['lender_case_id']!=old_lender


def test_typed_operator_verification_and_allowed_actions_are_current():
    client,bank,case=prepare();case=client.command('REFRESH_EVIDENCE',case)
    assert case['allowed_actions']==client.current(case['case_id'])['allowed_actions']
    q=next(q for q in case['data_context']['questionnaire'] if q['editable'] and q['data_type']=='boolean')
    payload={'kind':'verify','case_id':case['case_id'],'expected_version':case['version'],
             'arguments':{'field_code':q['field_code'],'value':'false','source_ref':'synthetic explicit review'}}
    assert bank.action(payload)[0]==400
    payload['arguments']['value']=False
    assert bank.action(payload)[0]==200
    case=client.current(case['case_id'])
    verified=next(f for f in case['current_data']['questionnaire'] if f['field_code']==q['field_code'])
    assert verified['value'] is False and verified['status']=='VERIFIED'
    case=client.command('ASSESS',case)
    assert 'SUBMIT' in case['allowed_actions'] and case['allowed_actions']==client.current(case['case_id'])['allowed_actions']
    assert 'POLL_STATUS' not in case['allowed_actions']


def test_recovery_is_private_durable_and_replays_the_original_receipt():
    client=Client('client01');other=Client('client02')
    body={'request_id':uuid4().hex,'kind':'command','command':{'request_id':uuid4().hex,'action':'CREATE','expected_version':0}}
    assert client.call('operation',{'operation':'prepare','body':body})[0]==200
    assert any(op['body']==body for op in Client('client01').call('operations')[1])
    assert not any(op['request_id']==body['request_id'] for op in other.call('operations')[1])
    result=client.call('action',body);assert result[0]==200
    assert next(op for op in client.call('operations')[1] if op['request_id']==body['request_id'])['completed']
    assert Client('client01').call('action',body)==result
    changed={**body,'kind':'document'}
    assert client.call('operation',{'operation':'prepare','body':changed})[0]==409
    assert client.call('operation',{'operation':'acknowledge','request_id':body['request_id']})[0]==200
    assert not any(op['request_id']==body['request_id'] for op in client.call('operations')[1])
