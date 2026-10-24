"""Password authentication and explicit provisioning of synthetic demo clients."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from ..schemas.models import utcnow
from ..repositories.case_repository import AccessDenied


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def check_password(password: str, encoded: str) -> bool:
    _, rounds, salt, expected = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
    return hmac.compare_digest(actual, expected)


DUMMY_HASH = hash_password('unusable-' + secrets.token_hex(32))


def authenticate(repository, login: str, password: str, *, evidence_consent=False):
    with repository.connect() as db:
        account = db.execute('SELECT * FROM client_accounts WHERE login=?', (login.strip().casefold(),)).fetchone()
        valid = check_password(password, account['password_hash'] if account else DUMMY_HASH)
        if not valid or not account or not account['active']:
            raise AccessDenied('INVALID_CREDENTIALS')
        token = secrets.token_hex(32)
        actor_id = 'client-' + account['client_id']
        previous=db.execute('SELECT session_id FROM web_clients WHERE actor_id=? LIMIT 1',(actor_id,)).fetchone()
        session_id = previous['session_id'] if previous else 'session-' + secrets.token_hex(16)
        db.execute('INSERT INTO web_clients(token,actor_id,session_id) VALUES(?,?,?)', (token, actor_id, session_id))
        db.execute('INSERT INTO client_sessions(token,client_id,expires_at) VALUES(?,?,?)',
                   (token, account['client_id'], (utcnow()+timedelta(hours=8)).isoformat()))
        profile=db.execute('SELECT company_id FROM web_profiles WHERE actor_id=?',(actor_id,)).fetchone()
        db.execute('INSERT INTO web_profiles(actor_id,company_id) VALUES(?,?) ON CONFLICT(actor_id) DO UPDATE SET company_id=excluded.company_id',
                   (actor_id, account['company_id']))
        if not profile and evidence_consent:
            from ..schemas.models import Scope
            now=utcnow()
            db.execute('INSERT INTO consents(actor_id,company_id,scope,granted_at,expires_at,revoked_at) VALUES(?,?,?,?,?,?) ON CONFLICT(actor_id,company_id,scope) DO NOTHING',
                       (actor_id,account['company_id'],Scope.EVIDENCE_COLLECTION.value,now.isoformat(),(now+timedelta(hours=1)).isoformat(),None))
    return token


def seed_clients(config):
    """Idempotent: never reset passwords or reassign existing accounts."""
    surnames = ['Иванов', 'Петров', 'Сидоров', 'Смирнов', 'Кузнецов', 'Попов', 'Васильев', 'Соколов', 'Михайлов', 'Новиков',
                'Фёдоров', 'Морозов', 'Волков', 'Алексеев', 'Лебедев', 'Семёнов', 'Егоров', 'Павлов', 'Козлов', 'Степанов',
                'Николаев', 'Орлов', 'Андреев', 'Макаров', 'Никитин', 'Захаров', 'Зайцев', 'Соловьёв', 'Борисов', 'Яковлев']
    credentials = []
    with config.connect(workflow=True) as db:
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('seed-client-accounts',0))")
        companies = db.execute('SELECT company_id FROM public.companies ORDER BY company_id LIMIT 30').fetchall()
        if len(companies) != 30:
            raise ValueError('Provisioning requires 30 existing synthetic businesses')
        for index, company in enumerate(companies, 1):
            if db.execute('SELECT 1 FROM client_accounts WHERE company_id=%s', (company['company_id'],)).fetchone():
                continue
            password = secrets.token_urlsafe(18)
            record = {'client_id':f'demo-{index:02}', 'full_name':f'{surnames[index-1]} Александр Сергеевич',
                      'login':f'client{index:02}', 'password':password, 'company_id':company['company_id']}
            db.execute('INSERT INTO client_accounts(client_id,full_name,login,password_hash,company_id) VALUES(%s,%s,%s,%s,%s)',
                       (record['client_id'],record['full_name'],record['login'],hash_password(password),record['company_id']))
            credentials.append(record)
    return credentials
