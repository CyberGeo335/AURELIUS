"""Launch boundaries: URL escaping and Ollama download/readiness failures."""
import json
import os
from pathlib import Path
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

DEPLOY = Path(__file__).resolve().parents[1]


def test_database_url_encodes_special_characters():
    from urllib.parse import unquote, urlsplit
    password = 'synthetic:@/ #$%пароль'
    env = dict(os.environ, PG_HOST='db', PG_PORT='5432', PG_DATABASE='demo',
               PG_USER='synthetic@user', PG_PASSWORD=password)
    command = 'import os,json; print(json.dumps([os.environ["DATABASE_URL"],os.environ["AURELIUS_DATABASE_URL"]]))'
    result = subprocess.run([sys.executable, str(DEPLOY / 'runtime.py'), sys.executable, '-c', command],
                            env=env, capture_output=True, text=True, check=True)
    urls = json.loads(result.stdout)
    assert urls[0].startswith('postgresql+psycopg://')
    for url in urls:
        parts = urlsplit(url)
        assert unquote(parts.password) == password
        assert unquote(parts.username) == 'synthetic@user'
        assert parts.hostname == 'db'


def test_empty_password_fails_without_logging_it():
    result = subprocess.run([sys.executable, str(DEPLOY / 'runtime.py'), 'true'],
                            env=dict(os.environ, PG_PASSWORD=' '), capture_output=True, text=True)
    assert result.returncode != 0 and 'POSTGRES_PASSWORD' in result.stderr


def run_ollama(installed, pull_error=False, inference_error=False, probe=False):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'models': [{'name': 'demo:latest'}] if installed or '/api/pull' in calls else []}).encode())

        def do_POST(self):
            calls.append(self.path)
            json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(200)
            self.end_headers()
            payload = ({'error': 'synthetic pull failure'} if pull_error else {'status': 'success'}) if self.path == '/api/pull' else ({'error': 'synthetic inference failure'} if inference_error else {'done': True})
            self.wfile.write(json.dumps(payload).encode() + b'\n')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([sys.executable, str(DEPLOY / 'ollama_ready.py'), *(['--probe'] if probe else [])],
                                env=dict(os.environ, OLLAMA_MODEL='demo:latest',
                                         OLLAMA_BASE_URL=f'http://127.0.0.1:{server.server_port}'),
                                capture_output=True, text=True, timeout=10)
        return result, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_installed_model_is_not_pulled_and_inference_is_checked():
    result, calls = run_ollama(True)
    assert result.returncode == 0 and '/api/pull' not in calls and '/api/generate' in calls


def test_absent_model_is_pulled_before_inference():
    result, calls = run_ollama(False)
    assert result.returncode == 0 and calls.index('/api/pull') < calls.index('/api/generate')


def test_pull_failure_blocks_readiness():
    result, calls = run_ollama(False, pull_error=True)
    assert result.returncode != 0 and '/api/generate' not in calls


def test_inference_failure_blocks_readiness():
    result, _ = run_ollama(True, inference_error=True)
    assert result.returncode != 0


def shell_start(tmp_path, probe_status='0', model_state='exited 0'):
    import shutil
    source = DEPLOY.parent / 'start.sh'
    shutil.copyfile(source, tmp_path / 'start.sh')
    (tmp_path / '.env').write_text('# synthetic test config\n')
    fake = tmp_path / 'docker'
    fake.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$TRACE_FILE"
case "$*" in
  'compose run --rm --no-deps probe') exit "$PROBE_STATUS" ;;
  'compose ps --all --quiet model-init') echo test-model ;;
  'inspect --format '*) echo "$MODEL_STATE" ;;
esac
''')
    fake.chmod(0o755)
    trace = tmp_path / 'calls'
    result = subprocess.run(['sh', str(tmp_path / 'start.sh')], capture_output=True, text=True,
                            env=dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'],
                                     TRACE_FILE=str(trace), PROBE_STATUS=probe_status, MODEL_STATE=model_state))
    return result, trace.read_text()


def test_launcher_uses_external_and_starts_app_only_after_model_check(tmp_path):
    result, calls = shell_start(tmp_path)
    assert result.returncode == 0
    assert '--profile bundled' not in calls
    assert calls.index('inspect --format') < calls.index('compose up -d --no-deps app')


def test_launcher_falls_back_to_bundled_ollama(tmp_path):
    result, calls = shell_start(tmp_path, probe_status='2')
    assert result.returncode == 0 and '--profile bundled up -d ollama' in calls


def test_launcher_does_not_hide_probe_execution_failure(tmp_path):
    result, calls = shell_start(tmp_path, probe_status='7')
    assert result.returncode != 0 and 'up -d --no-deps app' not in calls


def test_launcher_blocks_app_after_failed_model_initialization(tmp_path):
    result, calls = shell_start(tmp_path, model_state='exited 1')
    assert result.returncode != 0 and 'up -d --no-deps app' not in calls
