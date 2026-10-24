"""PostgreSQL-backed modules 2–3. Unsupported families remain explicit candidates."""
import json
from datetime import datetime

from ..repositories.business_repository import PRODUCT_CODES, BusinessRepository, json_safe
from ..schemas.models import LoanRequest, ModuleResult
from ..schemas.products import ProductRule, Requirement
from .data_preparation import DataPreparationService, build_evidence
from .product_matching import ProductMatcher, context_hash, load_catalog
from .workflow_service import ModuleUnavailable


class DatabaseModules:
    requires_company_binding = True

    def __init__(self, config):
        self.repository = BusinessRepository(config)
        self.preparation = DataPreparationService(self.repository)
        from .lending import LendingService
        self.lending = LendingService(config)

    def supports(self, operation):
        return operation in {'lookup_business_profile','get_product_candidates','get_data_requirements','request_evidence',
                             'run_assessment','get_assessment_status','submit_application','get_bank_status','accept_offer','execute_demo'}

    def supports_evidence(self, routes):
        return any(route['product_id'] in PRODUCT_CODES for route in routes)

    def matcher(self, cutoff, legal_form=None):
        catalog = load_catalog().model_copy(deep=True)
        products, terms, fields, extra_rules = self.repository.product_rows()
        approvals=self.repository.approval_rows()
        by_code = {item['product_code']:item for item in products}
        for card in catalog.products:
            code = PRODUCT_CODES.get(card.product_id)
            card.database_product_code, card.database_supported = code, code is not None
            if code is None:
                card.limitations.append('Это направление не поддерживается текущей PostgreSQL-схемой R01–R03; не перенаправлять в обычный кредит.')
                continue
            all_terms = [item for item in terms if item['product_code'] == code]
            options = [item for item in all_terms if item['effective_from'] is not None
                       and item['effective_from'] <= cutoff.date()
                       and (item['effective_to'] is None or cutoff.date() <= item['effective_to'])
                       and item['source_checked_at'] is not None and item['source_checked_at'] <= cutoff]
            card.approved = False
            card.source_conditions = {
                'terms': json.loads(json.dumps(all_terms, default=json_safe)),
                'eligibility_rules': json.loads(json.dumps([rule for rule in extra_rules if rule['product_code'] == code], default=json_safe)),
                'validity': 'UNKNOWN',
            }
            card.limitations.append('PostgreSQL DEMO: утверждение кредитором не задано; дополнительные eligibility rules требуют согласования семантики. Проверка UNKNOWN.')
            row = options[0] if len(options) == 1 and by_code.get(code, {}).get('active') else None
            if row is None:
                card.limitations.append('Нет единственной подтверждённой по времени версии условий PostgreSQL. Опубликованные поля сохранены как справочные.')
            else:
                approval=approvals.get(row['terms_id'])
                card.approved=bool(approval and approval['approved_at']<=cutoff)
                card.source_conditions['approval_version']=approval['policy_version'] if card.approved else None
                card.source_conditions['rule_mappings']=approval['rule_mappings'] if card.approved else {}
                card.source_conditions['eligibility_rules']=[rule for rule in card.source_conditions['eligibility_rules'] if rule['terms_id']==row['terms_id']]
                card.source_conditions['validity']='APPROVED' if card.approved else 'UNKNOWN'
                if card.approved:
                    card.limitations=[item for item in card.limitations if not item.startswith('PostgreSQL DEMO: утверждение')]
                    card.limitations.append('Версия условий подтверждена оператором DEMO; результат не является одобрением кредита.')
                card.source_version = f"POSTGRES:{code}:{row['version_code']}:{row['terms_id']}"
                card.rule_version = card.source_version
                card.source_url = row['source_url'] or card.source_url
                card.effective_from, card.effective_until = row['effective_from'], row['effective_to']
                updates = {
                    'AMOUNT': {'minimum': row['min_amount'], 'maximum': row['max_amount']},
                    'BUSINESS_TENURE': {'minimum': row['min_business_age_months']},
                    'COLLATERAL': {'expected_bool': row['requires_collateral']},
                }
                if row['contract_term_unit'] == 'MONTHS':
                    updates['CONTRACT_TERM'] = {'minimum': row['min_contract_term_value'], 'maximum': row['max_contract_term_value']}
                if row['tranche_term_unit'] == 'DAYS':
                    updates['TRANCHE_TERM'] = {'field':'tranche_term_days','minimum': row['min_tranche_term_value'], 'maximum': row['max_tranche_term_value']}
                elif row['tranche_term_unit']=='MONTHS':
                    updates['TRANCHE_TERM']={'field':'tranche_term_months','minimum':row['min_tranche_term_value'],'maximum':row['max_tranche_term_value']}
                if row['allowed_entity_types'] is not None:
                    allowed = []
                    if 'INDIVIDUAL_ENTREPRENEUR' in row['allowed_entity_types']:
                        allowed.append('IP')
                    if 'LEGAL_ENTITY' in row['allowed_entity_types']:
                        allowed.extend(['OOO', 'AO', 'OTHER'])
                    updates['LEGAL_FORM'] = {'allowed': allowed}
                card.rules = [ProductRule.model_validate({**rule.model_dump(), **updates.get(rule.code, {})}) for rule in card.rules]
            for item in fields:
                applicable = item['required_ip'] if legal_form == 'IP' else item['required_ooo'] if legal_form == 'OOO' else True
                if item['product_code'] == code and applicable:
                    card.requirements.append(Requirement(code=f"PG:{code}:{item['field_code']}", label=item['field_label'],
                        source=item['source_description'] or 'Источник не указан',
                        purpose=f"{item['target_db_field']}; required_ip={item['required_ip']}; required_ooo={item['required_ooo']}"))
        catalog = type(catalog).model_validate(catalog.model_dump())
        catalog.version += ':postgres:' + '|'.join(card.source_version for card in catalog.products if card.database_supported)
        return ProductMatcher(catalog)

    def needs_refresh(self, case):
        cutoff = case.data_cutoff_at
        try:
            matcher = self.matcher(cutoff, case.request.legal_form)
            return case.product_selection is None or case.product_selection.context_hash != context_hash(case.request,case.verified_facts,matcher.catalog,cutoff)
        except Exception:
            return True  # Tool invocation will record the concrete controlled failure.

    def call(self, operation, envelope, idempotency_key):
        if not self.supports(operation):
            raise ModuleUnavailable(operation)
        cutoff = datetime.fromisoformat(envelope['decision_at'])
        if operation in {'run_assessment','get_assessment_status','submit_application','get_bank_status','accept_offer','execute_demo'}:
            if operation == 'get_assessment_status':
                result = envelope.get('assessment')
                if not result:
                    raise ValueError('Assessment reference required')
            else:
                result = getattr(self.lending,operation)(envelope,envelope.get('arguments',{}))
            ref = result.get('assessment_id') if operation in {'run_assessment','get_assessment_status'} else result['lender_case_id']
            return ModuleResult(ok=True,code=result['status'],case_id=envelope['case_id'],revision=envelope['revision'],
                                borrower_id=envelope['borrower_id'],result_ref=ref,data=result)
        if operation == 'lookup_business_profile':
            raw = self.repository.company_profile(envelope['company_id'], cutoff)
            evidence = build_evidence(envelope, raw)
            return ModuleResult(ok=True, code='PROFILE_LOOKUP_COMPLETE', case_id=envelope['case_id'],
                revision=envelope['revision'], borrower_id=envelope['borrower_id'],
                result_ref=f"profile:{envelope['case_id']}:{envelope['revision']}",
                data={'profile': {'company_id':envelope['company_id'], 'borrower_id':envelope['borrower_id'], 'decision_at':envelope['decision_at'],
                                 'verified_facts':evidence['verified_facts'],
                                 'conflicts':['legal_form'] if 'LEGAL_FORM_SOURCE_CONFLICT' in evidence['data_quality']['blocking_issues'] else []}})
        matcher = self.matcher(cutoff, envelope['request'].get('legal_form'))
        selection = matcher.select(envelope['case_id'],envelope['revision'],LoanRequest.model_validate(envelope['request']),envelope['verified_facts'],now=cutoff)
        ref = f'products:{selection.case_id}:{selection.revision}:{selection.context_hash}'
        if operation=='get_product_candidates':
            data={'selection':selection.model_dump(mode='json')}
        elif operation=='get_data_requirements':
            if envelope['result_refs'].get('products') != ref:
                return ModuleResult(ok=False,code='STALE_PRODUCT_SELECTION',case_id=selection.case_id,revision=selection.revision,borrower_id=selection.borrower_id)
            data={'requirements':matcher.requirements(selection).model_dump(mode='json')}
            ref='requirements:'+ref
        else:
            if not any(PRODUCT_CODES.get(route['product_id']) for route in envelope.get('product_routes', [])):
                return ModuleResult(ok=False,code='UNSUPPORTED_DATABASE_ROUTE',case_id=selection.case_id,revision=selection.revision,borrower_id=selection.borrower_id)
            data={'snapshot':self.preparation.collect(envelope)}
            # Scope and route IDs are persisted under advisory transaction locks.
            ref=f"evidence:{selection.case_id}:{selection.revision}:"+','.join(str(value) for value in data['snapshot'].get('snapshot_ids',{}).values())
        return ModuleResult(ok=True,code='SNAPSHOT_READY' if operation=='request_evidence' else 'PRODUCTS_READY' if operation=='get_product_candidates' else 'REQUIREMENTS_READY',case_id=selection.case_id,revision=selection.revision,borrower_id=selection.borrower_id,result_ref=ref,data=data)
