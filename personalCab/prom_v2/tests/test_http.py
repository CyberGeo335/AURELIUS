"""Real local HTTP contract; no PostgreSQL/Ollama and no V1 writes."""
from functools import partial
from http.server import ThreadingHTTPServer
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from personalCab.prom_v2.agent import Agent
from personalCab.prom_v2.models import Actor
from personalCab.prom_v2.repository import MemoryRepository
from personalCab.prom_v2.server import Handler


@pytest.fixture
def http():
    token = "test-only-token-with-more-than-32-characters"
    actor = Actor(actor_id="test-client", company_id=40, borrower_id="test-business")
    agent = Agent(MemoryRepository())
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, agent=agent, actor=actor, token=token))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, body=None, *, authenticated=True, origin=None):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + token
        if origin:
            headers["Origin"] = origin
        req = Request(f"http://127.0.0.1:{server.server_port}" + path,
                      data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    yield request
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


def test_auth_identity_override_and_origin(http):
    assert http("/api/v2/cases", authenticated=False)[0] == 401
    assert http("/api/v2/health", origin="https://untrusted.example")[0] == 403
    assert http("/api/v2/commands", {"request_id": "hack", "action": "CREATE", "expected_version": 0,
                                      "company_id": 41, "role": "OPERATOR"})[0] == 400


def test_case_commands_replay_stale_version_and_reference(http):
    command = {"request_id": "create", "action": "CREATE", "expected_version": 0}
    status, created = http("/api/v2/commands", command)
    assert status == 200
    assert http("/api/v2/commands", command)[1] == created
    change = {"request_id": "edit", "action": "UPDATE_REQUEST", "case_id": created["case_id"],
              "expected_version": created["version"], "arguments": {"patch": {"amount_rub": 1500000}}}
    status, updated = http("/api/v2/commands", change)
    assert status == 200 and updated["request"]["amount_rub"] == 1500000
    assert http("/api/v2/commands", {**change, "request_id": "stale"})[0] == 409
    rag = {"request_id": "rag", "action": "CHAT", "case_id": created["case_id"],
           "expected_version": updated["version"], "text": "Какой формат ИНН для R01 ООО?"}
    status, answer = http("/api/v2/commands", rag)
    assert status == 200 and answer["knowledge_answer"]["status"] == "FOUND"
    assert answer["request"] == updated["request"] and answer["revision"] == updated["revision"]
    assert http("/api/v2/cases/" + created["case_id"])[1]["version"] == answer["version"]
    assert len(http("/api/v2/cases")[1]["cases"]) == 1


def test_old_v1_routes_are_not_exposed(http):
    assert http("/api/chat")[0] == 404
    assert http("/api/v2/operator/decision", {})[0] == 404
