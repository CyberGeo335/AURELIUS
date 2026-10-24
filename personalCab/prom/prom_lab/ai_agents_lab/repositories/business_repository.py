"""Scoped business reads and immutable snapshots in the existing PostgreSQL schema."""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from psycopg.types.json import Jsonb

from .case_repository import AccessDenied, ConflictError
from ..schemas.models import Scope

PRODUCT_CODES = {'term':'R01', 'rcl':'R02', 'overdraft':'R03'}


def json_safe(value):
    if isinstance(value, (datetime,date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


class BusinessRepository:
    def __init__(self, config):
        self.config = config

    def product_rows(self):
        with self.config.connect() as connection:
            products = connection.execute('SELECT product_code,product_name,active FROM public.credit_products ORDER BY product_code').fetchall()
            terms = connection.execute('SELECT * FROM public.credit_product_terms ORDER BY terms_id').fetchall()
            for table in ('credit_product_rate_options', 'credit_product_fees', 'credit_product_purposes', 'credit_product_repayment_options'):
                rows = connection.execute(f'SELECT * FROM public.{table} ORDER BY terms_id').fetchall()
                for term in terms:
                    term[table] = [row for row in rows if row['terms_id'] == term['terms_id']]
            fields = connection.execute('SELECT * FROM public.application_field_requirements ORDER BY product_code,field_number').fetchall()
            rules = connection.execute('SELECT r.*,t.product_code FROM public.credit_product_eligibility_rules r JOIN public.credit_product_terms t ON t.terms_id=r.terms_id ORDER BY r.rule_id').fetchall()
        return products, terms, fields, rules

    def approval_rows(self):
        with self.config.connect(workflow=True) as db:
            return {row['terms_id']:row for row in db.execute('SELECT * FROM product_approvals').fetchall()}

    def company_profile(self, company_id, as_of):
        """Minimal M1 lookup: no transactions, scores or previous loan parameters."""
        with self.config.connect() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            company = connection.execute('SELECT company_id,entity_type,legal_form,source_checked_at FROM public.companies WHERE company_id=%s', (company_id,)).fetchone()
            if not company:
                raise AccessDenied('COMPANY_NOT_FOUND')
            provenance = connection.execute("SELECT * FROM public.company_data_provenance WHERE company_id=%s AND target_field='legal_form' AND obtained_at<=%s ORDER BY provenance_id", (company_id,as_of)).fetchall()
            resolution=connection.execute('SELECT * FROM aurelius_workflow.profile_resolutions WHERE company_id=%s AND available_at<=%s AND reviewed_at<=%s ORDER BY reviewed_at DESC,resolution_id DESC LIMIT 1',(company_id,as_of,as_of)).fetchone()
        return json.loads(json.dumps({'company':company,'provenance':provenance,'profile_resolution':resolution,'financial_statements':[],'bank_transactions':[]}, default=json_safe))

    def collect(self, company_id, as_of):
        """Explicit columns exclude repayment/default outcomes and future-available records."""
        with self.config.connect() as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            company = connection.execute('SELECT * FROM public.companies WHERE company_id=%s', (company_id,)).fetchone()
            if not company:
                raise AccessDenied('COMPANY_NOT_FOUND')
            provenance = connection.execute('SELECT * FROM public.company_data_provenance WHERE company_id=%s AND obtained_at<=%s ORDER BY provenance_id', (company_id,as_of)).fetchall()
            financials = connection.execute('SELECT * FROM public.financial_statements WHERE company_id=%s AND period_end<=%s AND source_checked_at<=%s ORDER BY period_end,statement_id', (company_id,as_of.date(),as_of)).fetchall()
            transactions = connection.execute('SELECT transaction_id,company_id,transaction_date,amount,currency,direction,operation_category,source_statement_id,source_checked_at FROM public.bank_transactions WHERE company_id=%s AND transaction_date<=%s AND source_checked_at<=%s ORDER BY transaction_date,transaction_id', (company_id,as_of,as_of)).fetchall()
            # Current debt columns have no historical availability/version contract. Read as raw
            # observations, but never use balances/default status to populate historical ML inputs.
            debts = connection.execute('SELECT obligation_id,company_id,creditor_name,obligation_type,contract_date,maturity_date,original_amount,interest_rate FROM public.credit_obligations WHERE company_id=%s AND contract_date<=%s ORDER BY obligation_id', (company_id,as_of.date())).fetchall()
            resolution=connection.execute('SELECT * FROM aurelius_workflow.profile_resolutions WHERE company_id=%s AND available_at<=%s AND reviewed_at<=%s ORDER BY reviewed_at DESC,resolution_id DESC LIMIT 1',(company_id,as_of,as_of)).fetchone()
        return json.loads(json.dumps({'company':company,'provenance':provenance,'profile_resolution':resolution,'financial_statements':financials,'bank_transactions':transactions,'credit_obligations_unverified_availability':debts},default=json_safe))

    def questionnaire_sources(self,envelope):
        with self.config.connect(workflow=True) as db:
            fields=db.execute('SELECT * FROM public.application_field_requirements ORDER BY product_code,field_number').fetchall()
            columns=db.execute("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public'").fetchall()
            types={f"{row['table_name']}.{row['column_name']}":row['data_type'] for row in columns}
            for field in fields:
                field['data_type']=types.get(field['target_db_field'].removeprefix('public.'),'text')
            values=db.execute('SELECT DISTINCT ON (v.product_code,v.field_code) v.*,c.revision AS reported_revision FROM public.application_field_values v JOIN case_applications c ON c.application_id=v.application_id WHERE c.case_id=%s AND c.revision<=%s AND v.obtained_at<=%s AND v.updated_at<=%s ORDER BY v.product_code,v.field_code,c.revision DESC,v.updated_at DESC',
                              (envelope['case_id'],envelope['revision'],envelope['decision_at'],envelope['decision_at'])).fetchall()
            documents=db.execute('SELECT document_id,filename,sha256,uploaded_at,extracted_data FROM evidence_documents WHERE case_id=%s AND owner_id=%s AND company_id=%s AND uploaded_at<=%s ORDER BY uploaded_at',
                                 (envelope['case_id'],envelope['owner_id'],envelope['company_id'],envelope['decision_at'])).fetchall()
        return fields,{(v['product_code'],v['field_code']):v for v in values},json.loads(json.dumps(documents,default=json_safe))

    def answer_fields(self,case,actor,answers):
        from ..services.questionnaire import applicable, validate_answer
        if not actor.has_consent(Scope.EVIDENCE_COLLECTION,case.request.borrower_id):
            raise AccessDenied('CONSENT_REQUIRED')
        with self.config.connect(workflow=True) as db:
            for answer in answers:
                if set(answer)!={'product_code','field_code','value'}:
                    raise ValueError('Unknown questionnaire answer keys')
                code,field=answer['product_code'],answer['field_code']
                link=db.execute('SELECT * FROM case_applications WHERE case_id=%s AND revision=%s AND product_code=%s AND company_id=%s',
                                (case.case_id,case.revision,code,actor.company_id)).fetchone()
                requirement=db.execute('SELECT * FROM public.application_field_requirements WHERE product_code=%s AND field_code=%s',(code,field)).fetchone()
                if not link or not requirement or not applicable(requirement,case.request.legal_form):
                    raise AccessDenied('QUESTIONNAIRE_FIELD_NOT_IN_SCOPE')
                target=requirement['target_db_field'].removeprefix('public.')
                table,sep,column=target.partition('.')
                typ=db.execute("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s",(table,column)).fetchone()
                value=validate_answer(answer['value'],typ['data_type'] if typ else 'text',target,case.request.legal_form)
                old=db.execute('SELECT field_value FROM public.application_field_values WHERE application_id=%s AND field_code=%s FOR UPDATE',(link['application_id'],field)).fetchone()
                old_value=old['field_value'] if old else None
                if old and old_value==value:
                    continue
                if not old and table=='companies':
                    # Column comes from requirements; quote as an identifier, never interpolate SQL.
                    from psycopg import sql
                    previous=db.execute(sql.SQL('SELECT {} AS value FROM public.companies WHERE company_id=%s').format(sql.Identifier(column)),(actor.company_id,)).fetchone()
                    old_value=previous['value'] if previous else None
                from ..services.questionnaire import REQUEST_TARGETS
                if table=='credit_applications' and column in REQUEST_TARGETS and value!=getattr(case.request,REQUEST_TARGETS[column]):
                    raise ValueError('Change request parameters through UPDATE_REQUEST, not the questionnaire')
                db.execute("INSERT INTO public.application_field_values(application_id,product_code,field_code,field_value,value_source,source_reference,obtained_at,verification_status,changed_by_type) VALUES(%s,%s,%s,%s,'CLIENT',%s,CURRENT_TIMESTAMP,'UNVERIFIED','CLIENT') ON CONFLICT(application_id,field_code) DO UPDATE SET field_value=EXCLUDED.field_value,value_source='CLIENT',source_reference=EXCLUDED.source_reference,obtained_at=CURRENT_TIMESTAMP,verification_status='UNVERIFIED',changed_by_type='CLIENT',updated_at=CURRENT_TIMESTAMP",
                           (link['application_id'],code,field,Jsonb(value),'case:'+case.case_id))
                if old_value != value:
                    db.execute('INSERT INTO client_field_changes(case_id,revision,company_id,product_code,field_code,old_value,new_value) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                               (case.case_id,case.revision,actor.company_id,code,field,Jsonb(json.loads(json.dumps(old_value,default=json_safe))),Jsonb(value)))
                db.execute("UPDATE public.application_data_requests SET request_status='ANSWERED',answered_at=CURRENT_TIMESTAMP,answer_value=%s WHERE application_id=%s AND product_code=%s AND field_code=%s AND request_status='OPEN'",
                           (Jsonb(value),link['application_id'],code,field))

    def save_snapshot(self, envelope, code, payload):
        """One DRAFT per case/revision/route; historical snapshots are append-only."""
        from psycopg.types.json import Jsonb
        request = envelope['request']
        serialized = json.dumps(payload,sort_keys=True,default=json_safe,ensure_ascii=False)
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        key = (envelope['case_id'],envelope['revision'],code)
        with self.config.connect(workflow=True) as connection:
            connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (':'.join(map(str,key)),))
            case = connection.execute('SELECT owner_id,borrower_id,payload FROM credit_cases WHERE case_id=%s', (key[0],)).fetchone()
            if not case or case['owner_id'] != envelope['owner_id'] or case['borrower_id'] != envelope['borrower_id']:
                raise AccessDenied('CASE_SCOPE_MISMATCH')
            stored_company = json.loads(case['payload']).get('company_id')
            if stored_company is not None and stored_company != envelope['company_id']:
                raise AccessDenied('CASE_COMPANY_CHANGED')
            if payload['company_id'] != envelope['company_id'] or payload['sources']['company']['company_id'] != envelope['company_id']:
                raise AccessDenied('SNAPSHOT_COMPANY_MISMATCH')
            bound_company = connection.execute('SELECT DISTINCT company_id FROM case_applications WHERE case_id=%s', (key[0],)).fetchall()
            if any(row['company_id'] != envelope['company_id'] for row in bound_company):
                raise AccessDenied('CASE_COMPANY_CHANGED')
            link = connection.execute('SELECT * FROM case_applications WHERE case_id=%s AND revision=%s AND product_code=%s FOR UPDATE', key).fetchone()
            if link and link['input_hash'] == digest:
                return link['application_id'], link['snapshot_id']
            if link:
                application_id = link['application_id']
            else:
                application_id = connection.execute("INSERT INTO public.credit_applications(company_id,product_code,requested_amount,requested_term_months,purpose,application_status,missing_data_status) VALUES(%s,%s,%s,%s,%s,'DRAFT','PARTIAL') RETURNING application_id", (envelope['company_id'],code,request.get('amount_rub'),request.get('term_months'),request.get('purpose'))).fetchone()['application_id']
                connection.execute('INSERT INTO case_applications(case_id,revision,product_code,company_id,application_id,input_hash) VALUES(%s,%s,%s,%s,%s,%s)', (*key,envelope['company_id'],application_id,digest))
            version = connection.execute('SELECT COALESCE(MAX(snapshot_version),0)+1 AS n FROM public.application_snapshots WHERE application_id=%s',(application_id,)).fetchone()['n']
            snapshot_id = connection.execute("INSERT INTO public.application_snapshots(application_id,snapshot_type,snapshot_data,created_by_type,snapshot_version) VALUES(%s,'MANUAL',%s,'SYSTEM',%s) RETURNING snapshot_id", (application_id,Jsonb(json.loads(serialized)),version)).fetchone()['snapshot_id']
            for item in payload.get('questionnaire',[]):
                if item['product_code']==code and item['status']=='MISSING':
                    connection.execute("INSERT INTO public.application_data_requests(application_id,product_code,field_code,question_text) SELECT %s,%s,%s,%s WHERE NOT EXISTS(SELECT 1 FROM public.application_data_requests WHERE application_id=%s AND product_code=%s AND field_code=%s AND request_status='OPEN')",
                                       (application_id,code,item['field_code'],item['question'],application_id,code,item['field_code']))
            connection.execute('UPDATE case_applications SET snapshot_id=%s,input_hash=%s WHERE case_id=%s AND revision=%s AND product_code=%s', (snapshot_id,digest,*key))
        return application_id,snapshot_id
