"""Same-origin local DEMO server for the cabinet and modules 1–3.

Run from repository root: python -m personalCab.frontend.server
Identity is assigned by the trusted demo boundary, never by chat/LLM.
"""
from __future__ import annotations

import argparse
from datetime import timedelta, datetime
import psycopg
from functools import partial
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Literal, Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from personalCab.prom.prom_lab.ai_agents_lab.agents.workflow import WorkflowApp
from personalCab.prom.prom_lab.ai_agents_lab.repositories.case_repository import AccessDenied, ConflictError
from personalCab.prom.prom_lab.ai_agents_lab.repositories.postgres_case_repository import create_case_repository
from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import ActorContext, Consent, Scope, utcnow, DialogueResult, MessageInput, REQUIRED_FIELDS
from personalCab.prom.prom_lab.ai_agents_lab.services.cabinet import CabinetControls

ROOT = Path(__file__).resolve().parent
MODEL = 'gpt-oss:20b'
LOG = logging.getLogger('aurelius.web')


class ChatCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_-]+$')
    text: str = Field(min_length=1, max_length=12000)


class LoginCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    login: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class CaseCommand(ChatCommand):
    command: Literal['UPDATE_REQUEST','REFRESH_EVIDENCE','ASSESS','SUBMIT','ACCEPT_OFFER','EXECUTE_DEMO','POLL_STATUS']
    arguments: dict[str,Any] = Field(default_factory=dict)


class ControlCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=1,max_length=120,pattern=r'^[A-Za-z0-9_-]+$')
    arguments: dict[str,Any] = Field(default_factory=dict)


class FieldAnswers(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str
    revision: int = Field(strict=True,gt=0)
    answers: list[dict[str,Any]] = Field(min_length=1,max_length=100)


class DocumentUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str
    filename: str = Field(min_length=1,max_length=255)
    content_base64: str = Field(min_length=1,max_length=28*1024*1024)


class DemoPayment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    case_id:str
    operation_id:str=Field(min_length=1,max_length=120,pattern=r'^[A-Za-z0-9_-]+$')
    amount_rub:str=Field(min_length=1,max_length=30)


ACTION_HINTS = {
    'KNOWLEDGE_ANSWER': 'Справка по требованиям; можно продолжить работу с заявкой',
    'ASK_FIELDS': 'Уточнить обязательные сведения у предпринимателя',
    'SELECT_BORROWER': 'Выбрать один субъект для обращения',
    'SPLIT_PURPOSES': 'Уточнить одну потребность и её параметры',
    'PROVIDE_CONSENT': 'Получить согласие через доверенный интерфейс',
    'ALTERNATIVE_ROUTE': 'Уточнить альтернативный способ предоставления данных',
    'PROVIDE_DOCUMENTS': 'Дождаться документов предпринимателя',
    'HUMAN_HANDOFF_REQUIRED': 'Дождаться подключения уполномоченного специалиста',
    'HANDOFF_MODULE_5': 'Передать подтверждённую оценку модулю 5',
    'CONNECT_MODULE': 'Подключить следующий модуль',
    'RETRY_MESSAGE': 'Повторить или уточнить сообщение; надёжное извлечение не завершено',
    'RETRY_TOOL': 'Восстановить инструмент и повторить действие',
    'POLL_EXISTING_PROCESS': 'Дождаться результата существующего внешнего процесса',
    'WAIT_FOR_INTEGRATION': 'Подключить адаптер существующего процесса',
    'DONE': 'Процесс завершён',
    'DATABASE_ROUTE_UNSUPPORTED': 'Подключить сбор данных для выбранного продуктового направления',
    'REVIEW_DATA_QUALITY': 'Проверить блокирующие замечания snapshot и согласовать преобразования признаков',
    'CLARIFY_PRODUCT_NEED': 'Уточнить потребность или известные ограничения для подбора продукта',
}


def result_envelope(result: DialogueResult, message_id: str | None = None) -> dict:
    """Expose confirmed module output plus a deterministic, labelled debug view."""
    request = result.request.model_dump(mode='json')
    missing = [field for field in REQUIRED_FIELDS if request[field] is None]
    completed = [trace.tool_name for trace in result.tool_traces if trace.result.ok]
    completed.append('persist')  # handle() returned only after the atomic commit.
    waiting = ACTION_HINTS.get(result.next_action, result.next_action)
    ready = not missing and result.error_code != 'LLM_UNAVAILABLE_OR_INVALID_OUTPUT'
    return {
        'message_id': message_id,
        'result': result.model_dump(mode='json'),
        'workflow_log': {
            'case_id': result.case_id, 'revision': result.revision,
            'mode': result.mode, 'status': result.status,
            'subject': {'borrower_id': request['borrower_id'], 'legal_form': request['legal_form']},
            'purpose': request['purpose'], 'amount_rub': request['amount_rub'],
            'term_months': request['term_months'], 'needed_by': request['needed_by'],
            'constraints': {key: request[key] for key in ('known_obligations', 'collateral', 'seasonality', 'repayment_source', 'recurring', 'financing_need', 'business_age_months', 'monthly_revenue_rub', 'operating_cycle_days', 'has_collateral')},
            'unknown_fields': result.unknown_fields, 'missing_required': missing,
            'completed_stage': f"Модуль 5 DEMO: {result.bank_application['status']}" if result.bank_application else f"Модуль 4: {result.assessment['status']}" if result.assessment else 'Модули 1–3: snapshot сохранён, готовность признаков проверена' if result.data_context else 'Модули 1–2: запрос, кандидаты и требования подготовлены' if result.product_requirements else 'Модуль 1: структурированный запрос подготовлен' if ready else 'Уточнение потребности в модуле 1',
            'data_resolution': result.data_resolution.model_dump(mode='json') if result.data_resolution else None,
            'module_3': result.data_context,
            'evidence_recheck':result.evidence_recheck,
            'module_4':result.assessment,
            'module_5':result.bank_application,
            'module_2': result.product_selection.model_dump(mode='json') if result.product_selection else None,
            'requirements': result.product_requirements.model_dump(mode='json') if result.product_requirements else None,
            'knowledge_answer': result.knowledge_answer.model_dump(mode='json') if result.knowledge_answer else None,
            'completed_operations': completed, 'waiting_on': waiting,
            'next_action': result.next_action, 'next_module': result.next_module,
            'error_code': result.error_code, 'correlation_id': result.correlation_id,
        },
    }


class ChatService:
    def __init__(self, database=None, *, extractor=None, company_id=None, evidence_consent=False, allowed_company_ids=None, require_login=None):
        self.database = database
        self.repository = create_case_repository(database)
        self.require_login = hasattr(self.repository, 'config') if require_login is None else require_login
        self.company_id = company_id
        self.evidence_consent = evidence_consent
        self.allowed_company_ids = set(allowed_company_ids or ([company_id] if company_id else []))
        if company_id and company_id not in self.allowed_company_ids:
            raise ValueError('Default company must be authorized')
        if company_id is not None:
            if company_id <= 0:
                raise ValueError('company_id must be positive')
            if hasattr(self.repository, 'config'):
                with self.repository.config.connect() as db:
                    if not db.execute('SELECT 1 FROM public.companies WHERE company_id=%s', (company_id,)).fetchone():
                        raise ValueError('Configured DEMO company does not exist')
        self.extractor = extractor
        with self.repository.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS web_clients (token TEXT PRIMARY KEY, actor_id TEXT NOT NULL, session_id TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS login_attempts(address TEXT NOT NULL, attempted_at TEXT NOT NULL)')
            if not hasattr(self.repository, 'config'):
                db.execute('CREATE TABLE IF NOT EXISTS client_accounts(client_id TEXT PRIMARY KEY,full_name TEXT NOT NULL,login TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,company_id INTEGER UNIQUE NOT NULL,active INTEGER NOT NULL DEFAULT 1)')
                db.execute('CREATE TABLE IF NOT EXISTS client_sessions(token TEXT PRIMARY KEY,client_id TEXT NOT NULL,expires_at TEXT NOT NULL)')
        self.controls=CabinetControls(self.repository,self.allowed_company_ids)

    def client(self, token: str | None) -> tuple[str, ActorContext, str, bool]:
        account = None
        if self.require_login:
            with self.repository.connect() as db:
                account = db.execute('SELECT a.* FROM client_sessions s JOIN client_accounts a ON a.client_id=s.client_id WHERE s.token=? AND s.expires_at>? AND a.active=1', (token or '',utcnow().isoformat())).fetchone()
            if not account:
                raise AccessDenied('LOGIN_REQUIRED')
        with self.repository.connect() as db:
            row = db.execute('SELECT actor_id,session_id FROM web_clients WHERE token=?', (token or '',)).fetchone()
            new = row is None
            if new:
                token = secrets.token_hex(32)
                actor_id, session_id = 'web-' + secrets.token_hex(16), 'session-' + secrets.token_hex(16)
                db.execute('INSERT INTO web_clients VALUES(?,?,?)', (token, actor_id, session_id))
            else:
                actor_id, session_id = row['actor_id'], row['session_id']
        with self.repository.connect() as db:
            profile=db.execute('SELECT company_id FROM web_profiles WHERE actor_id=?',(actor_id,)).fetchone()
            selected=account['company_id'] if account else profile['company_id'] if profile else self.company_id
            if not account and selected is not None and selected not in self.allowed_company_ids:
                raise AccessDenied('COMPANY_NOT_AUTHORIZED')
            if not profile:
                db.execute('INSERT INTO web_profiles(actor_id,company_id) VALUES(?,?)',(actor_id,selected))
                if self.evidence_consent and selected:
                    now=utcnow()
                    db.execute('INSERT INTO consents(actor_id,company_id,scope,granted_at,expires_at,revoked_at) VALUES(?,?,?,?,?,?) ON CONFLICT(actor_id,company_id,scope) DO NOTHING',
                               (actor_id,selected,Scope.EVIDENCE_COLLECTION.value,now.isoformat(),(now+timedelta(hours=1)).isoformat(),None))
            grants=db.execute('SELECT * FROM consents WHERE actor_id=? AND company_id=?',(actor_id,selected)).fetchall() if selected else []
        borrower = f'PG-COMPANY-{selected}' if selected else 'BORROWER-DEMO-PETYA'
        consents = []
        for grant in grants:
            if grant['revoked_at'] is None:
                consents.append(Consent(consent_id=f"stored:{selected}:{grant['scope']}",borrower_id=borrower,scope=grant['scope'],granted_at=grant['granted_at'],expires_at=grant['expires_at']))
        actor = ActorContext(actor_id=actor_id, active_borrower_id=borrower, allowed_borrower_ids=[borrower], company_id=selected, consents=consents)
        return token, actor, session_id, new

    def handle(self, command: ChatCommand, actor: ActorContext, session_id: str) -> dict:
        if not command.text.strip():
            raise ValueError('Сообщение не должно быть пустым')
        if isinstance(command,ChatCommand) and not isinstance(command,CaseCommand) and re.search(r'\bнов(?:ая|ую)\s+заявк|\bнов(?:ое|ый)\s+обращени',command.text.casefold()):
            try:
                current=self.current_case(actor,session_id)
            except AccessDenied:
                current=None
            if current and current.status in {'CANCELLED','COMPLETED'}:
                session_id=self.controls.execute(actor,session_id,'new-'+command.message_id,'new_session',{})['session_id']
        refs = re.findall(r'https?://[^\s<>"\[\]]+', command.text)[:20]
        message = MessageInput(session_id=session_id, message_id=command.message_id, text=command.text,
                               document_refs=[ref.rstrip('.,;!?)')[:2000] for ref in refs],
                               command=getattr(command,'command','CHAT'),arguments=getattr(command,'arguments',{}))
        with WorkflowApp(self.database, extractor=self.extractor) as app:
            result = app.handle(message, actor)
        return result_envelope(result, command.message_id)

    def state(self, actor: ActorContext, session_id: str) -> dict:
        with self.repository.connect() as db:
            row = db.execute('SELECT case_id FROM credit_sessions WHERE owner_id=? AND session_id=?', (actor.actor_id, session_id)).fetchone()
            if not row:
                return {'history': [], 'latest': None, 'context':self.context(actor)}
            case = self.repository.load(row['case_id'], actor)
            audit = db.execute('SELECT message_id,payload FROM credit_audit WHERE case_id=? ORDER BY id DESC LIMIT 1', (case.case_id,)).fetchone()
        latest = result_envelope(DialogueResult.model_validate_json(audit['payload']), audit['message_id']) if audit else None
        if latest:
            lender=self.controls.lender_status(case,actor)
            latest['result']['bank_application']=lender
            latest['workflow_log']['module_5']=lender
        return {'history': case.history, 'latest': latest, 'context':self.context(actor)}

    def context(self,actor):
        companies=[]
        if hasattr(self.repository,'config'):
            with self.repository.config.connect() as db:
                companies=db.execute('SELECT company_id,name,entity_type FROM public.companies WHERE company_id=ANY(%s) ORDER BY company_id',([actor.company_id] if self.require_login else list(self.allowed_company_ids),)).fetchall()
        with self.repository.connect() as db:
            account = db.execute('SELECT full_name,login FROM client_accounts WHERE client_id=?',(actor.actor_id.removeprefix('client-'),)).fetchone()
        return {'company_id':actor.company_id,'companies':companies,
                'client':dict(account) if account else None,'authenticated':self.require_login,
                'consents':{scope.value:actor.has_consent(scope,actor.active_borrower_id) for scope in Scope},'mode':'DEMO'}

    def current_case(self,actor,session,case_id=None):
        with self.repository.connect() as db:
            row=db.execute('SELECT case_id FROM credit_sessions WHERE owner_id=? AND session_id=?',(actor.actor_id,session)).fetchone()
        if not row or (case_id is not None and case_id!=row['case_id']):
            raise AccessDenied('CASE_NOT_IN_CURRENT_SESSION')
        return self.repository.load(row['case_id'],actor)

    def health(self) -> dict:
        modules=[1,2,3,4,5] if hasattr(self.repository,'config') else [1,2]
        try:
            with self.repository.connect() as db:
                db.execute('SELECT 1')
        except (psycopg.Error, sqlite3.Error, OSError):
            return {'status': 'storage_unavailable', 'modules': modules, 'mode': 'DEMO'}
        base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
        try:
            with urlopen(base_url + '/api/tags', timeout=3) as response:
                models = json.load(response).get('models', [])
            available = any(item.get('name') == MODEL or item.get('model') == MODEL for item in models)
            return {'status': 'ready' if available else 'model_missing', 'model': MODEL, 'module': 1, 'modules': modules, 'mode': 'DEMO'}
        except (OSError, URLError, ValueError):
            return {'status': 'ollama_unavailable', 'model': MODEL, 'module': 1, 'modules': modules, 'mode': 'DEMO'}


class CabinetHandler(SimpleHTTPRequestHandler):
    server_version = 'AURELIUS-DEMO/1.0'

    def __init__(self, *args, service: ChatService, **kwargs):
        self.service = service
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        # Do not log message bodies, cookies, or arbitrary query strings.
        LOG.info('%s %s', self.command, urlsplit(self.path).path)

    def allowed_origin(self) -> bool:
        host = self.headers.get('Host', '')
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        return host in allowed and (origin is None or origin == 'http://' + host)

    def identity(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:
            pass
        morsel = cookie.get('aurelius_demo')
        return self.service.client(morsel.value if morsel else None)

    def json_response(self, status: int, data: dict, token: str | None = None):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if token:
            age=28800 if self.service.require_login else 31536000
            self.send_header('Set-Cookie', f'aurelius_demo={token}; HttpOnly; SameSite=Strict; Path=/api; Max-Age={age}')
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A retry with the same message_id returns the committed receipt.

    def do_GET(self):
        if not self.allowed_origin():
            return self.json_response(403, {'error': 'LOCAL_ORIGIN_REQUIRED'})
        route = urlsplit(self.path).path
        if route == '/api/health':
            return self.json_response(200, self.service.health())
        if route == '/api/auth':
            return self.json_response(200, {'required': self.service.require_login})
        if route == '/api/chat/state':
            try:
                token, actor, session, new = self.identity()
                return self.json_response(200, self.service.state(actor, session), token if new else None)
            except AccessDenied:
                return self.json_response(401 if self.service.require_login else 403, {'error': 'LOGIN_REQUIRED' if self.service.require_login else 'ACCESS_DENIED'})
            except (psycopg.Error, sqlite3.Error, OSError):
                return self.json_response(503, {'error': 'STORAGE_UNAVAILABLE'})
        if route in {'/api/applications','/api/documents'}:
            try:
                token,actor,session,new=self.identity()
                data={'applications':self.service.controls.applications(actor)} if route=='/api/applications' else {'documents':self.service.controls.documents(self.service.current_case(actor,session),actor)}
                return self.json_response(200,data,token if new else None)
            except AccessDenied:
                return self.json_response(403,{'error':'ACCESS_DENIED'})
            except (psycopg.Error,sqlite3.Error,OSError):
                return self.json_response(503,{'error':'STORAGE_UNAVAILABLE'})
        if route.startswith('/api/'):
            return self.json_response(404, {'error': 'NOT_FOUND'})
        if not self.static_allowed():
            return self.send_error(404)
        return super().do_GET()

    def do_HEAD(self):
        if not self.allowed_origin() or not self.static_allowed():
            return self.send_error(404)
        return super().do_HEAD()

    def static_allowed(self) -> bool:
        path = Path(self.translate_path(self.path)).resolve()
        if not path.is_relative_to(ROOT):
            return False
        relative = path.relative_to(ROOT)
        return str(relative) in {'.', 'index.html', 'styles.css', 'app.js', 'landing.html', 'landing.css', 'landing.js'} or (
            relative.parts and relative.parts[0] == 'front_assets' and path.is_file() and path.suffix.lower() in {'.png', '.svg', '.jpg', '.jpeg', '.webp', '.woff', '.woff2'}
        )

    def do_POST(self):
        if not self.allowed_origin():
            return self.json_response(403, {'error': 'LOCAL_ORIGIN_REQUIRED'})
        route=urlsplit(self.path).path
        if route not in {'/api/login','/api/logout','/api/chat','/api/case/command','/api/session/new','/api/context','/api/consents','/api/case/fields','/api/documents','/api/applications/select','/api/case/payment'}:
            return self.json_response(404, {'error': 'NOT_FOUND'})
        if self.headers.get_content_type() != 'application/json':
            return self.json_response(415, {'error': 'JSON_REQUIRED'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= (29*1024*1024 if route=='/api/documents' else 64000):
                return self.json_response(413, {'error': 'BODY_TOO_LARGE'})
            raw=self.rfile.read(length)
            if route == '/api/login':
                from personalCab.prom.prom_lab.ai_agents_lab.services.client_auth import authenticate
                credentials=LoginCommand.model_validate_json(raw)
                with self.service.repository.connect() as db:
                    cutoff=(utcnow()-timedelta(minutes=1)).isoformat()
                    db.execute('DELETE FROM login_attempts WHERE attempted_at<?',(cutoff,))
                    count=db.execute('SELECT COUNT(*) AS n FROM login_attempts WHERE address=?',(self.client_address[0],)).fetchone()['n']
                    if count>=10:
                        return self.json_response(429,{'error':'TOO_MANY_ATTEMPTS','message':'Слишком много попыток входа. Повторите через минуту.'})
                    db.execute('INSERT INTO login_attempts(address,attempted_at) VALUES(?,?)',(self.client_address[0],utcnow().isoformat()))
                token=authenticate(self.service.repository,credentials.login,credentials.password,evidence_consent=self.service.evidence_consent)
                return self.json_response(200,{'authenticated':True},token)
            schema=ChatCommand if route=='/api/chat' else CaseCommand if route=='/api/case/command' else FieldAnswers if route=='/api/case/fields' else DocumentUpload if route=='/api/documents' else DemoPayment if route=='/api/case/payment' else ControlCommand
            command=schema.model_validate_json(raw)
            token, actor, session, new = self.identity()
            if route == '/api/logout':
                with self.service.repository.connect() as db:
                    db.execute('DELETE FROM client_sessions WHERE token=?',(token,))
                return self.json_response(200,{'authenticated':False})
            if route == '/api/context' and self.service.require_login:
                raise AccessDenied('ACCOUNT_COMPANY_IS_FIXED')
            if new:
                return self.json_response(428, {'error': 'SESSION_REQUIRED', 'message': 'Сессия создана. Повторите запрос с тем же message_id или обновите диалог.'}, token)
            if route in {'/api/chat','/api/case/command'}:
                result=self.service.handle(command,actor,session)
            elif route in {'/api/session/new','/api/context','/api/consents','/api/applications/select'}:
                result=self.service.controls.execute(actor,session,command.request_id,{'/api/session/new':'new_session','/api/context':'company','/api/consents':'consent','/api/applications/select':'select_case'}[route],command.arguments)
            elif route=='/api/case/fields':
                if not hasattr(self.service.repository,'config'):
                    raise ValueError('PostgreSQL is required')
                with self.service.repository.actor_lock(actor.actor_id):
                    case=self.service.current_case(actor,session,command.case_id)
                    if case.revision!=command.revision or case.status in {'CANCELLED','COMPLETED'}:
                        raise ConflictError('Case revision changed or case is closed')
                    from personalCab.prom.prom_lab.ai_agents_lab.repositories.business_repository import BusinessRepository
                    BusinessRepository(self.service.repository.config).answer_fields(case,actor,command.answers)
                result={'saved':True,'next_action':'REFRESH_EVIDENCE'}
            elif route=='/api/case/payment':
                if not hasattr(self.service.repository,'config'):
                    raise ValueError('PostgreSQL is required')
                with self.service.repository.actor_lock(actor.actor_id):
                    case=self.service.current_case(actor,session,command.case_id)
                    from personalCab.prom.prom_lab.ai_agents_lab.services.lending import LendingService
                    result={'bank_application':LendingService(self.service.repository.config).record_demo_payment(case,actor,command.operation_id,command.amount_rub)}
            else:
                with self.service.repository.actor_lock(actor.actor_id):
                    case=self.service.current_case(actor,session,command.case_id)
                    result={'documents':self.service.controls.upload(case,actor,command.filename,command.content_base64),'next_action':'REFRESH_EVIDENCE'}
            return self.json_response(200, result, token if new else None)
        except (ValidationError, ValueError) as exc:
            return self.json_response(400, {'error': 'INVALID_MESSAGE', 'message': str(exc) if route=='/api/case/fields' and not isinstance(exc,ValidationError) else 'Проверьте формат введённых данных.'})
        except ConflictError:
            return self.json_response(409, {'error': 'CONFLICT', 'message': 'Предыдущий запрос ещё обрабатывается или идентификатор уже использован. Повторите то же сообщение после завершения обработки.'})
        except AccessDenied as exc:
            auth_error = str(exc) in {'LOGIN_REQUIRED','INVALID_CREDENTIALS'}
            return self.json_response(401 if auth_error else 403, {'error': str(exc) if auth_error else 'ACCESS_DENIED', 'message': 'Проверьте логин и пароль или войдите заново.' if auth_error else 'Нет доступа к этому обращению.'})
        except (sqlite3.Error, psycopg.Error, OSError):
            return self.json_response(503, {'error': 'STORAGE_UNAVAILABLE', 'message': 'Хранилище временно недоступно. Повторите запрос с тем же идентификатором.'})
        except Exception:
            LOG.exception('Module 1 request failed')
            return self.json_response(500, {'error': 'WORKFLOW_ERROR', 'message': 'Ошибка обработки. Повторите запрос с тем же идентификатором; состояние заявки хранится на сервере.'})


def main():
    parser = argparse.ArgumentParser(description='AURELIUS cabinet + module 1 (local DEMO)')
    parser.add_argument('--port', type=int, default=5173)
    parser.add_argument('--database', type=Path, help='Явный legacy SQLite режим; по умолчанию PostgreSQL')
    parser.add_argument('--host', choices=['127.0.0.1', '0.0.0.0'], default='127.0.0.1')
    parser.add_argument('--company-id', type=int, default=int(os.environ['AURELIUS_DEMO_COMPANY_ID']) if os.getenv('AURELIUS_DEMO_COMPANY_ID') else None)
    parser.add_argument('--allowed-company-ids',default=os.getenv('AURELIUS_DEMO_ALLOWED_COMPANY_IDS',''),help='Comma-separated operator-authorized DEMO companies')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s: %(message)s')
    allowed=[int(value) for value in args.allowed_company_ids.split(',') if value.strip()] or None
    service = ChatService(args.database, company_id=args.company_id, evidence_consent=os.getenv('AURELIUS_DEMO_EVIDENCE_CONSENT', 'false').lower() == 'true',allowed_company_ids=allowed)
    server = ThreadingHTTPServer((args.host, args.port), partial(CabinetHandler, service=service))
    print(f'AURELIUS: http://127.0.0.1:{server.server_port} · modules 1–5 DEMO · {MODEL}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
