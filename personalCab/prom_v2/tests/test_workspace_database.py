"""Additional opt-in checks inside the isolated V2 database; mutations roll back."""
import os
from uuid import uuid4
import pytest
from personalCab.prom_v2.web_server import Application
from personalCab.prom_v2.repository import Conflict
from personalCab.prom.prom_lab.ai_agents_lab.repositories.postgres_config import PostgresConfig

pytestmark=pytest.mark.skipif(os.getenv('AURELIUS_V2_ATOMIC_TEST')!='1',reason='Explicit isolated V2 DB check')


def test_assigned_reviewer_is_enforced_by_projection_and_execution():
    app=Application(PostgresConfig.from_env())
    account={'login':'client01','role':'BORROWER','company_id':40}
    first={'login':'analyst','role':'OPERATOR','company_id':None}
    second={**first,'login':'reviewer-test-'+uuid4().hex}
    with app.config.connect() as db, db.transaction(force_rollback=True):
        db.execute("INSERT INTO aurelius_agent_v2.accounts(login,password_hash,full_name,role) SELECT %s,password_hash,'Synthetic second reviewer','OPERATOR' FROM aurelius_agent_v2.accounts WHERE login='analyst'",(second['login'],))
        case=app.mutate(account,{'request_id':uuid4().hex,'kind':'command','command':{'request_id':uuid4().hex,'action':'CREATE','expected_version':0}})
        def mutate(who,kind,version):return app.mutate(who,{'request_id':uuid4().hex,'kind':kind,'case_id':case['case_id'],'expected_version':version,'arguments':{}})
        mutate(first,'claim',case['version'])
        current=next(c for c in app.state(second,summary=True)['cases'] if c['case_id']==case['case_id'])
        assert 'claim' not in current['allowed_operations'] and 'authority' not in current['allowed_operations']
        with pytest.raises(Conflict,match='ASSIGNED_TO_ANOTHER_REVIEWER'):
            mutate(second,'claim',current['version'])
        mutate(first,'release',current['version'])
        mutate(second,'claim',current['version']+1)
        saved=db.execute('SELECT payload FROM aurelius_agent_v2.cases WHERE case_id=%s',(case['case_id'],)).fetchone()['payload']
        assert saved['review_owner']==second['login']


def test_profile_resolution_is_trusted_audited_and_preserves_applicant_request():
    app=Application(PostgresConfig.from_env())
    account={'login':'client01','role':'BORROWER','company_id':40}
    operator={'login':'analyst','role':'OPERATOR','company_id':None}
    with app.config.connect() as db, db.transaction(force_rollback=True):
        case=app.mutate(account,{'request_id':uuid4().hex,'kind':'command','command':{'request_id':uuid4().hex,'action':'CREATE','expected_version':0}})
        result=app.mutate(operator,{'request_id':uuid4().hex,'kind':'profile_resolution','case_id':case['case_id'],'expected_version':case['version'],
                                    'arguments':{'legal_form':'IP','source_ref':'Synthetic registry resolution','available_at':'2026-01-01T00:00:00+00:00'}})
        resolution=db.execute('SELECT * FROM aurelius_workflow.profile_resolutions WHERE resolution_id=%s',(result['resolution_id'],)).fetchone()
        assert resolution['company_id']==40 and resolution['reviewed_by']=='analyst'
        current=app.repository.get(app.auth.actor(account),case['case_id'])
        assert current.request.legal_form is None and current.request.amount_rub is None
        event=db.execute('SELECT metadata FROM aurelius_agent_v2.audit WHERE case_id=%s ORDER BY version DESC LIMIT 1',(case['case_id'],)).fetchone()
        assert event['metadata']['source_ref']=='Synthetic registry resolution'
