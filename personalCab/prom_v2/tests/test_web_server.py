"""Actual loopback HTTP checks of the integrated server's origin boundary."""
import json
from functools import partial
from http.server import ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pytest
from personalCab.prom_v2.web_server import Handler, public_origin


@pytest.mark.parametrize('origin',['https://localhost:5187','http://127.0.0.1:5187'])
def test_external_port_is_explicit_and_foreign_origins_are_rejected(tmp_path, monkeypatch, origin):
    monkeypatch.setenv('V2_PUBLIC_ORIGIN',origin)
    app=SimpleNamespace(auth=SimpleNamespace(session=lambda token:{'login':'synthetic'}))
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,app=app,root=tmp_path))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    def get(host, sender=None):
        headers={'Host':host}
        if sender: headers['Origin']=sender
        try:response=urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/v2/session',headers=headers),timeout=5)
        except HTTPError as exc:response=exc
        with response:return response.status,json.load(response)
    try:
        assert get('localhost:5187',origin.replace('127.0.0.1','localhost'))[0]==200
        assert get('127.0.0.1:5187',origin.replace('localhost','127.0.0.1'))[0]==200
        assert get('localhost:5180')[0]==403
        assert get('localhost:5187','https://untrusted.invalid')[0]==403
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


@pytest.mark.parametrize('origin',['http://localhost:99999','http://user:pass@localhost:5187','http://localhost:5187/path'])
def test_invalid_public_origin_fails_closed(origin):
    with pytest.raises(ValueError):public_origin(5180,origin)
