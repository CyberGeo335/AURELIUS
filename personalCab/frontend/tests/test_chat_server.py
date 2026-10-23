"""HTTP boundary + actual LangGraph/SQLite workflow, deterministic extraction only."""
from functools import partial
import http.client
import json
from threading import Thread

import pytest

from personalCab.frontend.server import CabinetHandler, ChatService, ThreadingHTTPServer
from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import Extraction, LoanRequest, MessageInput


class ScriptedExtractor:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def extract(self, message, case):
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def patch(text, **fields):
    return Extraction(patch=LoanRequest(**fields), evidence={key: text for key in fields})


@pytest.fixture
def service(tmp_path):
    return ChatService(tmp_path / 'web.sqlite3', extractor=ScriptedExtractor())


@pytest.fixture
def http_server(service):
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(CabinetHandler, service=service))
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield server
    server.shutdown()
    server.server_close()
    worker.join(timeout=3)


def request(server, method, path, payload=None, cookie=None, **headers):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=15)
    if cookie:
        headers['Cookie'] = cookie
    if payload is not None:
        headers.setdefault('Content-Type', 'application/json')
    connection.request(method, path, json.dumps(payload) if payload is not None else None, headers)
    response = connection.getresponse()
    status, body, cookie_header = response.status, response.read(), response.getheader('Set-Cookie')
    connection.close()
    try:
        body = json.loads(body)
    except ValueError:
        pass
    return status, body, cookie_header


def test_http_chat_persists_retries_and_revisions(http_server, service):
    text1 = 'Нужно три миллиона рублей на товар'
    text2 = 'Я ИП, деньги нужны на 24 месяца'
    text3 = 'Измени сумму на пять миллионов рублей'
    service.extractor = ScriptedExtractor(
        patch(text1, amount_rub=3000000, purpose='INVENTORY'),
        patch(text2, legal_form='IP', term_months=24),
        patch(text3, amount_rub=5000000),
    )
    status, state, cookie = request(http_server, 'GET', '/api/chat/state')
    assert status == 200 and state == {'history': [], 'latest': None}
    assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
    cookie = cookie.split(';')[0]
    command = {'message_id': 'turn-1', 'text': text1}
    status, first, _ = request(http_server, 'POST', '/api/chat', command, cookie)
    assert status == 200 and first['result']['status'] == 'NEEDS_INPUT'
    assert first['workflow_log']['amount_rub'] == 3000000
    assert first['workflow_log']['needed_by'] is None
    assert 'legal_form' in first['workflow_log']['missing_required']
    status, repeated, _ = request(http_server, 'POST', '/api/chat', command, cookie)
    assert status == 200 and repeated == first and service.extractor.calls == 1
    status, _, _ = request(http_server, 'POST', '/api/chat', {**command, 'text': 'Другое сообщение'}, cookie)
    assert status == 409
    _, second, _ = request(http_server, 'POST', '/api/chat', {'message_id': 'turn-2', 'text': text2}, cookie)
    assert second['result']['status'] == 'WAITING_DOCUMENTS'
    assert second['workflow_log']['next_module'] == 3
    assert second['workflow_log']['error_code'] == 'MODULE_NOT_CONFIGURED'
    assert second['workflow_log']['missing_required'] == []
    assert second['result']['tool_traces'][-1]['tool_name'] == 'request_evidence'
    assert second['workflow_log']['module_2']['status'] == 'PRODUCTS_READY'
    assert second['workflow_log']['requirements']['routes']
    _, third, _ = request(http_server, 'POST', '/api/chat', {'message_id': 'turn-3', 'text': text3}, cookie)
    assert third['result']['case_id'] == first['result']['case_id']
    assert third['result']['revision'] == second['result']['revision'] + 1
    assert third['workflow_log']['amount_rub'] == 5000000
    # Reopen service against the same SQLite file: server/process restart.
    http_server.RequestHandlerClass = partial(CabinetHandler, service=ChatService(service.database))
    _, restored, _ = request(http_server, 'GET', '/api/chat/state', cookie=cookie)
    assert len(restored['history']) == 6 and restored['latest'] == third


def test_clients_are_isolated(http_server, service):
    service.extractor = ScriptedExtractor(patch('Товар за 1000000', purpose='INVENTORY', amount_rub=1000000))
    _, _, cookie = request(http_server, 'GET', '/api/chat/state')
    request(http_server, 'POST', '/api/chat', {'message_id':'one', 'text':'Товар за 1000000'}, cookie.split(';')[0])
    _, other_state, other_cookie = request(http_server, 'GET', '/api/chat/state')
    assert other_state['latest'] is None and other_cookie != cookie


def test_boundaries_reject_role_override_origins_and_private_files(http_server):
    _, _, cookie = request(http_server, 'GET', '/api/chat/state')
    cookie = cookie.split(';')[0]
    status, _, _ = request(http_server, 'POST', '/api/chat', {'message_id':'m','text':'Привет','role':'OPERATOR'}, cookie)
    assert status == 400
    status, _, _ = request(http_server, 'POST', '/api/chat', {'message_id':'m','text':'Привет'}, cookie, Origin='https://example.org')
    assert status == 403
    status, _, _ = request(http_server, 'GET', '/', Host='example.org')
    assert status == 403
    for path in ['/server.py', '/tests/test_chat_server.py', '/../prom/prom_lab/ai_agents_lab/data/aurelius.sqlite3', '/front_assets/../server.py']:
        assert request(http_server, 'GET', path)[0] == 404
    assert request(http_server, 'GET', '/')[0] == 200
    assert request(http_server, 'GET', '/front_assets/money.svg')[0] == 200
    assert request(http_server, 'GET', '/api/unknown')[0] == 404


def test_first_post_establishes_cookie_before_inference(http_server, service):
    status, result, cookie = request(http_server, 'POST', '/api/chat', {'message_id':'m','text':'Привет'})
    assert status == 428 and cookie and service.extractor.calls == 0


def test_model_error_keeps_explicit_unknowns_and_committed_log(service):
    service.extractor = ScriptedExtractor(TimeoutError())
    _, actor, session, _ = service.client(None)
    from personalCab.frontend.server import ChatCommand
    result = service.handle(ChatCommand(message_id='failed-model', text='Нужен кредит'), actor, session)
    assert result['workflow_log']['error_code'] == 'LLM_UNAVAILABLE_OR_INVALID_OUTPUT'
    assert result['workflow_log']['amount_rub'] is None
    assert result['workflow_log']['completed_operations'][-1] == 'persist'
    assert service.state(actor, session)['latest'] == result


def test_links_are_references_never_downloaded(service):
    service.extractor = ScriptedExtractor(Extraction())
    _, actor, session, _ = service.client(None)
    from personalCab.frontend.server import ChatCommand
    service.handle(ChatCommand(message_id='document-link', text='Выписка: https://example.org/statement.pdf'), actor, session)
    case_id = service.state(actor, session)['latest']['result']['case_id']
    case = service.repository.load(case_id, actor)
    assert case.document_refs == ['https://example.org/statement.pdf']
    assert case.verified_facts == []
