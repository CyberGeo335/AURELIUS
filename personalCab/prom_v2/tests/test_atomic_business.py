"""Run explicitly inside the isolated V2 deployment; never against V1."""
import os
from datetime import timedelta
from uuid import uuid4
import pytest
from personalCab.prom_v2.models import Actor,Grant,Command,utcnow
from personalCab.prom_v2.web_server import Application
from personalCab.prom.prom_lab.ai_agents_lab.repositories.postgres_config import PostgresConfig


@pytest.mark.skipif(os.getenv('AURELIUS_V2_ATOMIC_TEST')!='1',reason='Explicit isolated V2 DB check')
def test_business_write_rolls_back_with_invalid_module_output():
    app=Application(PostgresConfig.from_env())
    actor=Actor(actor_id='atomic-'+uuid4().hex,company_id=40,borrower_id='company-40',
                grants=[Grant(scope='EVIDENCE_COLLECTION',granted_at=utcnow()-timedelta(seconds=1),expires_at=utcnow()+timedelta(hours=1))])
    def command(action,case=None,arguments=None):
        return app.agent.handle(actor,Command(action=action,request_id=uuid4().hex,case_id=case.case_id if case else None,expected_version=case.version if case else 0,arguments=arguments or {}))
    case=command('CREATE')
    case=command('UPDATE_REQUEST',case,{'patch':{'legal_form':'IP','amount_rub':1500000,'term_months':12,'purpose':'INVENTORY'}})
    case=command('SELECT_PRODUCT',case,{'product_id':'term'})
    real=app.business.execute
    def invalid(*args):
        result=real(*args)
        result['case_id']='different-case'
        return result
    app.business.execute=invalid
    with pytest.raises(ValueError,match='scope mismatch'):
        command('REFRESH_EVIDENCE',case)
    assert app.agent.state(actor,case.case_id).version==case.version
    with app.config.connect() as db:
        assert db.execute('SELECT count(*) AS n FROM aurelius_workflow.credit_cases WHERE case_id=%s',(case.case_id,)).fetchone()['n']==0
        assert db.execute('SELECT count(*) AS n FROM aurelius_workflow.case_applications WHERE case_id=%s',(case.case_id,)).fetchone()['n']==0


@pytest.mark.skipif(os.getenv('AURELIUS_V2_ATOMIC_TEST')!='1',reason='Explicit isolated V2 DB check')
def test_saved_reply_survives_source_failure_and_partial_snapshot_is_rolled_back():
    from psycopg.types.json import Jsonb
    from personalCab.prom_v2.models import Case, FollowUp
    app=Application(PostgresConfig.from_env())
    account={'login':'client01','role':'BORROWER','company_id':40}
    def action(body):return app.mutate(account,{'request_id':uuid4().hex,**body})
    def command(name,view=None,arguments=None):
        cmd={'action':name,'request_id':uuid4().hex,'expected_version':view['version'] if view else 0,'arguments':arguments or {}}
        if view:cmd['case_id']=view['case_id']
        return action({'kind':'command','command':cmd})
    action({'kind':'consent','scope':'EVIDENCE_COLLECTION','granted':True})
    view=command('CREATE')
    view=command('UPDATE_REQUEST',view,{'patch':{'legal_form':'IP','amount_rub':1500000,'term_months':12,'purpose':'INVENTORY'}})
    view=command('SELECT_PRODUCT',view,{'product_id':'term'})
    view=command('REFRESH_EVIDENCE',view)
    case=app.repository.get(app.auth.actor(account),view['case_id'])
    field=next(q for q in case.data_context['questionnaire'] if q['editable'] and q['data_type']=='text' and q['value'] is None)
    case.follow_ups=[FollowUp(fields=[field['field_code']],reason='Synthetic source failure test')]
    with app.config.connect() as db:
        db.execute('UPDATE aurelius_agent_v2.cases SET payload=%s WHERE case_id=%s',(Jsonb(case.model_dump(mode='json')),case.case_id))
    real=app.business.modules.preparation.collect
    def failing(envelope):
        real(envelope)
        raise RuntimeError('Synthetic source failure after snapshot writes')
    app.business.modules.preparation.collect=failing
    action({'kind':'fields','case_id':case.case_id,'expected_version':case.version,'answers':[
        {'product_code':field['product_code'],'field_code':field['field_code'],'value':'Durable reply despite source failure'}]})
    case=app.repository.get(app.auth.actor(account),case.case_id)
    assert case.status=='CHECKING' and case.evidence_stale and case.checking_error
    assert app.business.current_data(case)['questionnaire'][next(i for i,q in enumerate(case.data_context['questionnaire']) if q['field_code']==field['field_code'])]['value']=='Durable reply despite source failure'
    with app.config.connect() as db:
        assert db.execute('SELECT count(*) AS n FROM aurelius_workflow.case_applications WHERE case_id=%s',(case.case_id,)).fetchone()['n']==1
    app.business.modules.preparation.collect=real
    refreshed=command('REFRESH_EVIDENCE',case.model_dump(mode='json'))
    assert refreshed['status']=='CHECKING' and not refreshed['evidence_stale'] and not refreshed['checking_error']
