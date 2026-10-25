"""Transactional adapters for the isolated V2 business database."""
from contextlib import contextmanager
from threading import local
from datetime import timedelta
import hashlib
import json
import secrets

from psycopg.types.json import Jsonb
from personalCab.prom.prom_lab.ai_agents_lab.repositories.postgres_config import PostgresConfig
from personalCab.prom.prom_lab.ai_agents_lab.services.database_modules import DatabaseModules
from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import Case as ServiceCase, ActorContext
from personalCab.prom.prom_lab.ai_agents_lab.services.client_auth import hash_password, check_password, DUMMY_HASH
from .models import Actor, Grant, utcnow
from .repository import AccessDenied


class TransactionConfig:
    """All participating repositories share the outer transaction on this thread."""
    def __init__(self, base):
        self.base, self.context = base, local()

    @contextmanager
    def connect(self, *, workflow=False, **kwargs):
        active = getattr(self.context, 'db', None)
        if active is not None:
            if workflow:
                active.execute('SET LOCAL search_path=aurelius_workflow,public')
            yield active
            return
        with self.base.connect(**kwargs) as db:
            self.context.db = db
            try:
                if workflow:
                    db.execute('SET LOCAL search_path=aurelius_workflow,public')
                yield db
            finally:
                self.context.db = None


def service_case(case):
    refs = {}
    if case.data_context:
        refs['evidence'] = case.data_context['evidence_ref']
    if case.assessment:
        refs['assessment'] = case.assessment['assessment_id']
    if case.bank_application:
        refs['bank_application'] = case.bank_application['lender_case_id']
    return ServiceCase(case_id=case.case_id, owner_id=case.owner_id, company_id=case.company_id,
                       revision=case.revision, request=case.request, result_refs=refs,
                       data_context=case.data_context, assessment=case.assessment,
                       bank_application=case.bank_application, data_cutoff_at=case.data_cutoff_at,
                       client_changes=[{**change,'review_status':change.get('review_status','PENDING')} for change in case.client_changes],
                       status='CANCELLED' if case.status=='CANCELLED' else 'COMPLETED' if case.status in {'DECLINED','EXECUTED_DEMO'} else 'REQUEST_READY')


class BusinessAdapter:
    def __init__(self, config):
        self.config = config
        self.modules = DatabaseModules(config)
        from .assessment import ExplainableAssessmentService
        self.modules.lending.repository.assessment_service=ExplainableAssessmentService()
        class EvidenceConfig:
            @contextmanager
            def connect(self, *, workflow=False, **kwargs):
                # M3 starts a read-only repeatable-read snapshot before its first
                # query. Keep source reads separate; all writes join the outer tx.
                with (config if workflow else config.base).connect(workflow=workflow,**kwargs) as db:
                    yield db
        self.modules.repository.config=EvidenceConfig()

    def supports(self, action):
        return action in {'LOOKUP_PROFILE','REFRESH_EVIDENCE','ASSESS','SUBMIT','POLL_STATUS','ACCEPT_OFFER','EXECUTE_DEMO'}

    def lookup_profile(self, case):
        envelope = dict(case_id=case.case_id, revision=case.revision, company_id=case.company_id,
                        borrower_id=case.borrower_id, decision_at=case.data_cutoff_at.isoformat(),
                        request=case.request.model_dump(mode='json'), result_refs={})
        return self.modules.call('lookup_business_profile', envelope, 'profile:'+case.case_id).data['profile']

    def current_data(self, case):
        """Latest saved answers/files, independent of the immutable evidence snapshot."""
        from personalCab.prom.prom_lab.ai_agents_lab.services.questionnaire import build_questionnaire
        code = {'term':'R01','rcl':'R02','overdraft':'R03'}.get(case.selected_product_id)
        envelope = dict(case_id=case.case_id, revision=case.revision, owner_id=case.owner_id,
                        company_id=case.company_id, decision_at=utcnow().isoformat(),
                        request=case.request.model_dump(mode='json'), client_changes=case.client_changes,
                        product_routes=[{'product_id':case.selected_product_id,'product_code':code}] if code else [])
        fields, values, documents = self.modules.repository.questionnaire_sources(envelope)
        # A projection is not a new source collection. Reuse only already acquired
        # company evidence; before consent/snapshot display saved answers and files.
        snapshot=case.data_context or {}
        company={'source_checked_at':snapshot.get('decision_at')}
        for question in snapshot.get('questionnaire',[]):
            if question.get('source')=='DATABASE' and question.get('target','').startswith('companies.'):
                company[question['target'].split('.',1)[1]]=question['value']
        raw = {'company':company}
        from .workspace import statement_coverage
        from personalCab.prom.prom_lab.ai_agents_lab.services.questionnaire import validate_answer
        questions=build_questionnaire(envelope,raw,fields,values)
        for question in questions:
            reported=values.get((question['product_code'],question['field_code']))
            if reported and reported['field_value']==question['value'] and reported['value_source']==question['source']:
                question['source_ref']=reported['source_reference']
                question['available_at']=reported['obtained_at'].isoformat()
            elif question['source']=='DATABASE':
                question['source_ref']='snapshot:'+str(snapshot.get('snapshot_ids',{}).get(question['product_code']))+':'+question['field_code']
            if question['value'] is not None:
                try:validate_answer(question['value'],question['data_type'],question['target'],case.request.legal_form)
                except (ValueError,TypeError):
                    question['status']='CONFLICT'
                    question['validation_error']='Сохранённое значение не соответствует формату поля и форме бизнеса. Уточните его или предоставьте проверенный источник.'
        return {'questionnaire':questions,
                'documents':[{k:d[k] for k in ('document_id','filename','sha256','uploaded_at')} |
                             {'status':d['extracted_data']['status'],
                              'statement':statement_coverage(d['extracted_data'],utcnow())} for d in documents]}

    def shadow(self, case):
        legacy = service_case(case)
        with self.config.connect(workflow=True) as db:
            db.execute('INSERT INTO credit_cases(case_id,owner_id,borrower_id,status,version,payload) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(case_id) DO UPDATE SET payload=excluded.payload,status=excluded.status,version=excluded.version',
                       (case.case_id,case.owner_id,case.borrower_id,legacy.status.value,case.version,legacy.model_dump_json()))
        return legacy

    def execute(self, actor, case, command):
        legacy = self.shadow(case)
        code = {'term':'R01','rcl':'R02','overdraft':'R03'}[case.selected_product_id]
        envelope = dict(case_id=case.case_id, revision=case.revision, owner_id=case.owner_id,
                        borrower_id=case.borrower_id, company_id=case.company_id,
                        decision_at=case.data_cutoff_at.isoformat(), request=case.request.model_dump(mode='json'),
                        verified_facts=[], result_refs=legacy.result_refs, data_context=case.data_context,
                        assessment=case.assessment, client_changes=legacy.client_changes)
        result = {key:envelope[key] for key in ('case_id','revision','company_id','borrower_id')}
        if command.action == 'REFRESH_EVIDENCE':
            envelope['product_routes']=[{'product_id':case.selected_product_id,'product_code':code}]
            snapshot = self.modules.preparation.collect(envelope)
            snapshot['evidence_ref'] = 'v2-evidence:'+case.case_id+':'+str(case.revision)+':'+str(snapshot['snapshot_ids'])
            result.update(data_context=snapshot,status='DRAFT',message='Снимок и адресная анкета сохранены. Данные клиента остаются непроверенными.')
        else:
            operation = {'ASSESS':'run_assessment','SUBMIT':'submit_application','POLL_STATUS':'get_bank_status',
                         'ACCEPT_OFFER':'accept_offer','EXECUTE_DEMO':'execute_demo'}[command.action]
            arguments = {**command.arguments,'product_code':code}
            value = getattr(self.modules.lending,operation)(envelope,arguments)
            field = 'assessment' if command.action=='ASSESS' else 'bank_application'
            status = case.status if field=='assessment' else {'REQUEST_DATA':'NEEDS_INFO'}.get(value['status'],value['status'])
            result.update({field:value},status=status,message='Оценка: '+value['status'] if field=='assessment' else 'Рассмотрение DEMO: '+value['status'])
        return result


class DatabaseProducts:
    """M2 uses the existing approval/time contract and keeps all 16 directions."""
    def __init__(self, business):
        self.business = business

    def select(self, case):
        matcher = self.business.modules.matcher(case.data_cutoff_at, case.request.legal_form)
        facts = (case.business_profile or {}).get('verified_facts', [])
        return matcher.select(case.case_id, case.revision, case.request, facts, now=case.data_cutoff_at)


class Auth:
    def __init__(self, config):
        self.config = config

    def seed(self):
        with self.config.connect() as db:
            rows=db.execute('SELECT company_id,name FROM public.companies WHERE name IS NOT NULL AND company_id>=40 ORDER BY company_id LIMIT 2').fetchall()
            for index,row in enumerate(rows,1):
                db.execute('INSERT INTO aurelius_agent_v2.accounts(login,password_hash,full_name,role,company_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(login) DO NOTHING',
                           (f'client{index:02}',hash_password('Aurelius2026!'),row['name'],'BORROWER',row['company_id']))
            db.execute("INSERT INTO aurelius_agent_v2.accounts(login,password_hash,full_name,role,company_id) VALUES('analyst',%s,'Анна Смирнова','OPERATOR',NULL) ON CONFLICT(login) DO NOTHING",(hash_password('Aurelius2026!'),))

    def login(self, login, password, address):
        with self.config.connect() as db:
            db.execute("DELETE FROM aurelius_agent_v2.login_attempts WHERE created_at < now()-interval '1 minute'")
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('v2-login:'+address,))
            count=db.execute('SELECT count(*) AS n FROM aurelius_agent_v2.login_attempts WHERE address=%s',(address,)).fetchone()['n']
            if count>=10:
                return None
            db.execute('INSERT INTO aurelius_agent_v2.login_attempts(address) VALUES(%s)',(address,))
            account=db.execute('SELECT * FROM aurelius_agent_v2.accounts WHERE login=%s',(login.strip().casefold(),)).fetchone()
            valid=check_password(password,account['password_hash'] if account else DUMMY_HASH)
            if not valid or not account or not account['active']:
                return None
            token=secrets.token_urlsafe(32)
            db.execute("INSERT INTO aurelius_agent_v2.sessions(token_hash,login,expires_at) VALUES(%s,%s,now()+interval '8 hours')",(hashlib.sha256(token.encode()).hexdigest(),account['login']))
            return token

    def session(self, token):
        with self.config.connect() as db:
            account=db.execute('SELECT a.login,a.full_name,a.role,a.company_id FROM aurelius_agent_v2.sessions s JOIN aurelius_agent_v2.accounts a USING(login) WHERE token_hash=%s AND expires_at>now() AND a.active',
                               (hashlib.sha256((token or '').encode()).hexdigest(),)).fetchone()
            if not account: raise AccessDenied('LOGIN_REQUIRED')
            return account

    def actor(self, account):
        if account['role']!='BORROWER': raise AccessDenied('BORROWER_REQUIRED')
        with self.config.connect() as db:
            rows=db.execute('SELECT scope,granted_at,expires_at,revoked FROM aurelius_agent_v2.grants WHERE login=%s',(account['login'],)).fetchall()
        return Actor(actor_id='v2-'+account['login'],company_id=account['company_id'],borrower_id='company-'+str(account['company_id']),
                     grants=[Grant(**row) for row in rows])

    def logout(self, token):
        with self.config.connect() as db:
            db.execute('DELETE FROM aurelius_agent_v2.sessions WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))
