"""Integration tests require an explicit disposable aurelius_test* v3 database."""
import json
import os
from uuid import uuid4

import pytest

from personalCab.prom_v2.cabinet import ApiError, Cabinet

URL = os.getenv("AURELIUS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Set AURELIUS_TEST_DATABASE_URL for a seeded disposable DB")


@pytest.fixture
def cabinet():
    service = Cabinet(URL)
    with service.connect() as db:
        assert db.execute("SELECT current_database() AS name").fetchone()["name"].startswith("aurelius_test")
    service.initialize()
    return service


@pytest.fixture
def users(cabinet):
    # Read credentials only in memory; neither output nor fixture repr includes passwords.
    with cabinet.connect() as db:
        rows = db.execute("SELECT login,password FROM public.user_accounts WHERE role='CLIENT' AND is_active ORDER BY user_id LIMIT 2").fetchall()
        employee = db.execute("SELECT login,password FROM public.user_accounts WHERE role='BANK_EMPLOYEE' AND is_active LIMIT 1").fetchone()
    result = []
    for row in [*rows, employee]:
        token, user = cabinet.login(row["login"], row["password"])
        assert cabinet.session(token) == user
        result.append(user)
    return result


def command(cabinet, user, action, aid=None, **kwargs):
    body = {"kind": "credit", "action": action, "request_id": uuid4().hex}
    if aid is not None:
        app = next(a for a in cabinet.state(user)["applications"] if a["application_id"] == int(aid))
        body.update(application_id=int(aid), expected_version=app["version"])
    body.update(kwargs)
    return cabinet.action(user, body)


def test_migration_is_additive_and_idempotent(cabinet):
    query = "SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY conname,definition"
    with cabinet.connect() as db:
        before = db.execute(query).fetchall()
    cabinet.initialize()
    with cabinet.connect() as db:
        assert db.execute(query).fetchall() == before
        assert db.execute("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'").fetchone()["n"] == 35


def test_auth_uses_v3_and_clears_cookie_session(cabinet, users):
    assert users[0]["role"] == "CLIENT"
    assert users[2]["role"] == "BANK_EMPLOYEE"
    with pytest.raises(ApiError) as error:
        cabinet.login(users[0]["login"], "incorrect-password")
    assert error.value.status == 401
    with cabinet.connect() as db:
        row = db.execute("SELECT login,password FROM public.user_accounts WHERE user_id=%s", (users[0]["user_id"],)).fetchone()
    token, _ = cabinet.login(row["login"], row["password"])
    cabinet.logout(token)
    with pytest.raises(ApiError):
        cabinet.session(token)


def test_ownership_version_and_idempotent_create(cabinet, users):
    client, other, bank = users
    body = {"kind": "credit", "action": "create", "product": "R01", "company_id": other["company_id"], "request_id": uuid4().hex}
    first = cabinet.action(client, body)
    assert cabinet.action(client, body) == first
    aid = int(first["application_id"])
    own = next(a for a in cabinet.state(client)["applications"] if a["application_id"] == aid)
    assert own["company_id"] == client["company_id"]
    assert not any(a["application_id"] == aid for a in cabinet.state(other)["applications"])
    for user, action in [(other, "cancel"), (client, "review"), (bank, "save")]:
        with pytest.raises(ApiError) as error:
            cabinet.action(user, {"kind": "credit", "action": action, "application_id": aid, "expected_version": 1, "request_id": uuid4().hex})
        assert error.value.status in (403, 404)
    command(cabinet, client, "save", aid, patch={"amount": "3000000", "term": 36, "purpose": "Пополнение оборотных средств"})
    with pytest.raises(ApiError) as error:
        cabinet.action(client, {"kind": "credit", "action": "cancel", "application_id": aid, "expected_version": 1, "request_id": uuid4().hex})
    assert error.value.status == 409
    with pytest.raises(ApiError):
        cabinet.action(client, {**body, "product": "R02"})


def test_incomplete_submission_rolls_back(cabinet, users):
    client = users[0]
    aid = command(cabinet, client, "create", product="R01")["application_id"]
    with pytest.raises(ApiError):
        command(cabinet, client, "submit", aid)
    app = next(a for a in cabinet.state(client)["applications"] if str(a["application_id"]) == aid)
    assert app["application_status"] == "DRAFT"
    assert app["version"] == 1


def test_http_origin_cookie_login_and_logout(cabinet, users, tmp_path):
    from functools import partial
    from http.server import ThreadingHTTPServer
    from http.cookiejar import CookieJar
    from threading import Thread
    from urllib.request import build_opener, HTTPCookieProcessor, Request
    from urllib.error import HTTPError
    from personalCab.prom_v2.cabinet_server import Handler
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, cabinet=cabinet, root=tmp_path))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    with cabinet.connect() as db:
        credentials = db.execute("SELECT login,password FROM public.user_accounts WHERE user_id=%s", (users[0]['user_id'],)).fetchone()
    def post(path, body, origin=base):
        return opener.open(Request(base + path, data=json.dumps(body).encode(),
                                   headers={'Origin': origin, 'Content-Type': 'application/json'}))
    try:
        with pytest.raises(HTTPError) as error:
            post('/api/v2/login', credentials, 'http://untrusted.example')
        assert error.value.code == 403
        with post('/api/v2/login', credentials) as response:
            cookie = response.headers['Set-Cookie']
            assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
            assert json.load(response)['role'] == 'CLIENT'
        with opener.open(base + '/api/v2/state') as response:
            assert all(a['company_id'] == users[0]['company_id'] for a in json.load(response)['applications'])
        post('/api/v2/logout', {}).close()
        with pytest.raises(HTTPError) as error:
            opener.open(base + '/api/v2/session')
        assert error.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_employee_attestation_preserves_source_facts(cabinet, users):
    client, _, bank = users
    aid = int(command(cabinet, client, 'create', product='R01')['application_id'])
    with cabinet.connect() as db:
        db.execute("UPDATE public.credit_applications SET application_status='UNDER_REVIEW' WHERE application_id=%s", (aid,))
        company_before = db.execute('SELECT * FROM public.companies WHERE company_id=%s', (client['company_id'],)).fetchone()
    for actor, source in [(client, 'Test document'), (bank, '')]:
        with pytest.raises(ApiError):
            command(cabinet, actor, 'verify', aid, check_kind='authority', source_ref=source, comment='Reviewed')
    command(cabinet, bank, 'verify', aid, check_kind='authority', source_ref='Test document 123', comment='Полномочия проверены по документу')
    app = next(a for a in cabinet.state(bank)['applications'] if a['application_id'] == aid)
    assert app['verifications'][0]['details']['source_ref'] == 'Test document 123'
    assert next(a for a in cabinet.state(client)['applications'] if a['application_id'] == aid)['verifications'] == []
    with cabinet.connect() as db:
        assert db.execute('SELECT * FROM public.companies WHERE company_id=%s', (client['company_id'],)).fetchone() == company_before


def test_scoring_outage_retries_submission_without_duplicate_mutation(cabinet, users):
    client = users[0]
    aid = int(command(cabinet, client, 'create', product='R01')['application_id'])
    with cabinet.connect() as db:
        company = db.execute('SELECT inn,entity_type FROM companies WHERE company_id=%s', (client['company_id'],)).fetchone()
    fields = {r['field_code']: 'Test fixture' for r in cabinet.state(client)['requirements'] if r['product_code'] == 'R01'}
    fields.update(R01_01='R01', R01_03=company['inn'] or '7701000000', R01_05='1000000', R01_06='36', R01_31='Подтверждаю')
    command(cabinet, client, 'save', aid, patch={'amount': '1000000', 'term': 36, 'purpose': 'Пополнение оборотных средств', 'fields': fields,
        'consentBki': True, 'consentData': True, 'businessConfirmed': True})
    app = next(a for a in cabinet.state(client)['applications'] if a['application_id'] == aid)
    body = {'kind': 'credit', 'action': 'submit', 'application_id': aid, 'expected_version': app['version'], 'request_id': uuid4().hex}
    calls = []
    def unstable_scorer(application_id, save):
        calls.append(application_id)
        if len(calls) == 1:
            raise RuntimeError('Simulated scoring outage')
        return {}  # Receipt recovery only; no credit decision or result is fabricated.
    cabinet.scorer = unstable_scorer
    with pytest.raises(RuntimeError):
        cabinet.action(client, body)
    assert cabinet.action(client, body)['application_id'] == str(aid)
    assert cabinet.action(client, body)['application_id'] == str(aid)
    assert calls == [aid, aid]
    with cabinet.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM aurelius_cabinet.events WHERE application_id=%s AND action='submit'", (aid,)).fetchone()['n'] == 1


def test_actual_scorer_result_review_accept_and_client_redaction(cabinet, users):
    """Use a synthetic financial fixture in the disposable DB, real CatBoost/library."""
    client, _, bank = users
    aid = int(command(cabinet, client, "create", product="R01")["application_id"])
    fixture_inn = '9' + str(uuid4().int % 10**9).zfill(9)
    # Make a new isolated company for this fixture rather than change a seeded company.
    with cabinet.connect() as db:
        cid = db.execute("INSERT INTO public.companies(entity_type,name,inn,registration_date,status,information_reliability_status,okved_main) VALUES('LEGAL_ENTITY','Cabinet test fixture',%s,'2019-01-15','ACTIVE','VERIFIED','46.90') RETURNING company_id", (fixture_inn,)).fetchone()["company_id"]
        db.execute("UPDATE public.credit_applications SET company_id=%s WHERE application_id=%s", (cid, aid))
        for index in range(2025 * 12 + 8, 2026 * 12 + 9):
            year, month = divmod(index, 12)
            db.execute("INSERT INTO public.bank_transactions(company_id,transaction_date,amount,direction,operation_category,currency) VALUES(%s,%s,1000000,'IN','REVENUE','RUB')", (cid, f"{year}-{month + 1:02d}-15"))
        db.execute("INSERT INTO public.financial_statements(company_id,period_start,period_end,statement_type,revenue,operating_profit,cash_and_equivalents,is_verified) VALUES(%s,'2025-10-01','2026-09-30','MANAGEMENT',12000000,3000000,2000000,true)", (cid,))
        oid = db.execute("INSERT INTO public.credit_obligations(company_id,obligation_type,outstanding_balance,monthly_payment,obligation_status) VALUES(%s,'LOAN',300000,100000,'ACTIVE') RETURNING obligation_id", (cid,)).fetchone()["obligation_id"]
        db.execute("INSERT INTO public.credit_repayment_history(obligation_id,period_date,overdue_days) VALUES(%s,'2026-09-01',0)", (oid,))
    actor = {**client, "company_id": cid}  # Trusted fixture identity, never an HTTP field.
    requirements = cabinet.state(actor)["requirements"]
    fields = {r["field_code"]: "Test fixture value" for r in requirements if r["product_code"] == "R01" and r["required_ooo"]}
    fields.update(R01_01="R01", R01_02="LEGAL_ENTITY", R01_03=fixture_inn, R01_05="1000000", R01_06="36", R01_31="Подтверждаю")
    command(cabinet, actor, "save", aid, patch={"amount": "1000000", "term": 36, "purpose": "Пополнение оборотных средств", "fields": fields,
        "consentBki": True, "consentData": True, "businessConfirmed": True})
    command(cabinet, actor, "submit", aid)
    app = next(a for a in cabinet.state(bank)["applications"] if a["application_id"] == aid)
    assert app["application_status"] == "UNDER_REVIEW"
    assert app["decision"] == "MANUAL_REVIEW"
    assert app["assessment"]["risk_assessment"]["pd_application_1y"] is not None
    assert app["offer"]["offer_status"] == "DRAFT"
    borrower = next(a for a in cabinet.state(actor)["applications"] if a["application_id"] == aid)
    assert borrower["assessment"] is None
    assert borrower["offer"] is None
    command(cabinet, bank, "review", aid, decision="APPROVE", reason="Условия проверены сотрудником банка.")
    published = next(a for a in cabinet.state(actor)["applications"] if a["application_id"] == aid)
    assert published["application_status"] == "APPROVED"
    assert published["offer"]["offer_status"] == "PROPOSED"
    assert "pd_application" not in json.dumps(published, default=str)
    command(cabinet, actor, "accept", aid, offer_id=published["offer"]["offer_id"])
    accepted = next(a for a in cabinet.state(actor)["applications"] if a["application_id"] == aid)
    assert accepted["offer"]["offer_status"] == "ACCEPTED"
    assert accepted["application_status"] == "APPROVED"
