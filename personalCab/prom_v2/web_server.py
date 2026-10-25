"""Session-based V2 WEB/API, isolated database, atomic business adapters."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from datetime import timedelta
import argparse
import json
import os
import hashlib

from psycopg.types.json import Jsonb
from pydantic import ValidationError
from personalCab.prom.prom_lab.ai_agents_lab.repositories.postgres_config import PostgresConfig
from personalCab.prom.prom_lab.ai_agents_lab.repositories.case_repository import ConflictError, AccessDenied as ServiceDenied
from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import ActorContext
from personalCab.prom.prom_lab.ai_agents_lab.repositories.cabinet_repository import CabinetRepository
from .adapters import OllamaExtraction
from .agent import Agent
from .models import Actor, Command, Scope, FollowUp, utcnow
from .operations import Operations
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4
from .repository import PostgresRepository, AccessDenied, Conflict
from .integration import TransactionConfig, BusinessAdapter, DatabaseProducts, Auth, service_case
from .workspace import audit_metadata, preview_decision
from . import operator


class Application:
    def __init__(self, config, *, extractor=None):
        self.config=TransactionConfig(config)
        with self.config.connect() as db:
            if db.execute('SELECT current_database() AS name').fetchone()['name']!='aurelius_v2':
                raise ValueError('Integrated V2 requires its dedicated aurelius_v2 database; V1 is never modified')
        self.repository=PostgresRepository(self.config)
        self.business=BusinessAdapter(self.config)
        self.agent=Agent(self.repository,extractor=extractor,modules=self.business,products=DatabaseProducts(self.business))
        self.auth=Auth(self.config)
        self.operations=Operations(self.config)

    def initialize(self, seed=False):
        self.repository.initialize()
        with self.config.connect() as db:
            root=Path(__file__).resolve().parents[2]
            for path in sorted(root.joinpath('scoring/bd/migrations').glob('*.sql')):
                db.execute(path.read_text(),prepare=False)
            db.execute(Path(__file__).with_name('migrations').joinpath('002_sessions.sql').read_text(),prepare=False)
            db.execute(Path(__file__).with_name('migrations').joinpath('003_operations.sql').read_text(),prepare=False)
            db.execute("UPDATE public.application_field_requirements SET target_db_field='credit_applications.requested_term_months' WHERE field_code IN ('R01_06','R02_06','R03_06')")
        if seed:self.auth.seed()

    def state(self, account, *, detail=None, summary=False):
        # Share one connection across projections; avoid one new connection per field/case.
        with self.config.connect():
            return self._state(account,detail=detail,summary=summary)

    def _state(self, account, *, detail=None, summary=False):
        borrower=self.auth.actor(account) if account['role']=='BORROWER' else None
        if account['role']=='OPERATOR':
            with self.config.connect() as db:
                from .models import Case
                cases=[Case.model_validate(row['payload']) for row in db.execute('SELECT payload FROM aurelius_agent_v2.cases ORDER BY case_id').fetchall()]
        else: cases=self.repository.list(borrower)
        with self.config.connect() as db:
            companies=db.execute('SELECT company_id,name,entity_type,inn FROM public.companies WHERE (%s::bigint IS NULL OR company_id=%s) ORDER BY company_id',
                                 (account['company_id'],account['company_id'])).fetchall()
            pending_cases={r['case_id'] for r in db.execute("SELECT DISTINCT ch.case_id FROM aurelius_workflow.client_field_changes ch JOIN aurelius_agent_v2.cases c ON c.case_id=ch.case_id WHERE ch.review_status='PENDING' AND (%s OR (c.owner_id=%s AND c.company_id=%s))",(account['role']=='OPERATOR','v2-'+account['login'],account['company_id'])).fetchall()}
        views=[]
        for case in cases:
            self.legacy_follow_up(case)
            actor=borrower if borrower else Actor(actor_id=case.owner_id,company_id=case.company_id,borrower_id=case.borrower_id,role='OPERATOR')
            view=self.agent._view(actor,case,self.agent._question(case)).model_dump(mode='json')
            expanded=not summary or case.case_id==detail
            view['current_data']=self.business.current_data(case) if expanded else None
            view['allowed_operations']=[kind for kind in ('fields','document','payment','verify','features','review','claim','release','authority','profile_resolution','review_changes') if self.operation_denial(account,case,kind,actor=borrower) is None]
            view['client_changes']=case.client_changes
            view['has_pending_changes']=case.case_id in pending_cases or any(c.get('review_status','PENDING')=='PENDING' for c in case.client_changes)
            if account['role']=='OPERATOR' and expanded:
                view['field_changes']=db.execute("SELECT change_id,field_code,old_value,new_value,review_status,source_ref FROM aurelius_workflow.client_field_changes WHERE case_id=%s ORDER BY change_id",(case.case_id,)).fetchall()
            # Financial source rows are private evidence, never the general UI log.
            if view['data_context']: view['data_context'].pop('sources',None)
            if not expanded:
                for field in ('data_context','assessment','bank_application','product_selection','pending','last_knowledge_answer'):
                    if field!='assessment':view[field]=None
                view['history']=[]
                view['offer_history']=[]
            views.append(view)
        return {'cases':views,'companies':companies,'session':account,
                'scopes':[s.value for s in Scope],
                'grants':[g.model_dump(mode='json') for g in borrower.grants] if borrower else []}

    def catalog(self):
        matcher=self.business.modules.matcher(utcnow())
        # A public catalog must not use request routing: an empty request has no
        # intent and legitimately produces zero matched candidates.
        selection={'catalog_version':matcher.catalog.version,'candidates':[
            {**card.model_dump(mode='json'),'eligibility':'UNKNOWN','priority':index,
             'reasons':['Для подбора заполните запрос. Это карточка каталога, не результат проверки.'],
             'checks':[],'missing_checks':['REQUEST_REQUIRED']}
            for index,card in enumerate(matcher.catalog.products)]}
        service=self.business.modules.lending.repository.assessment_service
        selection['model_registry']={'version':service.registry['version'],'available':not service.registry_error,
                                     'models':[{k:v for k,v in m.items() if k!='path'} for m in service.registry['models']]}
        return selection

    def audit(self, account, case_id=None, cursor=None):
        if cursor is not None and (not str(cursor).isdigit() or int(cursor)<1):raise ValueError('Invalid audit cursor')
        with self.config.connect() as db:
            if case_id:
                if account['role']=='BORROWER':self.repository.get(self.auth.actor(account),case_id)
                elif not db.execute('SELECT 1 FROM aurelius_agent_v2.cases WHERE case_id=%s',(case_id,)).fetchone():raise AccessDenied('CASE_NOT_ACCESSIBLE')
            rows=db.execute('SELECT a.* FROM aurelius_agent_v2.audit a JOIN aurelius_agent_v2.cases c USING(case_id) WHERE (%s::text IS NULL OR a.case_id=%s) AND (%s::bigint IS NULL OR a.id<%s) AND (%s OR (c.owner_id=%s AND c.company_id=%s)) ORDER BY a.id DESC LIMIT 201',
                            (case_id,case_id,cursor,cursor,account['role']=='OPERATOR','v2-'+account['login'],account['company_id'])).fetchall()
            security=db.execute('SELECT * FROM aurelius_agent_v2.security_audit WHERE (%s OR (actor_id=%s AND company_id=%s)) ORDER BY id DESC LIMIT 100',
                                (account['role']=='OPERATOR','v2-'+account['login'],account['company_id'])).fetchall()
        return {'events':rows[:200],'next_cursor':str(rows[199]['id']) if len(rows)>200 else None,'consent_events':security}

    def review_preview(self, account, body):
        if account['role']!='OPERATOR':raise AccessDenied('OPERATOR_REQUIRED')
        from .models import Case
        with self.config.connect() as db:
            row=db.execute('SELECT payload FROM aurelius_agent_v2.cases WHERE case_id=%s',(body['case_id'],)).fetchone()
            if not row:raise AccessDenied('CASE_NOT_ACCESSIBLE')
            case=Case.model_validate(row['payload'])
            if type(body['expected_version']) is not int or case.version!=body['expected_version']:raise Conflict('STALE_CASE_VERSION')
            denial=self.operation_denial(account,case,'review')
            if denial:raise Conflict(denial)
            if body['arguments'].get('decision')=='REQUEST_DATA':
                request=operator.follow_up(self.business,case,body['arguments'])
                if not (request.fields or request.documents) or not request.due_at:raise ValueError('Addressed request and deadline required')
            return preview_decision(case,body['arguments'])

    def owner_actor(self, case):
        with self.config.connect() as db:
            account=db.execute("SELECT login,role,company_id FROM aurelius_agent_v2.accounts WHERE 'v2-'||login=%s AND company_id=%s AND active",(case.owner_id,case.company_id)).fetchone()
        return self.auth.actor(account) if account else Actor(actor_id=case.owner_id,company_id=case.company_id,borrower_id=case.borrower_id)

    @staticmethod
    def legacy_follow_up(case):
        if (case.bank_application or {}).get('status')=='REQUEST_DATA' and not any(r.status=='OPEN' for r in case.follow_ups):
            case.follow_ups.append(FollowUp(reason='; '.join(case.bank_application.get('review_reasons',[])) or 'Нужны дополнительные сведения.'))

    def operation_denial(self, account, case, kind, *, actor=None):
        if account['role']=='OPERATOR':
            if kind=='claim':return None if case.review_owner in {None,account['login']} else 'ASSIGNED_TO_ANOTHER_REVIEWER'
            if kind=='release':return None if case.review_owner==account['login'] else 'NOT_ASSIGNED_TO_YOU'
            if case.review_owner not in {None,account['login']}:return 'ASSIGNED_TO_ANOTHER_REVIEWER'
            if kind not in {'verify','features','review','authority','profile_resolution','review_changes'}: return 'OPERATOR_ACTION_REQUIRED'
            if case.status in {'CANCELLED','DECLINED','ACCEPTED','EXECUTED_DEMO'}: return 'CASE_CLOSED'
            if kind in {'authority','profile_resolution'}:return None
            if case.evidence_stale or not case.data_context: return 'EVIDENCE_REFRESH_REQUIRED'
            if kind=='review' and (case.bank_application or {}).get('status') not in {'MANUAL_REVIEW','REQUEST_DATA'}: return 'SUBMISSION_REQUIRED'
            if kind in {'features','verify'} and case.status=='OFFERED': return 'CASE_ALREADY_REVIEWED'
            return None
        if kind not in {'fields','document','payment'}: return 'BORROWER_ACTION_NOT_ALLOWED'
        actor=actor or self.auth.actor(account)
        if kind=='payment':
            offer=(case.bank_application or {}).get('offer') or {}
            if case.status!='EXECUTED_DEMO' or offer.get('repayment_type')!='ANNUITY' or any(float(f)!=0 for f in offer.get('fees_rub',[])): return 'PAYMENT_NOT_AVAILABLE'
            return None if actor.permits(Scope.DEMO_EXECUTION,utcnow()) else 'CONSENT_REQUIRED'
        if case.status in {'CANCELLED','DECLINED','EXECUTED_DEMO','ACCEPTED'}: return 'CASE_CLOSED'
        if not actor.permits(Scope.EVIDENCE_COLLECTION,utcnow()): return 'CONSENT_REQUIRED'
        if kind=='fields' and not case.data_context: return 'EVIDENCE_REQUIRED'
        return None

    @staticmethod
    def record_reply(case, fields=(), filename=None):
        progressed=False
        for request in case.follow_ups:
            if request.status!='OPEN': continue
            matched=set(fields)&set(request.fields)
            documents={filename} & set(request.documents) if filename else set()
            before=(set(request.answered_fields),set(request.answered_documents))
            request.answered_fields=sorted(set(request.answered_fields)|matched)
            request.answered_documents=sorted(set(request.answered_documents)|documents)
            if (set(request.fields)<=set(request.answered_fields) and set(request.documents)<=set(request.answered_documents)
                    and (request.fields or request.documents or fields or filename)):
                request.status='ANSWERED'
                progressed=True
            progressed |= before!=(set(request.answered_fields),set(request.answered_documents))
        return progressed

    def refresh_reply(self, case):
        """A source failure must not discard the customer's already saved reply."""
        candidate=case.model_copy(deep=True)
        candidate.status='CHECKING'
        try:
            with self.config.connect() as db, db.transaction():
                _,error=self.agent._business(self.owner_actor(case),candidate,Command(request_id=uuid4().hex,case_id=case.case_id,expected_version=case.version,action='REFRESH_EVIDENCE'))
                if error: raise ValueError(error)
            candidate.status='NEEDS_INFO' if any(r.status=='OPEN' for r in candidate.follow_ups) else 'CHECKING'
            return candidate
        except Exception:
            case.status='CHECKING'
            case.checking_error='Данные пока недоступны или требуется действующее разрешение. Повторите обновление.'
            return case

    def mutate(self, account, body):
        if not isinstance(body,dict) or not isinstance(body.get('request_id'),str) or not 1<=len(body['request_id'])<=120:
            raise ValueError('request_id required')
        digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
        with self.config.connect() as db:
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('agent-v2:v2-'+account['login'],))
            receipt=db.execute('SELECT input_hash,result FROM aurelius_agent_v2.action_receipts WHERE login=%s AND request_id=%s',(account['login'],body['request_id'])).fetchone()
            if receipt:
                if receipt['input_hash']!=digest:raise Conflict('REQUEST_ID_REUSED')
                return receipt['result']
            result=self._mutate(account,body)
            db.execute('INSERT INTO aurelius_agent_v2.action_receipts(login,request_id,input_hash,result) VALUES(%s,%s,%s,%s)',(account['login'],body['request_id'],digest,Jsonb(result)))
            return result

    def _mutate(self, account, body):
        with self.config.connect() as db:
            actor_id='v2-'+account['login']
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('agent-v2:'+actor_id,))
            kind=body.get('kind','command')
            if kind=='consent':
                actor=self.auth.actor(account)
                scope=Scope(body['scope'])
                if type(body['granted']) is not bool: raise ValueError('Explicit boolean required')
                db.execute('INSERT INTO aurelius_agent_v2.grants(login,scope,granted_at,expires_at,revoked) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(login,scope) DO UPDATE SET granted_at=excluded.granted_at,expires_at=excluded.expires_at,revoked=excluded.revoked',
                           (account['login'],scope.value,utcnow(),utcnow()+timedelta(hours=1),not body['granted']))
                db.execute('INSERT INTO aurelius_agent_v2.security_audit(actor_id,company_id,action,scope) VALUES(%s,%s,%s,%s)',(actor_id,account['company_id'],'GRANT' if body['granted'] else 'REVOKE',scope.value))
                return {'saved':True}
            if kind=='command':
                return self.agent.handle(self.auth.actor(account),Command.model_validate(body['command'])).model_dump(mode='json')
            case_id=body['case_id']
            if type(body.get('expected_version')) is not int:raise ValueError('Integer version required')
            if account['role']=='OPERATOR':
                row=db.execute('SELECT payload FROM aurelius_agent_v2.cases WHERE case_id=%s',(case_id,)).fetchone()
                if not row: raise AccessDenied('CASE_NOT_ACCESSIBLE')
                from .models import Case
                case=Case.model_validate(row['payload'])
                # Serialize with the borrower's commands, not just the reviewer's login.
                db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('agent-v2:'+case.owner_id,))
                case=Case.model_validate(db.execute('SELECT payload FROM aurelius_agent_v2.cases WHERE case_id=%s FOR UPDATE',(case_id,)).fetchone()['payload'])
                if case.version!=body['expected_version']:raise Conflict('STALE_CASE_VERSION')
                denial=self.operation_denial(account,case,kind)
                if denial: raise Conflict(denial)
                result=operator.execute(self.config,self.business,account,case,kind,body['arguments'])
                if kind=='review':case.bank_application=result;case.status={'REQUEST_DATA':'NEEDS_INFO'}.get(result['status'],result['status'])
                elif kind=='verify':
                    self.agent.evidence_changed(case)
                    case=self.refresh_reply(case)
                elif kind=='features':
                    case.assessment=case.bank_application=None
                    case.status='CHECKING'
                elif kind=='profile_resolution':
                    case.business_profile=None
                    case.profile_lookup_status='NOT_NEEDED'
                    if case.data_context:
                        self.agent.evidence_changed(case)
                    else:
                        self.agent._invalidate(case)
            else:
                actor=self.auth.actor(account)
                case=self.repository.get(actor,case_id)
                if case.version!=body['expected_version']:raise Conflict('STALE_CASE_VERSION')
                self.legacy_follow_up(case)
                denial=self.operation_denial(account,case,kind)
                if denial:
                    if denial in {'CONSENT_REQUIRED','BORROWER_ACTION_NOT_ALLOWED'}:raise AccessDenied(denial)
                    raise Conflict(denial)
                if case.status in {'CANCELLED','DECLINED','EXECUTED_DEMO','ACCEPTED'} and kind!='payment':raise Conflict('CASE_CLOSED')
                if not actor.permits(Scope.DEMO_EXECUTION if kind=='payment' else Scope.EVIDENCE_COLLECTION,utcnow()):raise AccessDenied('CONSENT_REQUIRED')
                legacy=self.business.shadow(case)
                context=ActorContext(actor_id=actor.actor_id,company_id=actor.company_id,active_borrower_id=actor.borrower_id,allowed_borrower_ids=[actor.borrower_id])
                from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import Consent, Scope as OldScope
                context.consents=[Consent(consent_id='v2',borrower_id=actor.borrower_id,scope=OldScope(scope.scope.value),granted_at=scope.granted_at,expires_at=scope.expires_at) for scope in actor.grants if not scope.revoked]
                if kind=='fields':
                    def field_values():
                        return db.execute(
                            'SELECT DISTINCT ON(v.field_code) v.field_code,v.field_value,v.verification_status FROM public.application_field_values v '
                            'JOIN aurelius_workflow.case_applications c USING(application_id) '
                            'WHERE c.case_id=%s AND c.revision<=%s ORDER BY v.field_code,c.revision DESC',
                            (case.case_id,case.revision),
                        ).fetchall()
                    before = field_values()
                    editable={q['field_code']:q for q in self.business.current_data(case)['questionnaire'] if q['editable']}
                    for answer in body['answers']:
                        if answer.get('field_code') not in editable or answer.get('product_code')!=editable[answer['field_code']]['product_code']:
                            raise AccessDenied('QUESTIONNAIRE_FIELD_NOT_IN_SCOPE')
                        link=db.execute('SELECT revision FROM aurelius_workflow.case_applications WHERE case_id=%s AND product_code=%s AND revision<=%s ORDER BY revision DESC LIMIT 1',(case.case_id,answer['product_code'],case.revision)).fetchone()
                        self.business.modules.repository.answer_fields(legacy.model_copy(update={'revision':link['revision']}),context,[answer])
                    evidence_changed = before != field_values()
                    replied=self.record_reply(case,fields=[a['field_code'] for a in body['answers']])
                elif kind=='document':
                    # Cabinet upload repeats the trusted grant check using V1's value contract.
                    cabinet = CabinetRepository(type('Repo',(),{'config':self.config})(),set())
                    before = cabinet.documents(legacy,context)
                    evidence_changed = before != cabinet.upload(legacy,context,body['filename'],body['content_base64'])
                    replied=self.record_reply(case,filename=body['filename'])
                elif kind=='payment':
                    case.bank_application=self.business.modules.lending.record_demo_payment(legacy,context,body['operation_id'],body['amount_rub'])
                else:raise AccessDenied('BORROWER_ACTION_NOT_ALLOWED')
                result={'saved':True}
                if kind!='payment' and (evidence_changed or replied):
                    self.agent.evidence_changed(case)
                    if case.follow_ups and not any(r.status=='OPEN' for r in case.follow_ups):
                        case=self.refresh_reply(case)
            case.version+=1
            db.execute('UPDATE aurelius_agent_v2.cases SET payload=%s,version=%s WHERE case_id=%s',(Jsonb(case.model_dump(mode='json')),case.version,case.case_id))
            self.business.shadow(case)
            db.execute('INSERT INTO aurelius_agent_v2.audit(case_id,version,revision,actor_id,action) VALUES(%s,%s,%s,%s,%s)',(case.case_id,case.version,case.revision,actor_id,kind))
            metadata=audit_metadata(case)
            if kind in {'review','authority','profile_resolution','verify','review_changes'}:
                args=body.get('arguments',{})
                metadata.update({k:args[k] for k in ('decision','reason','source_ref','field_code','fields') if k in args})
            db.execute('UPDATE aurelius_agent_v2.audit SET metadata=%s WHERE case_id=%s AND version=%s',(Jsonb(metadata),case.case_id,case.version))
            return result


def public_origin(server_port, configured=None):
    origin=configured or os.getenv('V2_PUBLIC_ORIGIN') or f'http://127.0.0.1:{server_port}'
    parsed=urlsplit(origin)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment:
        raise ValueError('V2_PUBLIC_ORIGIN must be a complete http(s) origin')
    # Accessing port also validates its numeric range.
    port=parsed.port
    return parsed.scheme, parsed.hostname, port or (443 if parsed.scheme=='https' else 80)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,app,root,**kwargs):
        self.app=app;self.root=Path(root).resolve()
        super().__init__(*args,directory=str(self.root),**kwargs)
    def log_message(self,*args):return
    def respond(self,status,data,cookie=None):
        payload=json.dumps(data,ensure_ascii=False,default=str).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if cookie is not None:self.send_header('Set-Cookie',f'aurelius_v2={cookie}; HttpOnly; SameSite=Strict; Path=/api/v2; Max-Age={28800 if cookie else 0}')
        self.end_headers()
        try:self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError):return
    def token(self):
        cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''));item=cookie.get('aurelius_v2');return item.value if item else ''
    def local_origin(self):
        host=self.headers.get('Host','')
        scheme,hostname,port=public_origin(self.server.server_port)
        hosts={hostname}
        if hostname in {'127.0.0.1','localhost'}:hosts={'127.0.0.1','localhost'}
        allowed={f'{name}:{port}' for name in hosts}
        if port==(443 if scheme=='https' else 80):allowed|=hosts
        return host in allowed and self.headers.get('Origin') in {None,scheme+'://'+host}
    def do_GET(self):
        if not self.local_origin():return self.respond(403,{'error':'LOCAL_ORIGIN_REQUIRED'})
        path=self.path.split('?')[0]
        if path.startswith('/api/'):
            try:
                account=self.app.auth.session(self.token())
                if path=='/api/v2/session':return self.respond(200,account)
                if path=='/api/v2/state':
                    query=parse_qs(urlsplit(self.path).query)
                    return self.respond(200,self.app.state(account,summary=query.get('summary')==['1'],detail=query.get('detail',[None])[0]))
                if path=='/api/v2/operations':return self.respond(200,self.app.operations.pending(account))
                if path=='/api/v2/catalog':return self.respond(200,self.app.catalog())
                if path=='/api/v2/audit':
                    query=parse_qs(urlsplit(self.path).query)
                    return self.respond(200,self.app.audit(account,query.get('case_id',[None])[0],query.get('cursor',[None])[0]))
                return self.respond(404,{'error':'NOT_FOUND'})
            except AccessDenied as exc:return self.respond(401 if str(exc)=='LOGIN_REQUIRED' else 403,{'error':str(exc)})
            except ValueError:return self.respond(400,{'error':'INVALID_QUERY'})
            except Exception:return self.respond(503,{'error':'STORAGE_UNAVAILABLE'})
        requested=Path(self.translate_path(path)).resolve()
        if not requested.is_relative_to(self.root):return self.send_error(404)
        if not requested.is_file():self.path='/index.html'
        super().do_GET()
    def do_POST(self):
        if not self.local_origin():return self.respond(403,{'error':'LOCAL_ORIGIN_REQUIRED'})
        if self.path not in {'/api/v2/login','/api/v2/logout','/api/v2/action','/api/v2/operation','/api/v2/review-preview'}:return self.respond(404,{'error':'NOT_FOUND'})
        if self.headers.get_content_type()!='application/json':return self.respond(415,{'error':'JSON_REQUIRED'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=29*1024*1024:return self.respond(413,{'error':'BODY_TOO_LARGE'})
            body=json.loads(self.rfile.read(length))
            if self.path=='/api/v2/login':
                if set(body)!={'login','password'} or not all(isinstance(v,str) and len(v)<=256 for v in body.values()):raise ValueError()
                token=self.app.auth.login(body['login'],body['password'],self.client_address[0])
                return self.respond(200,{'authenticated':True},token) if token else self.respond(401,{'error':'INVALID_CREDENTIALS_OR_RATE_LIMIT'})
            account=self.app.auth.session(self.token())
            if self.path=='/api/v2/review-preview':return self.respond(200,self.app.review_preview(account,body))
            if self.path=='/api/v2/operation':
                if body.get('operation')=='prepare':return self.respond(200,self.app.operations.prepare(account,body['body']))
                if body.get('operation')=='acknowledge':return self.respond(200,self.app.operations.acknowledge(account,body['request_id']))
                raise ValueError('Unknown recovery operation')
            if self.path=='/api/v2/logout':self.app.auth.logout(self.token());return self.respond(200,{'authenticated':False},'')
            return self.respond(200,self.app.mutate(account,body))
        except (AccessDenied,ServiceDenied):return self.respond(403,{'error':'ACCESS_DENIED'})
        except (Conflict,ConflictError) as exc:
            code = 'STALE_CASE_VERSION' if str(exc)=='STALE_CASE_VERSION' else 'ACTION_CONFLICT'
            return self.respond(409,{'error':'STALE_OR_CONFLICT','code':code,'message':'Заявка изменилась. Сверьте актуальные данные перед повторным действием.'})
        except (ValueError,KeyError,TypeError,ValidationError):return self.respond(400,{'error':'INVALID_ACTION','message':'Проверьте поля, этап и условия операции.'})
        except Exception:
            import logging;logging.error('V2 action failed; no request data logged')
            return self.respond(503,{'error':'OPERATION_UNAVAILABLE'})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--init',action='store_true');parser.add_argument('--seed-demo',action='store_true');parser.add_argument('--port',type=int,default=5180);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--root',default='personalCab/web/dist');args=parser.parse_args()
    app=Application(PostgresConfig.from_env(),extractor=OllamaExtraction())
    if args.init:app.initialize(args.seed_demo);return
    public_origin(args.port)
    server=ThreadingHTTPServer((args.host,args.port),partial(Handler,app=app,root=args.root))
    print(f'AURELIUS V2 integrated: {args.port}',flush=True)
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
