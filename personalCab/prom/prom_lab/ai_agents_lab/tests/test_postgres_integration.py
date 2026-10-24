"""Opt-in tests against a seeded, dedicated integration PostgreSQL, never production."""
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from ..agents.workflow import WorkflowApp
from ..database import initialize, import_sqlite
from ..repositories.postgres_config import PostgresConfig
from ..repositories.case_repository import AccessDenied, ConflictError
from ..schemas.models import ActorContext, Consent, Extraction, LoanRequest, MessageInput, Scope, utcnow
from ..services.database_modules import DatabaseModules
from ..services.data_preparation import build_evidence, legal_form


@pytest.fixture
def config():
    url = os.getenv('AURELIUS_TEST_DATABASE_URL')
    if not url:
        pytest.skip('AURELIUS_TEST_DATABASE_URL must point to a dedicated seeded test database')
    cfg = PostgresConfig(conninfo=url)
    initialize(cfg)
    return cfg


class Extractor:
    def extract(self, message, case):
        return Extraction(patch=LoanRequest(legal_form='OOO', purpose='INVENTORY', amount_rub=3000000, term_months=24),
                          evidence={key: message.text for key in ['legal_form','purpose','amount_rub','term_months']})


def identity(config, consent=True):
    with config.connect() as db:
        company = db.execute('SELECT company_id FROM public.companies ORDER BY company_id LIMIT 1').fetchone()['company_id']
    borrower = f'PG-COMPANY-{company}'
    now = utcnow()
    return ActorContext(actor_id='test-'+uuid4().hex, company_id=company, active_borrower_id=borrower,
                        allowed_borrower_ids=[borrower], consents=[Consent(consent_id='test',borrower_id=borrower,
                        scope=Scope.EVIDENCE_COLLECTION,granted_at=now-timedelta(minutes=1),expires_at=now+timedelta(hours=1))] if consent else [])


def command(mid='m1'):
    return MessageInput(session_id='test', message_id=mid, text='Я ООО, нужно 3000000 рублей на товар на 24 месяца.')


def test_postgres_workflow_snapshot_replay_and_isolation(config):
    actor = identity(config)
    with WorkflowApp(config, extractor=Extractor()) as app:
        result = app.handle(command(), actor)
        assert result.error_code is None, result.model_dump()
        assert result.next_action == 'REVIEW_DATA_QUALITY'
        assert result.data_context['features_ready'] is False
        assert result.data_context['snapshot_ids']['R01'] > 0
        replay = app.handle(command(), actor)
        assert replay.model_dump() == result.model_dump()
        foreign = actor.model_copy(update={'company_id': actor.company_id+1})
        with pytest.raises(AccessDenied):
            app.handle(command(), foreign)
        with app.repository.actor_lock(actor.actor_id):
            with pytest.raises(ConflictError):
                with app.repository.actor_lock(actor.actor_id):
                    pass
    with config.connect() as db:
        snapshots = db.execute('SELECT s.snapshot_data FROM public.application_snapshots s WHERE snapshot_id=%s',
                               (result.data_context['snapshot_ids']['R01'],)).fetchone()['snapshot_data']
        assert snapshots['company_id'] == actor.company_id
        assert snapshots['sources']['company']['company_id'] == actor.company_id
        assert snapshots['features']['annual_rate'] is None
    with WorkflowApp(config, extractor=Extractor()) as app:
        repeated = app.handle(command('m2'), actor)
        assert repeated.data_context['snapshot_ids'] == result.data_context['snapshot_ids']
        with config.connect(workflow=True) as db:
            assert db.execute('SELECT count(*) AS n FROM credit_audit WHERE case_id=%s', (result.case_id,)).fetchone()['n'] == 2


def test_postgres_consent_blocks_reads_and_catalog_keeps_16(config):
    actor = identity(config, consent=False)
    with WorkflowApp(config, extractor=Extractor()) as app:
        result = app.handle(command(),actor)
        assert result.error_code == 'CONSENT_REQUIRED'
        assert result.data_context is None
    matcher = DatabaseModules(config).matcher(utcnow())
    assert len(matcher.catalog.products) == 16
    assert sum(card.database_supported for card in matcher.catalog.products) == 3
    assert sum(len(card.requirements) for card in matcher.catalog.products if card.database_supported) >= 99
    assert all(not card.approved for card in matcher.catalog.products if card.database_supported)


def test_legacy_import_idempotent(config, tmp_path):
    from ..repositories.case_repository import CaseRepository
    path = tmp_path/'legacy.sqlite3'
    repository = CaseRepository(path)
    actor = ActorContext(actor_id=uuid4().hex)
    repository.open_session(command(),actor)
    assert import_sqlite(config,path)['credit_cases'] == 1
    assert import_sqlite(config,path)['credit_cases'] == 0


def test_unresolved_legal_entity_is_not_ooo():
    assert legal_form({'entity_type':'LEGAL_ENTITY'}) is None
    assert legal_form({'entity_type':'LEGAL_ENTITY','legal_form':'ООО'}) == 'OOO'


def test_client_field_format_changes_and_operator_queue(config):
    from ..repositories.business_repository import BusinessRepository
    from ..repositories.operator_repository import pending_client_changes,verify_field
    actor=identity(config)
    with WorkflowApp(config,extractor=Extractor()) as app:
        result=app.handle(command(),actor)
        case=app.repository.load(result.case_id,actor)
    with config.connect() as db:
        field=db.execute("SELECT field_code FROM application_field_requirements WHERE product_code='R01' AND target_db_field IN ('companies.inn','public.companies.inn')").fetchone()['field_code']
    repository=BusinessRepository(config)
    answer={'product_code':'R01','field_code':field,'value':'12345678901ABC'}
    with pytest.raises(ValueError):repository.answer_fields(case,actor,[answer])
    assert not [r for r in pending_client_changes(config,case.case_id) if r.get('field_code')==field]

    answer['value']='1234567890'
    repository.answer_fields(case,actor,[answer])
    changes=[r for r in pending_client_changes(config,case.case_id) if r.get('field_code')==field]
    assert len(changes)==1 and changes[0]['new_value']=='1234567890'
    assert changes[0]['old_value']!=changes[0]['new_value']
    repository.answer_fields(case,actor,[answer])
    assert len([r for r in pending_client_changes(config,case.case_id) if r.get('field_code')==field])==1
    answer['value']='letters'
    with pytest.raises(ValueError):repository.answer_fields(case,actor,[answer])
    verify_field(config,case.case_id,'R01',field,{'value':'1234567890','source_ref':'synthetic-test-registry'},'test-reviewer')
    assert not [r for r in pending_client_changes(config,case.case_id) if r.get('field_code')==field]


def test_thirty_client_accounts_are_unique_and_seed_is_non_destructive(config):
    from ..services.client_auth import seed_clients,check_password
    created=seed_clients(config)
    with config.connect(workflow=True) as db:
        rows=db.execute('SELECT * FROM client_accounts ORDER BY client_id').fetchall()
    assert len(rows)==30 and len({r['company_id'] for r in rows})==30
    assert len({r['login'] for r in rows})==30 and all(r['full_name'] for r in rows)
    for record in created:
        row=next(r for r in rows if r['client_id']==record['client_id'])
        assert check_password(record['password'],row['password_hash'])
    assert seed_clients(config)==[]
    with config.connect(workflow=True) as db:
        assert db.execute('SELECT * FROM client_accounts ORDER BY client_id').fetchall()==rows


def test_evidence_never_invents_features_or_uses_future_provenance():
    now=utcnow()
    envelope={'request':{'legal_form':'OOO','amount_rub':100,'term_months':12}, 'decision_at':now.isoformat(),
              'case_id':'test','revision':1,'borrower_id':'test','company_id':40,'result_refs':{}}
    raw={'company':{'company_id':40,'entity_type':'LEGAL_ENTITY','legal_form':'ООО','source_checked_at':now.isoformat()},
         'provenance':[{'target_table':'companies','target_record_pk':{'company_id':40},'verification_status':'VERIFIED',
         'verified_at':(now+timedelta(days=1)).isoformat(),'obtained_at':now.isoformat()}], 'financial_statements':[], 'bank_transactions':[]}
    evidence=build_evidence(envelope,raw)
    assert evidence['verified_facts'] == []
    assert evidence['features']['annual_rate'] is None
    assert evidence['features']['requested_amount'] == 100
    assert evidence['model_readiness'] == 'INSUFFICIENT_DATA'


def test_revision_preserves_old_snapshot_and_blocks_cross_company_write(config):
    from ..repositories.business_repository import BusinessRepository
    actor = identity(config)
    with WorkflowApp(config, extractor=Extractor()) as app:
        original = app.handle(command(),actor)
        app.workflow.extractor = type('ChangedExtractor', (), {'extract': lambda self,message,case:
            Extraction(patch=LoanRequest(amount_rub=5000000), evidence={'amount_rub':message.text})})()
        changed = app.handle(MessageInput(session_id='test',message_id='changed',text='Измени сумму на 5000000 рублей'),actor)
        assert changed.error_code is None, changed.model_dump()
        assert changed.revision == original.revision+1
        assert changed.data_context['snapshot_ids'] != original.data_context['snapshot_ids']
        case = app.repository.load(original.case_id,actor)
        with pytest.raises(ConflictError):
            app.repository.commit(case,case.storage_version-1,command('bad-version'),changed)
    repository=BusinessRepository(config)
    with config.connect() as db:
        old=db.execute('SELECT snapshot_data FROM public.application_snapshots WHERE snapshot_id=%s',
                       (original.data_context['snapshot_ids']['R01'],)).fetchone()['snapshot_data']
        assert old['features']['requested_amount'] == 3000000
    envelope={'case_id':original.case_id,'revision':original.revision,'owner_id':actor.actor_id,
              'borrower_id':actor.active_borrower_id,'company_id':actor.company_id+1,'request':original.request.model_dump()}
    with pytest.raises(AccessDenied):
        repository.save_snapshot(envelope,'R01',old)


def test_verified_postgres_profile_fills_missing_form_with_cutoff(config):
    from psycopg.types.json import Jsonb
    now=utcnow()-timedelta(minutes=1)
    inn='9'+str(int(uuid4().hex[:7],16)).zfill(9)
    with config.connect() as db:
        company=db.execute("INSERT INTO public.companies(entity_type,inn,ogrn,name,legal_form,source_checked_at) VALUES('LEGAL_ENTITY',%s,%s,'Synthetic profile lookup test','ООО',%s) RETURNING company_id",(inn,'1'+inn+'00',now)).fetchone()['company_id']
        for value,at in [('ООО',now),('АО',now+timedelta(days=2))]:
            db.execute("INSERT INTO public.company_data_provenance(company_id,target_table,target_record_pk,target_field,observed_value,source_type,obtained_at,verification_status,verified_at) VALUES(%s,'companies',%s,'legal_form',%s,'FNS',%s,'VERIFIED',%s)", (company,Jsonb({'company_id':company}),Jsonb(value),at,at))
    borrower=f'PG-COMPANY-{company}'
    actor=ActorContext(actor_id='profile-'+uuid4().hex, company_id=company,active_borrower_id=borrower,allowed_borrower_ids=[borrower],
        consents=[Consent(consent_id='test',borrower_id=borrower,scope=Scope.EVIDENCE_COLLECTION,granted_at=now,expires_at=utcnow()+timedelta(hours=1))])
    class WithoutForm:
        def extract(self,message,case):
            return Extraction(patch=LoanRequest(purpose='INVENTORY',amount_rub=3000000,term_months=24),
                              evidence={key:message.text for key in ['purpose','amount_rub','term_months']})
    with WorkflowApp(config,extractor=WithoutForm()) as app:
        result=app.handle(MessageInput(session_id='profile',message_id='m',text='Нужно 3000000 рублей на товар на 24 месяца.'),actor)
        assert result.error_code is None, result.model_dump()
        assert result.request.legal_form == 'OOO'
        assert result.data_resolution.database_lookup == 'FOUND'
        assert result.next_action == 'REVIEW_DATA_QUALITY'
        assert result.data_context['snapshot_ids']['R01'] > 0
        assert any(trace.tool_name=='lookup_business_profile' for trace in result.tool_traces)
