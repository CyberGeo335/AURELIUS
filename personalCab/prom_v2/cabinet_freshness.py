"""Conservative input guards around the unmodified scoring library.

Table locks deliberately also block inserts/deletes by external DB writers. This
is a local-demo contract, not a scalable row-versioning protocol for production.
"""
import hashlib
import json
from datetime import date
from pathlib import Path

from psycopg import sql

from .cabinet import serial

SOURCE_TABLES = (
    'credit_applications', 'companies', 'application_details', 'application_product_details',
    'application_field_values', 'credit_products', 'credit_product_terms',
    'credit_product_rate_options', 'credit_product_repayment_options',
    'credit_product_eligibility_rules', 'credit_product_purposes', 'credit_product_fees',
    'risk_policy_parameters', 'macro_indicators', 'bank_transactions', 'financial_statements',
    'credit_obligations', 'credit_repayment_history', 'legal_events',
)
OUTPUT_TABLES = ('application_product_terms', 'application_snapshots', 'credit_decisions')


def lock_inputs(db, outputs=False):
    # Always acquire sources before outputs and before the application row.
    # SRE serializes cabinet checks and avoids a SHARE->writer lock upgrade race.
    tables = OUTPUT_TABLES if outputs else SOURCE_TABLES
    db.execute(sql.SQL('LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE').format(
        sql.SQL(',').join(sql.Identifier('public', table) for table in tables)))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, default=serial, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def input_hash(db, aid):
    app = db.execute('SELECT * FROM public.credit_applications WHERE application_id=%s', (aid,)).fetchone()
    # Workflow state is an output, not a new economic input.
    app = {k: v for k, v in app.items() if k not in ('application_status', 'decision_date')}
    cid, product = app['company_id'], app['product_code']
    data = {'application': app, 'evaluation_date': date.today().isoformat()}
    scopes = {
        'companies': ('company_id=%s', (cid,)),
        **{table: ('application_id=%s', (aid,)) for table in
           ('application_details', 'application_product_details', 'application_field_values')},
        **{table: ('company_id=%s', (cid,)) for table in
           ('bank_transactions', 'financial_statements', 'credit_obligations', 'legal_events')},
        **{table: ('product_code=%s', (product,)) for table in
           ('credit_products', 'credit_product_terms', 'risk_policy_parameters')},
        **{table: ('terms_id IN (SELECT terms_id FROM public.credit_product_terms WHERE product_code=%s)', (product,))
           for table in ('credit_product_rate_options', 'credit_product_repayment_options',
                         'credit_product_eligibility_rules', 'credit_product_purposes', 'credit_product_fees')},
        'macro_indicators': ("indicator_code='KEY_RATE'", ()),
        'credit_repayment_history': ('obligation_id IN (SELECT obligation_id FROM public.credit_obligations WHERE company_id=%s)', (cid,)),
        'application_product_terms': ("application_id=%s AND offer_status IN ('DRAFT','PROPOSED') AND (offered_conditions->>'generated_by' IS DISTINCT FROM 'AURELIUS_SCORING')", (aid,)),
    }
    for table, (where, params) in scopes.items():
        rows = db.execute(sql.SQL('SELECT * FROM public.{} WHERE ' + where).format(sql.Identifier(table)), params).fetchall()
        data[table] = sorted(rows, key=lambda row: json.dumps(row, default=serial, sort_keys=True))
    root = Path(__file__).resolve().parents[2] / 'scoring' / 'main'
    # Pin all library code/config plus model metadata/weights, without changing it.
    paths = [p for p in root.rglob('*') if p.is_file() and
             (p.suffix in ('.py', '.json', '.cbm') and 'tests' not in p.parts and 'reports' not in p.parts)]
    data['artifacts'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return fingerprint(data)


def latest_input(db, aid):
    return db.execute('SELECT * FROM aurelius_cabinet.calculation_inputs WHERE application_id=%s ORDER BY input_id DESC LIMIT 1', (aid,)).fetchone()


def calculation_hash(db, aid, snapshot_id):
    # run_application may legitimately return an older cached DECISION when
    # source data returns to its former values. Bind that exact result, while
    # also detecting any later out-of-band calculation or snapshot mutation.
    latest = db.execute("SELECT snapshot_id,snapshot_version FROM public.application_snapshots WHERE application_id=%s AND snapshot_type='DECISION' ORDER BY snapshot_version DESC LIMIT 1", (aid,)).fetchone()
    selected = db.execute("SELECT snapshot_id,snapshot_data FROM public.application_snapshots WHERE application_id=%s AND snapshot_id=%s AND snapshot_type='DECISION'", (aid, snapshot_id)).fetchone()
    return fingerprint({'contract': 'cabinet-input-guard-v1', 'inputs': input_hash(db, aid),
                        'latest_snapshot': latest, 'selected_snapshot': selected})


def current_calculation(db, aid):
    from .cabinet import Cabinet
    guard = latest_input(db, aid)
    offer = Cabinet.latest_offer(db, aid)
    return guard if (guard
                     and guard['offer_hash'] == (offer_hash(offer) if offer else None)
                     and guard['input_hash'] == calculation_hash(db, aid, guard['snapshot_id'])) else None


def offer_hash(offer):
    return fingerprint({k: v for k, v in offer.items() if k != 'offer_status'})


def stale_offer(db, aid, offer, user):
    from .cabinet import Cabinet
    reason = 'Данные изменились, банк повторно проверяет предложение.'
    db.execute("INSERT INTO aurelius_cabinet.stale_offers(offer_id,application_id,reason) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING", (offer['offer_id'], aid, reason))
    db.execute("UPDATE public.application_product_terms SET offer_status='DECLINED' WHERE offer_id=%s AND offer_status='PROPOSED'", (offer['offer_id'],))
    db.execute("UPDATE public.credit_applications SET application_status='UNDER_REVIEW' WHERE application_id=%s", (aid,))
    Cabinet.event(db, aid, user, 'offer_stale', {'offer_id': offer['offer_id'], 'reason': reason})
