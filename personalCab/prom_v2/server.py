"""Local scoped-token gateway. This is not production IAM or a bank operator API."""
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from urllib.parse import urlsplit

from pydantic import ValidationError

from .models import Actor, Command
from .repository import AccessDenied, Conflict


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, agent, actor: Actor, token: str, **kwargs):
        self.agent, self.actor, self.token = agent, actor, token
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # Do not put bearer credentials, chat, query strings or document content in logs.
        return

    def respond(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed(self):
        host = self.headers.get("Host", "")
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in hosts or self.headers.get("Origin") not in {None, "http://" + host}:
            self.respond(403, {"error": "LOCAL_ORIGIN_REQUIRED"})
            return False
        value = self.headers.get("Authorization", "")
        if not hmac.compare_digest(value.encode(), ("Bearer " + self.token).encode()):
            self.respond(401, {"error": "AUTHENTICATION_REQUIRED"})
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        path = urlsplit(self.path).path
        try:
            if path == "/api/v2/health":
                return self.respond(200, {"api_version": "2", "mode": "DEMO", "capabilities": self.agent.capabilities()})
            if path == "/api/v2/cases":
                return self.respond(200, {"cases": self.agent.cases(self.actor)})
            if path.startswith("/api/v2/cases/"):
                case_id = path.removeprefix("/api/v2/cases/")
                return self.respond(200, self.agent.state(self.actor, case_id).model_dump(mode="json"))
            return self.respond(404, {"error": "NOT_FOUND"})
        except AccessDenied:
            return self.respond(403, {"error": "CASE_NOT_ACCESSIBLE"})
        except Exception:
            return self.respond(503, {"error": "STATE_UNAVAILABLE"})

    def do_POST(self):
        if not self.allowed():
            return
        if urlsplit(self.path).path != "/api/v2/commands":
            return self.respond(404, {"error": "NOT_FOUND"})
        if self.headers.get_content_type() != "application/json":
            return self.respond(415, {"error": "JSON_REQUIRED"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 64000:
                return self.respond(413, {"error": "BODY_TOO_LARGE"})
            command = Command.model_validate_json(self.rfile.read(length))
            result = self.agent.handle(self.actor, command)
            return self.respond(200, result.model_dump(mode="json"))
        except Conflict as exc:
            return self.respond(409, {"error": str(exc), "next_action": "RELOAD_CASE_OR_REPLAY_ORIGINAL_COMMAND"})
        except AccessDenied:
            return self.respond(403, {"error": "CASE_NOT_ACCESSIBLE"})
        except (ValidationError, ValueError, TypeError):
            return self.respond(400, {"error": "INVALID_COMMAND"})
        except Exception:
            # An unacknowledged mutation is retried with its original ID and content.
            return self.respond(503, {"error": "COMMAND_UNAVAILABLE", "next_action": "RETRY_SAME_REQUEST_ID"})


def serve(agent, actor: Actor, token: str, port: int = 5180):
    if len(token) < 32:
        raise ValueError("AURELIUS_V2_API_TOKEN must contain at least 32 characters")
    if actor.role != "BORROWER":
        raise ValueError("The local gateway binds one borrower; it does not grant operator powers")
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, agent=agent, actor=actor, token=token))
    print(f"AURELIUS V2 API: http://127.0.0.1:{server.server_port}/api/v2 · DEMO", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
