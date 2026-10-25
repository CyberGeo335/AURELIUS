"""Same-origin /api/v2 cabinet for the unmodified public business_scoring v3 schema."""
import argparse
import json
from functools import partial
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .cabinet import ApiError, Cabinet, serial


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, cabinet, root, **kwargs):
        self.cabinet = cabinet
        super().__init__(*args, directory=str(root), **kwargs)

    def log_message(self, *_):
        # Never log request bodies, passwords, cookies or query parameters.
        pass

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie["aurelius_v3"].value if "aurelius_v3" in cookie else ""
        except Exception:
            return ""

    def respond(self, status, result, token=None):
        payload = json.dumps(result, default=serial, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if token is not None:
            self.send_header("Set-Cookie", f"aurelius_v3={token}; HttpOnly; SameSite=Strict; Path=/api/v2; Max-Age={28800 if token else 0}")
        self.end_headers()
        self.wfile.write(payload)

    def error(self, exc):
        if isinstance(exc, ApiError):
            return self.respond(exc.status, {"message": str(exc), "code": exc.code})
        # Financial data failures are not rejections. Do not leak DB exception text.
        name = type(exc).__name__
        if name == "InputError":
            return self.respond(400, {"message": str(exc), "code": "SCORING_INPUT_ERROR"})
        if isinstance(exc, (ValueError, TypeError, KeyError)):
            return self.respond(400, {"message": "Проверьте данные запроса.", "code": "INVALID_REQUEST"})
        return self.respond(503, {"message": "Операция временно недоступна. Обновите заявку и повторите расчёт.",
                                  "code": "CONFIGURATION_ERROR" if name == "ConfigurationError" else "SERVICE_UNAVAILABLE"})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            try:
                user = self.cabinet.session(self.token())
                if path == "/api/v2/session":
                    return self.respond(200, user)
                if path == "/api/v2/state":
                    return self.respond(200, self.cabinet.state(user))
                return self.respond(404, {"message": "Маршрут не найден."})
            except Exception as exc:
                return self.error(exc)
        if path == "/" or not Path(path).suffix:
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path not in {"/api/v2/login", "/api/v2/logout", "/api/v2/action"}:
            return self.respond(404, {"message": "Маршрут не найден."})
        # Strict same-origin POST, including login/logout. No wildcard CORS.
        origin = self.headers.get("Origin")
        expected = f"http://{self.headers.get('Host', '')}"
        if origin != expected:
            return self.respond(403, {"message": "Недопустимый источник запроса."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2 * 1024 * 1024:
                raise ApiError(413, "Запрос слишком большой или пустой.")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ApiError(400, "Ожидается объект запроса.")
            if self.path == "/api/v2/login":
                token, user = self.cabinet.login(body.get("login"), body.get("password"))
                return self.respond(200, user, token)
            user = self.cabinet.session(self.token())
            if self.path == "/api/v2/logout":
                self.cabinet.logout(self.token())
                return self.respond(200, {"authenticated": False}, "")
            return self.respond(200, self.cabinet.action(user, body))
        except Exception as exc:
            return self.error(exc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="Add only aurelius_cabinet metadata")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--root", type=Path, default=Path("personalCab/web/dist"))
    args = parser.parse_args()
    cabinet = Cabinet()
    if args.init:
        cabinet.initialize()
        print("aurelius_cabinet initialized; public v3 schema preserved")
        return
    server = ThreadingHTTPServer((args.host, args.port), partial(Handler, cabinet=cabinet, root=args.root))
    print(f"AURELIUS cabinet: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
