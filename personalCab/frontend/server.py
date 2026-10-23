"""Same-origin local DEMO server for the cabinet and the existing module 1.

Run from repository root: python -m personalCab.frontend.server
Identity is assigned by this loopback-only demo boundary, never by chat/LLM.
"""
from __future__ import annotations

import argparse
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
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from personalCab.prom.prom_lab.ai_agents_lab.agents.workflow import WorkflowApp
from personalCab.prom.prom_lab.ai_agents_lab.repositories.case_repository import AccessDenied, CaseRepository, ConflictError
from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import ActorContext, DialogueResult, MessageInput, REQUIRED_FIELDS

ROOT = Path(__file__).resolve().parent
DEFAULT_DATABASE = ROOT.parent / 'prom/prom_lab/ai_agents_lab/data/aurelius.sqlite3'
MODEL = 'gpt-oss:20b'
LOG = logging.getLogger('aurelius.web')


class ChatCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_-]+$')
    text: str = Field(min_length=1, max_length=12000)


ACTION_HINTS = {
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
            'completed_stage': 'Модули 1–2: запрос, кандидаты и требования подготовлены' if result.product_requirements else 'Модуль 1: структурированный запрос подготовлен' if ready else 'Уточнение потребности в модуле 1',
            'module_2': result.product_selection.model_dump(mode='json') if result.product_selection else None,
            'requirements': result.product_requirements.model_dump(mode='json') if result.product_requirements else None,
            'completed_operations': completed, 'waiting_on': waiting,
            'next_action': result.next_action, 'next_module': result.next_module,
            'error_code': result.error_code, 'correlation_id': result.correlation_id,
        },
    }


class ChatService:
    def __init__(self, database: Path, *, extractor=None):
        self.database = Path(database)
        self.repository = CaseRepository(self.database)
        self.extractor = extractor
        with self.repository.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS web_clients (token TEXT PRIMARY KEY, actor_id TEXT NOT NULL, session_id TEXT NOT NULL)')

    def client(self, token: str | None) -> tuple[str, ActorContext, str, bool]:
        with self.repository.connect() as db:
            row = db.execute('SELECT actor_id,session_id FROM web_clients WHERE token=?', (token or '',)).fetchone()
            new = row is None
            if new:
                token = secrets.token_hex(32)
                actor_id, session_id = 'web-' + secrets.token_hex(16), 'session-' + secrets.token_hex(16)
                db.execute('INSERT INTO web_clients VALUES(?,?,?)', (token, actor_id, session_id))
            else:
                actor_id, session_id = row['actor_id'], row['session_id']
        # One synthetic subject per local demo profile. Browser input cannot grant roles/consents.
        actor = ActorContext(actor_id=actor_id, active_borrower_id='BORROWER-DEMO-PETYA', allowed_borrower_ids=['BORROWER-DEMO-PETYA'])
        return token, actor, session_id, new

    def handle(self, command: ChatCommand, actor: ActorContext, session_id: str) -> dict:
        if not command.text.strip():
            raise ValueError('Сообщение не должно быть пустым')
        refs = re.findall(r'https?://[^\s<>"\[\]]+', command.text)[:20]
        message = MessageInput(session_id=session_id, message_id=command.message_id, text=command.text,
                               document_refs=[ref.rstrip('.,;!?)')[:2000] for ref in refs])
        with WorkflowApp(self.database, extractor=self.extractor) as app:
            result = app.handle(message, actor)
        return result_envelope(result, command.message_id)

    def state(self, actor: ActorContext, session_id: str) -> dict:
        with self.repository.connect() as db:
            row = db.execute('SELECT case_id FROM credit_sessions WHERE owner_id=? AND session_id=?', (actor.actor_id, session_id)).fetchone()
            if not row:
                return {'history': [], 'latest': None}
            case = self.repository.load(row['case_id'], actor)
            audit = db.execute('SELECT message_id,payload FROM credit_audit WHERE case_id=? ORDER BY id DESC LIMIT 1', (case.case_id,)).fetchone()
        latest = result_envelope(DialogueResult.model_validate_json(audit['payload']), audit['message_id']) if audit else None
        return {'history': case.history, 'latest': latest}

    def health(self) -> dict:
        base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
        try:
            with urlopen(base_url + '/api/tags', timeout=3) as response:
                models = json.load(response).get('models', [])
            available = any(item.get('name') == MODEL or item.get('model') == MODEL for item in models)
            return {'status': 'ready' if available else 'model_missing', 'model': MODEL, 'module': 1, 'modules': [1, 2], 'mode': 'DEMO'}
        except (OSError, URLError, ValueError):
            return {'status': 'ollama_unavailable', 'model': MODEL, 'module': 1, 'modules': [1, 2], 'mode': 'DEMO'}


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
            self.send_header('Set-Cookie', f'aurelius_demo={token}; HttpOnly; SameSite=Strict; Path=/api; Max-Age=31536000')
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
        if route == '/api/chat/state':
            token, actor, session, new = self.identity()
            return self.json_response(200, self.service.state(actor, session), token if new else None)
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
        if urlsplit(self.path).path != '/api/chat':
            return self.json_response(404, {'error': 'NOT_FOUND'})
        if self.headers.get_content_type() != 'application/json':
            return self.json_response(415, {'error': 'JSON_REQUIRED'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 64000:
                return self.json_response(413, {'error': 'BODY_TOO_LARGE'})
            command = ChatCommand.model_validate_json(self.rfile.read(length))
            token, actor, session, new = self.identity()
            if new:
                return self.json_response(428, {'error': 'SESSION_REQUIRED', 'message': 'Сессия создана. Повторите запрос с тем же message_id или обновите диалог.'}, token)
            result = self.service.handle(command, actor, session)
            return self.json_response(200, result, token if new else None)
        except (ValidationError, ValueError):
            return self.json_response(400, {'error': 'INVALID_MESSAGE', 'message': 'Проверьте текст и идентификатор сообщения.'})
        except ConflictError:
            return self.json_response(409, {'error': 'CONFLICT', 'message': 'Предыдущий запрос ещё обрабатывается или идентификатор уже использован. Повторите то же сообщение после завершения обработки.'})
        except AccessDenied:
            return self.json_response(403, {'error': 'ACCESS_DENIED', 'message': 'Нет доступа к этому обращению.'})
        except (sqlite3.Error, OSError):
            return self.json_response(503, {'error': 'STORAGE_UNAVAILABLE', 'message': 'Хранилище временно недоступно. Повторите запрос с тем же идентификатором.'})
        except Exception:
            LOG.exception('Module 1 request failed')
            return self.json_response(500, {'error': 'WORKFLOW_ERROR', 'message': 'Ошибка обработки. Повторите запрос с тем же идентификатором; состояние заявки хранится на сервере.'})


def main():
    parser = argparse.ArgumentParser(description='AURELIUS cabinet + module 1 (local DEMO)')
    parser.add_argument('--port', type=int, default=5173)
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s: %(message)s')
    service = ChatService(args.database)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(CabinetHandler, service=service))
    print(f'AURELIUS: http://127.0.0.1:{server.server_port} · modules 1–2 · {MODEL}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
