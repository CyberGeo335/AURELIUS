"""Authentication is independent from model output and binds exactly one business."""
from datetime import timedelta
import pytest
from personalCab.frontend.server import ChatService
from personalCab.prom.prom_lab.ai_agents_lab.services.client_auth import authenticate,hash_password
from personalCab.prom.prom_lab.ai_agents_lab.repositories.case_repository import AccessDenied
from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import utcnow
from test_chat_server import request, http_server


@pytest.fixture
def service(tmp_path):
    service=ChatService(tmp_path/'auth.sqlite',require_login=True)
    with service.repository.connect() as db:
        for index in (1,2):
            db.execute('INSERT INTO client_accounts(client_id,full_name,login,password_hash,company_id) VALUES(?,?,?,?,?)',
                       (str(index),'Тестовый Клиент','client'+str(index),hash_password('test-pass'),index))
    return service


def test_login_required_wrong_password_logout_and_fixed_company(http_server,service):
    assert request(http_server,'GET','/api/chat/state')[0]==401
    assert request(http_server,'POST','/api/login',{'login':'client1','password':'wrong'})[0]==401
    assert request(http_server,'POST','/api/login',{'login':'missing','password':'test-pass'})[0]==401
    status,_,cookie=request(http_server,'POST','/api/login',{'login':'client1','password':'test-pass'})
    assert status==200 and 'HttpOnly' in cookie
    cookie=cookie.split(';')[0]
    status,state,_=request(http_server,'GET','/api/chat/state',cookie=cookie)
    assert status==200 and state['context']['company_id']==1
    assert state['context']['client']['full_name']=='Тестовый Клиент'
    assert request(http_server,'POST','/api/context',{'request_id':'switch','arguments':{'company_id':2}},cookie)[0]==403
    assert request(http_server,'POST','/api/logout',{'request_id':'logout','arguments':{}},cookie)[0]==200
    assert request(http_server,'GET','/api/chat/state',cookie=cookie)[0]==401


def test_account_isolation_expiration_and_password_storage(service):
    token=authenticate(service.repository,'CLIENT1','test-pass')
    other=authenticate(service.repository,'client2','test-pass')
    _,first,_,_=service.client(token)
    _,second,_,_=service.client(other)
    assert first.actor_id!=second.actor_id and first.company_id==1 and second.company_id==2
    with service.repository.connect() as db:
        assert db.execute('SELECT password_hash FROM client_accounts LIMIT 1').fetchone()['password_hash']!='test-pass'
        db.execute('UPDATE client_sessions SET expires_at=? WHERE token=?',((utcnow()-timedelta(seconds=1)).isoformat(),token))
    with pytest.raises(AccessDenied):service.client(token)
