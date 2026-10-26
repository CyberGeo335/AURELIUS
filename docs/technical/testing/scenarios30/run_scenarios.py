"""User CSV regression against a disposable v4 DB, real HTTP/LLM/CatBoost.

Credentials stay in memory. Fixture answers are synthetic test inputs, not
verified facts. No production DB, cancelled application, or company is edited.
"""
import csv
import hashlib
import http.cookiejar
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import date
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote
from uuid import uuid4

sys.path[:0] = ['/app', '/app/scoring']
from personalCab.prom_v2.cabinet import Cabinet, serial
from personalCab.prom_v2.cabinet_server import Handler
from main.ml_scoring.predictor import Predictor

OUT = Path('/tmp/scenarios30')
OUT.mkdir(exist_ok=True)
DBNAME = 'aurelius_test_scenarios_20261026_r2'
assert DBNAME.startswith('aurelius_test')
url = ('postgresql+psycopg://' + quote(os.environ['PG_USER'], safe='') + ':'
       + quote(os.environ['PG_PASSWORD'], safe='') + '@'
       + os.environ['PG_HOST'] + ':' + os.environ['PG_PORT'] + '/' + DBNAME)
cabinet = Cabinet(url)
cabinet.initialize()
server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, cabinet=cabinet, root='/app/personalCab/web/dist'))
Thread(target=server.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{server.server_port}'
rows = list(csv.DictReader(Path('/tmp/scenarios_30.csv').open(encoding='utf-8-sig')))
predictor = Predictor()
report = {'date': '2026-10-26', 'source_commit': '6a9a4c15a0c0eee4c74a62a1e15b9e5bb704eaf6',
          'input_sha256': hashlib.sha256(Path('/tmp/scenarios_30.csv').read_bytes()).hexdigest(),
          'database': DBNAME, 'transport': 'real cabinet_server.Handler HTTP',
          'llm': 'gpt-oss:20b', 'model_version': predictor.model_version,
          'assumptions': ['New application for every row; historical applications not reused',
              'Synthetic answers complete unrelated required fields through HTTP form',
              'AUR-01..09 target missing field supplied only through live chat + explicit confirmation',
              'Amount RUB 3000000; contract 36 months; working capital; all explicit DEMO consents',
              'R02 tranche 6 MONTHS, R03 tranche 30 DAYS are fixture inputs, distinct from contract',
              'AUR-07..09 follow expected field/check columns, not contradictory scenario titles',
              'Sensitivity compares the same requested application features with a single intervention; all other inputs fixed',
              'current_revenue_trend_3m is not a feature of the deployed model; no silent substitution with 12m trend',
              'debt_to_revenue is the existing synthetic model proxy, not observed outstanding-debt/revenue'],
          'results': []}

def save():
    (OUT / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=serial), encoding='utf-8')

def request(opener, path, body=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                                    headers={'Content-Type': 'application/json', 'Origin': BASE})
    try:
        with opener.open(request, timeout=600) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        payload = json.load(exc)
        raise RuntimeError(f'HTTP {exc.code}: {json.dumps(payload, ensure_ascii=False)}') from None

def login(cid=None):
    with cabinet.connect() as db:
        if cid is None:
            account = db.execute("SELECT login,password FROM user_accounts WHERE role='BANK_EMPLOYEE' AND is_active ORDER BY user_id LIMIT 1").fetchone()
        else:
            account = db.execute("SELECT login,password FROM user_accounts WHERE company_id=%s AND role='CLIENT' AND is_active", (cid,)).fetchone()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request(opener, '/api/v2/login', account)
    return opener

def state(opener, aid):
    return next(a for a in request(opener, '/api/v2/state')['applications'] if a['application_id'] == aid)

def action(opener, name, aid=None, **extra):
    body = dict(kind='credit', action=name, request_id=uuid4().hex, **extra)
    if aid is not None:
        body.update(application_id=aid, expected_version=state(opener, aid)['version'])
    return request(opener, '/api/v2/action', body)

def field_value(req, company, code):
    n = int(req['field_code'].split('_')[1])
    special = {1:code, 2:'ИП' if company['entity_type']=='INDIVIDUAL_ENTREPRENEUR' else 'Юридическое лицо',
               4:'Пополнение оборотных средств',5:'3000000',6:'36',7:'Без залога',8:'Готов обсудить поручительство',
               16:'Действующая регистрация',21:'Москва',24:'Иванов Иван Иванович',25:'Руководитель',
               26:'+79990000001',29:'Иванов Иван Иванович',30:'Устав / регистрация ИП',31:'Подтверждаю',
               32:'40702810900000000001',33:'Тестовый банк',34:'044525593'}
    if n in special:
        return special[n]
    target = req['target_db_field'].split(' + ')[0]
    if target.startswith('companies.'):
        value = company.get(target.split('.')[1])
        if value is not None:
            return str(serial(value)) if isinstance(value, date) else str(value)
    fallback = {3:'9900000017',9:'1990000000010',10:'399000000000041',11:'990001001',
                12:'ООО Тестовая компания',13:'ИП Тестовый Предприниматель',14:'ООО',15:'2024-04-13',
                17:'46.90',18:'Оптовая торговля',19:'г. Москва, ул. Тестовая, д. 1',
                20:'г. Москва, ул. Тестовая, д. 1',22:'Микропредприятие',23:'2024-05-01',
                27:'Иванов Иван Иванович',28:'Генеральный директор'}
    return fallback[n]

answers = {
 'AUR-01': ('inn','Мой ИНН: 9900000017.', '9900000017', ['инн']),
 'AUR-02': ('company_name','Полное наименование организации: ООО Тестовая компания 36.', 'ООО Тестовая компания 36', ['наименован']),
 'AUR-03': ('ogrn','ОГРН: 1990000000010.', '1990000000010', ['огрн']),
 'AUR-04': ('ogrnip','ОГРНИП: 399000000000041.', '399000000000041', ['огрнип']),
 'AUR-05': ('legal_address','Юридический адрес: г. Москва, ул. Тестовая, д. 1.', 'г. Москва, ул. Тестовая, д. 1', ['юридическ']),
 'AUR-06': ('director_name','ФИО руководителя: Иванов Иван Иванович.', 'Иванов Иван Иванович', ['руководител']),
 'AUR-07': ('okved_main','Основной ОКВЭД: 46.90.', '46.90', ['оквэд']),
 'AUR-08': ('registration_date','Дата государственной регистрации: 2024-04-13.', '2024-04-13', ['регистрац']),
 'AUR-09': ('actual_activity_description','Фактический вид деятельности: оптовая торговля.', 'оптовая торговля', ['деятельност']),
}

bank = login()
with cabinet.connect() as db:
    before_companies = db.execute('SELECT * FROM companies ORDER BY company_id').fetchall()
    before_history = db.execute('SELECT * FROM credit_applications ORDER BY application_id').fetchall()

for row in rows:
    started = time.monotonic()
    sid, cid, code = row['scenario_id'], int(row['company_id']), row['product_code']
    result = dict(scenario_id=sid, company_id=cid, type=row['тип'], title=row['сценарий'],
                  expected=row['ожидаемая проверка'], product_code=code)
    try:
        with cabinet.connect() as db:
            company = db.execute('SELECT * FROM companies WHERE company_id=%s', (cid,)).fetchone()
            requirements = db.execute('SELECT * FROM application_field_requirements WHERE product_code=%s ORDER BY field_number', (code,)).fetchall()
            old = db.execute('SELECT application_id,application_status FROM credit_applications WHERE company_id=%s ORDER BY application_id', (cid,)).fetchall()
        result['historical_applications'] = old
        result['entity_type_matches'] = company['entity_type'] == row['entity_type']
        opener = login(cid)
        aid = int(action(opener, 'create', product=code)['application_id'])
        result['application_id'] = aid
        result['new_application'] = aid not in {x['application_id'] for x in old}
        applicable = [r for r in requirements if r['required_ip' if company['entity_type']=='INDIVIDUAL_ENTREPRENEUR' else 'required_ooo']]
        missing = row['field_code_пропуска']
        fields = {r['field_code']:field_value(r, company, code) for r in applicable if r['field_code']!=missing}
        patch = dict(amount='3000000', term=36, purpose='Пополнение оборотных средств', fields=fields,
                     details={'contact_full_name':'Иванов Иван Иванович','contact_role':'Руководитель',
                              'contact_phone':'+79990000001','signer_full_name':'Иванов Иван Иванович',
                              'signer_authority_basis':'Устав / регистрация ИП'},
                     consentBki=True, consentData=True, businessConfirmed=True)
        if code != 'R01':
            patch['product_details'] = dict(max_tranche_term_value=6 if code=='R02' else 30,
                                           max_tranche_term_unit='MONTHS' if code=='R02' else 'DAYS')
        action(opener, 'save', aid, patch=patch)
        if row['тип']=='LLM':
            action(opener, 'chat', aid, text='Проверьте анкету: какие реквизиты ещё нужно уточнить? Сведения о сумме, сроке и цели уже заполнены в форме.')
            dialogue = state(opener, aid)['dialogue']
            question = dialogue['history'][-1]['content']
            result['initial_answer'] = question
            if sid in answers:
                target, message, expected_value, fragments = answers[sid]
                result['missing_field'] = missing
                result['profile_field_is_null'] = company.get({'company_name':'name'}.get(target,target)) is None
                result['missing_field_requested'] = any(fragment in question.lower() for fragment in fragments)
                action(opener, 'chat', aid, text=message)
                dialogue = state(opener, aid)['dialogue']
                result['reply'] = message
                result['proposal'] = dialogue['pending']
                assert dialogue['pending'], 'No confirmable proposal for target answer'
                assert target in dialogue['pending']['patch'], f'Target {target} absent from proposal'
                action(opener, 'confirm_facts', aid, proposal_id=dialogue['pending']['proposal_id'])
                saved = next(f for f in state(opener, aid)['fields'] if f['field_code']==missing)
                result['saved_value'] = saved['field_value']
                result['saved_through_chat'] = saved['field_value'].casefold().rstrip('.')==expected_value.casefold().rstrip('.')
                result['saved_provenance'] = {k:saved[k] for k in ('value_source','verification_status')}
        action(opener, 'submit', aid)
        calculated = state(bank, aid)
        assessment = calculated['assessment']
        result.update(application_status=calculated['application_status'], decision=calculated['decision'],
                      scoring_present=assessment is not None, reasons=calculated['reasons'])
        assert assessment, 'Submission has no saved assessment'
        (OUT / (sid+'-assessment.json')).write_text(json.dumps(assessment,ensure_ascii=False,indent=2,default=serial),encoding='utf-8')
        result['eligibility'] = assessment.get('eligibility')
        result['risk_assessment'] = assessment.get('risk_assessment')
        if row['тип']=='SCORE':
            snapshot = assessment['audit']['snapshot']
            from main.ml_scoring.feature_builder import build_features
            features, _ = build_features(snapshot, snapshot['individual_annual_rate_pct'])
            baseline = predictor.predict(features,36)
            changes = {
                'AUR-11':('debt_to_revenue',1), 'AUR-12':('debt_to_revenue',-1),
                'AUR-13':('dscr',-1), 'AUR-14':('dscr',1),
                'AUR-15':('cash_buffer_months',-1), 'AUR-16':('cash_buffer_months',1),
            }
            changed = dict(features)
            interventions = {}
            def move(key, direction, bounds):
                value = float(features[key]); low, high = bounds
                proposed = value + (high-value)*.5 if direction>0 else value-(value-low)*.5
                changed[key]=proposed
                interventions[key]={'baseline':value,'scenario':proposed}
            if sid in changes:
                key, direction = changes[sid]
                move(key,direction,{'debt_to_revenue':(.03,3),'dscr':(.05,8),'cash_buffer_months':(0,18)}[key])
                expected_pd_direction = direction if key=='debt_to_revenue' else -direction
            elif sid in ('AUR-19','AUR-20'):
                adverse = sid=='AUR-19'
                for key, direction, bounds in [('dscr',-1,(.05,8)),('debt_to_revenue',1,(.03,3)),('cash_buffer_months',-1,(0,18))]:
                    move(key,direction if adverse else -direction,bounds)
                expected_pd_direction = 1 if adverse else -1
                result['unsupported_feature'] = 'current_revenue_trend_3m'
            else:
                expected_pd_direction = None
                result['unsupported_feature'] = 'current_revenue_trend_3m'
            predicted = predictor.predict(changed,36)
            delta = predicted.cumulative_pd[11]-baseline.cumulative_pd[11]
            result['sensitivity'] = dict(features=features,interventions=interventions,baseline_pd_12m=baseline.cumulative_pd[11],
                scenario_pd_12m=predicted.cumulative_pd[11], delta_pd_12m=delta,
                baseline_pd_36m=baseline.pd_term,scenario_pd_36m=predicted.pd_term,
                direction_ok=(expected_pd_direction*delta>=-1e-10) if expected_pd_direction else None)
        result['status'] = 'PASS'
        if result.get('saved_through_chat') is False or result.get('missing_field_requested') is False:
            result['status']='FAIL'
        if result.get('sensitivity',{}).get('direction_ok') is False:
            result['status']='FAIL'
        if result.get('unsupported_feature'):
            result['status']='PARTIAL'
    except Exception as exc:
        result['status']='FAIL'
        result['error']=str(exc)
        result['traceback']=traceback.format_exc()
    result['seconds']=round(time.monotonic()-started,2)
    report['results'].append(result)
    save()
    print(sid, result['status'], result.get('error',''), result['seconds'], flush=True)

with cabinet.connect() as db:
    report['companies_unchanged'] = before_companies==db.execute('SELECT * FROM companies ORDER BY company_id').fetchall()
    report['historical_applications_unchanged'] = before_history==db.execute('SELECT * FROM credit_applications WHERE application_id=ANY(%s) ORDER BY application_id',([r['application_id'] for r in before_history],)).fetchall()
from collections import Counter
report['summary']=dict(Counter(r['status'] for r in report['results']))
save()
print('SUMMARY',report['summary'], 'companies_unchanged',report['companies_unchanged'],flush=True)
server.shutdown()
