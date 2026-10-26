"""Probe, download with progress, then verify the model can serve requests."""
import json
import os
import sys
import time
from urllib.request import Request, urlopen

base = os.environ.get('OLLAMA_BASE_URL', 'http://host.docker.internal:11434').rstrip('/')
model = os.environ.get('OLLAMA_MODEL', 'gpt-oss:20b')

def tags():
    with urlopen(base + '/api/tags', timeout=5) as response:
        return json.load(response)['models']

def post(path, payload, timeout):
    return urlopen(Request(base + path, data=json.dumps(payload).encode(),
                           headers={'Content-Type': 'application/json'}), timeout=timeout)

if '--probe' in sys.argv:
    try:
        tags()
    except Exception:
        print('External Ollama unavailable; use bundled Docker service.', flush=True)
        sys.exit(2)
    print('External Ollama reachable.', flush=True)
    sys.exit(0)

for attempt in range(60):
    try:
        models = tags()
        break
    except Exception:
        print(f'Waiting for Ollama ({attempt + 1}/60)...', flush=True)
        time.sleep(2)
else:
    raise SystemExit('Ollama unavailable. Check endpoint and docker compose logs ollama.')

names = {item.get('name') for item in models} | {item.get('model') for item in models}
if model not in names:
    print(f'Downloading {model}; progress follows (models persist in the Ollama volume).', flush=True)
    last = None
    with post('/api/pull', {'model': model, 'stream': True}, 3600) as response:
        for line in response:
            event = json.loads(line)
            if event.get('error'):
                raise RuntimeError(event['error'])
            total, completed = event.get('total', 0), event.get('completed', 0)
            progress = int(completed * 100 / total) if total else None
            state = (event.get('status'), progress)
            if state != last:
                print(f"{state[0]}" + (f' {progress}% ({completed}/{total} bytes)' if total else ''), flush=True)
                last = state
    if model not in {item.get('name') for item in tags()}:
        raise RuntimeError('Pull completed but model is absent from /api/tags')
else:
    print(f'{model} already installed; skipping download.', flush=True)
print('Checking model inference before starting cabinet...', flush=True)
with post('/api/generate', {'model': model, 'prompt': 'OK', 'stream': False,
                           'options': {'num_predict': 1, 'num_ctx': 16384}}, 1800) as response:
    result = json.load(response)
    if result.get('error') or not result.get('done'):
        raise RuntimeError(result.get('error', 'Model readiness check did not complete'))
print('Ollama model ready. Cabinet can start.', flush=True)
