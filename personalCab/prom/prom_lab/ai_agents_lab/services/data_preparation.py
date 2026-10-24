"""Module 3: point-in-time evidence snapshot. No inferred economic formulas or inference."""
from datetime import datetime, timezone
from ..repositories.business_repository import PRODUCT_CODES

from ..schemas.features import BASELINE_FEATURES, DYNAMIC_FEATURES

LEGAL_FORMS={'ИП':'IP','IP':'IP','ООО':'OOO','OOO':'OOO','АО':'AO','AO':'AO','ПАО':'AO','OTHER':'OTHER'}


def legal_form(company):
    if company.get('entity_type') == 'INDIVIDUAL_ENTREPRENEUR':
        return 'IP'
    # LEGAL_ENTITY is a class, not necessarily an OOO. Never infer from company name.
    return LEGAL_FORMS.get(company.get('legal_form'))


def build_evidence(envelope, raw):
    request = envelope['request']
    company = raw['company']
    as_of = envelope['decision_at']
    issues = []
    form = legal_form(company)
    cutoff = datetime.fromisoformat(as_of)
    resolution=raw.get('profile_resolution')
    if resolution and (resolution.get('company_id')!=envelope['company_id'] or datetime.fromisoformat(resolution['available_at'])>cutoff or datetime.fromisoformat(resolution['reviewed_at'])>cutoff):
        resolution=None
    if resolution:
        form=resolution['legal_form']
    if not resolution and (company.get('source_checked_at') is None or datetime.fromisoformat(company['source_checked_at']) > cutoff):
        issues.append('COMPANY_SOURCE_AVAILABILITY_UNKNOWN')
    if form is None:
        issues.append('LEGAL_FORM_UNRESOLVED')
    if form and request.get('legal_form') != form:
        issues.append('REQUEST_COMPANY_LEGAL_FORM_CONFLICT')
    features = {name:None for name in DYNAMIC_FEATURES}
    # Only direct request values are mapped. No guessed ratios, industry or annual rate.
    features.update(requested_amount=request.get('amount_rub'),term_months=request.get('term_months'))
    missing_baseline = [name for name in BASELINE_FEATURES if features[name] is None]
    missing_dynamic = [name for name in DYNAMIC_FEATURES if features[name] is None]
    issues.append('ML_MAPPING_AND_FORMULAS_NOT_APPROVED')
    facts = []
    if resolution:
        facts.append({'field':'legal_form','value':form,'borrower_id':envelope['borrower_id'],'company_id':envelope['company_id'],
                      'confirmed':True,'scope':'PRODUCT_MATCHING','source_ref':'postgres:profile_resolutions:'+resolution['resolution_id'],
                      'verified_at':resolution['reviewed_at'],'available_at':resolution['available_at'],'snapshot_as_of':as_of,'validity':'AS_OF_SNAPSHOT'})
    conflicting_form = False
    for item in raw['provenance'] if 'COMPANY_SOURCE_AVAILABILITY_UNKNOWN' not in issues else []:
        if item['target_table'] not in {'companies','public.companies'} or item['target_record_pk'].get('company_id') != company['company_id']:
            continue
        if item.get('target_field') != 'legal_form':
            continue
        if resolution and datetime.fromisoformat(item['obtained_at'])<=datetime.fromisoformat(resolution['reviewed_at']):
            continue
        if item.get('verification_status') == 'CONFLICT':
            conflicting_form = True
        verified = item.get('verified_at')
        if item.get('verification_status') != 'VERIFIED' or not verified or datetime.fromisoformat(verified) > cutoff or datetime.fromisoformat(item['obtained_at']) > cutoff:
            continue
        observed=item.get('observed_value')
        normalized=LEGAL_FORMS.get(observed) if isinstance(observed,str) else None
        matches_form=(normalized==form) if resolution else (observed==company.get('legal_form'))
        if item.get('observed_value') is not None and not matches_form:
            conflicting_form = True
        # No invented TTL: facts are valid only at this exact snapshot cutoff.
        if form and (resolution or company.get('legal_form') is not None) and matches_form:
            facts.append({'field':'legal_form','value':form,'borrower_id':envelope['borrower_id'],
                          'company_id':envelope['company_id'],'confirmed':True,'scope':'PRODUCT_MATCHING','source_ref':f"postgres:company_data_provenance:{item['provenance_id']}",
                          'verified_at':verified,'available_at':item['obtained_at'],'snapshot_as_of':as_of,'validity':'AS_OF_SNAPSHOT'})
    if conflicting_form:
        facts = []
        issues.append('LEGAL_FORM_SOURCE_CONFLICT')
    return {'schema_version':'PG-EVIDENCE-V1','mode':'DEMO','case_id':envelope['case_id'],
            'revision':envelope['revision'],'borrower_id':envelope['borrower_id'],
            'product_selection_ref':envelope['result_refs'].get('products'),'requirements_ref':envelope['result_refs'].get('requirements'),
            'company_id':envelope['company_id'],'decision_at':as_of,'sources':raw,
            'features':features,'baseline_feature_names':BASELINE_FEATURES,'dynamic_feature_names':DYNAMIC_FEATURES,
            'verified_facts':facts,'data_quality':{'blocking_issues':issues,'missing_baseline':missing_baseline,
            'missing_dynamic':missing_dynamic,'statement_rows':len(raw['financial_statements']),
            'transaction_rows':len(raw['bank_transactions']),
            'unverified_groups':['debt_availability','industry_mapping','derived_features','macroeconomic_mapping']},
            'model_readiness':'INSUFFICIENT_DATA','features_ready':False,'next_module':None}


class DataPreparationService:
    def __init__(self, repository):
        self.repository = repository

    def collect(self, envelope):
        if not envelope.get('company_id'):
            raise ValueError('COMPANY_BINDING_REQUIRED')
        cutoff = datetime.fromisoformat(envelope['decision_at'])
        if cutoff.tzinfo is None:
            raise ValueError('DECISION_TIME_REQUIRES_TIMEZONE')
        raw = self.repository.collect(envelope['company_id'],cutoff)
        payload = build_evidence(envelope,raw)
        if hasattr(self.repository,'questionnaire_sources'):
            from .questionnaire import build_questionnaire
            fields,values,documents=self.repository.questionnaire_sources(envelope)
            payload['questionnaire']=build_questionnaire(envelope,raw,fields,values)
            raw['documents']=documents
            payload['documents']=[{key:item[key] for key in ('document_id','filename','sha256','uploaded_at')} | {'status':item['extracted_data']['status']} for item in documents]
            payload['data_quality']['missing_questionnaire_fields']=[f"{item['product_code']}:{item['field_code']}" for item in payload['questionnaire'] if item['status']=='MISSING']
            payload['data_quality']['coverage']={
                'financial_periods':len(raw['financial_statements']),
                'transaction_months':len({row['transaction_date'][:7] for row in raw['bank_transactions']}),
                'currencies':sorted({row['currency'] for row in raw['bank_transactions']}),
                'is_full_business_coverage_verified':False,
            }
        routes = envelope.get('product_routes',[])
        applications, snapshots, unsupported = {}, {}, []
        for route in routes:
            code = PRODUCT_CODES.get(route['product_id'])
            if code is None:
                unsupported.append(route['product_id'])
                continue
            application_id,snapshot_id = self.repository.save_snapshot(envelope,code,payload)
            applications[code],snapshots[code] = application_id,snapshot_id
        if not snapshots:
            raise ValueError('UNSUPPORTED_DATABASE_ROUTE')
        # Full sources stay in immutable PostgreSQL snapshots, not in the chat response.
        summary = {key:value for key,value in payload.items() if key != 'sources'}
        summary.update(status='SNAPSHOT_READY',application_ids=applications,snapshot_ids=snapshots,unsupported_routes=unsupported)
        return summary
