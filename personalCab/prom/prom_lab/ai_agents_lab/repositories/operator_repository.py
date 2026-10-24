"""Transactional persistence for the trusted local operator CLI."""
from datetime import datetime,timezone
import json
from uuid import uuid4
from psycopg.types.json import Jsonb
from .case_repository import ConflictError
from ..schemas.administration import ProductApproval
from ..schemas.assessment import FeatureInput


def approve_features(config,case_id,product_code,data,reviewer):
    bundle=FeatureInput.model_validate(data)
    if not reviewer.strip():
        raise ValueError('Reviewer is required')
    with config.connect(workflow=True) as db:
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(case_id,))
        row=db.execute('SELECT payload FROM credit_cases WHERE case_id=%s FOR UPDATE',(case_id,)).fetchone()
        if not row:
            raise KeyError('Case not found')
        case=json.loads(row['payload'])
        evidence=case['result_refs'].get('evidence')
        if not evidence or case['status'] in {'CANCELLED','COMPLETED'} or product_code not in (case.get('data_context') or {}).get('application_ids',{}):
            raise ConflictError('Current evidence and supported product required')
        if (bundle.features['requested_amount'],bundle.features['term_months'],bundle.features['entity_type']) != (case['request']['amount_rub'],case['request']['term_months'],case['request']['legal_form']):
            raise ValueError('Explicit inputs do not match the current request')
        input_id='FEATURES-'+uuid4().hex
        db.execute('INSERT INTO feature_inputs(input_id,case_id,revision,evidence_ref,product_code,data,reviewed_by) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(case_id,revision,evidence_ref,product_code) DO UPDATE SET input_id=excluded.input_id,data=excluded.data,reviewed_by=excluded.reviewed_by,reviewed_at=CURRENT_TIMESTAMP',
                   (input_id,case_id,case['revision'],evidence,product_code,Jsonb(bundle.model_dump(mode='json')),reviewer))
        return input_id


def approve_product(config,terms_id,data,reviewer):
    approval=ProductApproval.model_validate(data)
    if not reviewer.strip():
        raise ValueError('Reviewer is required')
    with config.connect(workflow=True) as db:
        terms=db.execute('SELECT * FROM public.credit_product_terms WHERE terms_id=%s FOR UPDATE',(terms_id,)).fetchone()
        if not terms:
            raise KeyError('Product version not found')
        rules=db.execute('SELECT rule_code FROM public.credit_product_eligibility_rules WHERE terms_id=%s',(terms_id,)).fetchall()
        if set(approval.rule_mappings)-{row['rule_code'] for row in rules}:
            raise ValueError('Mapping refers to a rule outside this product version')
        db.execute('UPDATE public.credit_product_terms SET effective_from=%s,effective_to=%s,source_checked_at=%s WHERE terms_id=%s',
                   (approval.effective_from,approval.effective_to,approval.source_checked_at,terms_id))
        db.execute('INSERT INTO product_approvals(terms_id,policy_version,approved_by,approved_at,rule_mappings) VALUES(%s,%s,%s,CURRENT_TIMESTAMP,%s) ON CONFLICT(terms_id) DO UPDATE SET policy_version=excluded.policy_version,approved_by=excluded.approved_by,approved_at=excluded.approved_at,rule_mappings=excluded.rule_mappings',
                   (terms_id,approval.policy_version,reviewer,Jsonb(approval.rule_mappings)))


def resolve_profile(config,company_id,data,reviewer):
    if not isinstance(data,dict) or set(data)!={'legal_form','source_ref','available_at'} or data['legal_form'] not in {'IP','OOO','AO','OTHER'} or not data['source_ref'] or not reviewer.strip():
        raise ValueError('Explicit legal form, source reference, availability and reviewer required')
    available=datetime.fromisoformat(data['available_at'])
    if available.tzinfo is None or available>datetime.now(timezone.utc):
        raise ValueError('Future or timezone-free source is not allowed')
    with config.connect(workflow=True) as db:
        resolution_id='PROFILE-'+uuid4().hex
        db.execute('INSERT INTO profile_resolutions(resolution_id,company_id,legal_form,source_ref,available_at,reviewed_by) VALUES(%s,%s,%s,%s,%s,%s)',
                   (resolution_id,company_id,data['legal_form'],data['source_ref'],available,reviewer))
        return resolution_id


def verify_field(config,case_id,product_code,field_code,data,reviewer):
    from ..services.questionnaire import validate_answer
    if not isinstance(data,dict) or set(data)!={'value','source_ref'} or not data['source_ref'] or not reviewer.strip():
        raise ValueError('Explicit value, evidence source and reviewer required')
    with config.connect(workflow=True) as db:
        row=db.execute('SELECT payload FROM credit_cases WHERE case_id=%s FOR UPDATE',(case_id,)).fetchone()
        if not row:raise KeyError('Case not found')
        case=json.loads(row['payload'])
        if case['status'] in {'CANCELLED','COMPLETED'}:raise ConflictError('Case is closed')
        link=db.execute('SELECT application_id FROM case_applications WHERE case_id=%s AND revision=%s AND product_code=%s',(case_id,case['revision'],product_code)).fetchone()
        requirement=db.execute('SELECT target_db_field FROM public.application_field_requirements WHERE product_code=%s AND field_code=%s',(product_code,field_code)).fetchone()
        if not link or not requirement:raise KeyError('Field is not in the current application')
        table,_,column=requirement['target_db_field'].removeprefix('public.').partition('.')
        typ=db.execute("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s",(table,column)).fetchone()
        value=validate_answer(data['value'],typ['data_type'] if typ else 'text',requirement['target_db_field'],case['request'].get('legal_form'))
        db.execute("INSERT INTO public.application_field_values(application_id,product_code,field_code,field_value,value_source,source_reference,obtained_at,verification_status,changed_by_type) VALUES(%s,%s,%s,%s,'OTHER',%s,CURRENT_TIMESTAMP,'VERIFIED','BANK') ON CONFLICT(application_id,field_code) DO UPDATE SET field_value=excluded.field_value,value_source='OTHER',source_reference=excluded.source_reference,obtained_at=CURRENT_TIMESTAMP,verification_status='VERIFIED',changed_by_type='BANK',updated_at=CURRENT_TIMESTAMP",
                   (link['application_id'],product_code,field_code,Jsonb(value),reviewer+':'+data['source_ref']))
        db.execute("UPDATE public.application_data_requests SET request_status='ANSWERED',answer_value=%s,answered_at=CURRENT_TIMESTAMP WHERE application_id=%s AND field_code=%s AND request_status='OPEN'",(Jsonb(value),link['application_id'],field_code))
        db.execute("UPDATE client_field_changes SET review_status='REVIEWED',reviewed_by=%s,source_ref=%s WHERE case_id=%s AND revision=%s AND product_code=%s AND field_code=%s AND new_value=%s AND review_status='PENDING'",
                   (reviewer,data['source_ref'],case_id,case['revision'],product_code,field_code,Jsonb(value)))


def pending_client_changes(config, case_id=None):
    with config.connect(workflow=True) as db:
        changes=db.execute("SELECT * FROM client_field_changes WHERE review_status='PENDING' AND (%s::text IS NULL OR case_id=%s) ORDER BY changed_at,change_id",(case_id,case_id)).fetchall()
        cases=db.execute('SELECT case_id,payload FROM credit_cases WHERE (%s::text IS NULL OR case_id=%s)',(case_id,case_id)).fetchall()
        for row in cases:
            case=json.loads(row['payload'])
            for change in case.get('client_changes',[]):
                if change['review_status']=='PENDING':
                    changes.append({**change,'case_id':row['case_id'],'company_id':case.get('company_id'),'source':'REQUEST'})
        return changes


