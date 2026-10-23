"""Module 2: deterministic, versioned routing and three-valued formal checks."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..schemas.models import Case, LoanRequest, ModuleResult
from ..schemas.products import ConditionCheck, DataRequirements, ProductCandidate, ProductCatalog, ProductSelection
from .workflow_service import ModuleUnavailable

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'catalog/products.json'
PROFILE_FIELDS = {'legal_form', 'business_age_months', 'monthly_revenue_rub', 'operating_cycle_days', 'has_collateral'}


def load_catalog(path: Path = CATALOG_PATH) -> ProductCatalog:
    return ProductCatalog.model_validate_json(path.read_text())


def confirmed_profile(facts: list[dict], borrower_id: str, now: datetime) -> dict:
    """Ignore stale, foreign, conflicting and unscoped facts. Chat cannot confirm facts."""
    values = {}
    for fact in facts:
        try:
            field = fact['field']
            if field not in PROFILE_FIELDS or fact.get('borrower_id') != borrower_id or fact.get('scope') != 'PRODUCT_MATCHING' or fact.get('confirmed') is not True or not fact.get('source_ref'):
                continue
            verified = datetime.fromisoformat(fact['verified_at'])
            until = datetime.fromisoformat(fact['valid_until'])
            if verified.tzinfo is None or until.tzinfo is None or not verified <= now < until:
                continue
            value = fact['value']
            if field == 'has_collateral' and type(value) is not bool:
                continue
            if field == 'legal_form' and value not in {'IP', 'OOO', 'AO', 'OTHER'}:
                continue
            if field not in {'has_collateral', 'legal_form'} and (type(value) is not int or value < 0):
                continue
            values.setdefault(field, []).append(value)
        except (KeyError, ValueError, TypeError):
            continue
    return {field: items[0] if all(value == items[0] for value in items) else None for field, items in values.items()}


def context_hash(request: LoanRequest, facts: list[dict], catalog: ProductCatalog, now: datetime) -> str:
    payload = {'request': request.model_dump(mode='json'), 'profile': confirmed_profile(facts, request.borrower_id, now),
               'catalog': catalog.model_dump(mode='json'), 'day': now.date().isoformat()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def structural_needs(request: LoanRequest) -> dict[str, tuple[str, int, str]]:
    if request.financing_need:
        if (request.financing_need == 'REPEATED_PURCHASES' and request.recurring is False) or (request.financing_need == 'ONE_TIME_PURCHASE' and request.recurring is True):
            return {request.financing_need: ('UNKNOWN', 0, 'Сведения о повторяемости противоречат характеру потребности; уточнить')}
        return {request.financing_need: ('MATCH', 0, 'Явно указан характер потребности')}
    if request.purpose == 'INVENTORY':
        if request.recurring is True:
            return {'REPEATED_PURCHASES': ('MATCH', 0, 'Повторяющиеся закупки'), 'ONE_TIME_PURCHASE': ('UNKNOWN', 2, 'Разовую выдачу нужно подтвердить как альтернативу')}
        if request.recurring is False:
            return {'ONE_TIME_PURCHASE': ('MATCH', 0, 'Разовая закупка')}
        return {'ONE_TIME_PURCHASE': ('MATCH', 0, 'Закупка товара; разовый характер нужно уточнить'), 'REPEATED_PURCHASES': ('UNKNOWN', 1, 'Уточнить повторяемость закупок и оборотный цикл')}
    mapping = {'WORKING_CAPITAL': 'DEVELOPMENT', 'INVESTMENT': 'DEVELOPMENT', 'REAL_ESTATE': 'PREMISES',
               'VEHICLE': 'VEHICLE', 'REFINANCING': 'REFINANCING', 'GUARANTEE': 'CONTRACT_SECURITY'}
    if request.purpose in mapping:
        return {mapping[request.purpose]: ('MATCH', 0, 'Семейство соответствует заявленной цели')}
    return {}


class ProductMatcher:
    def __init__(self, catalog: ProductCatalog | None = None):
        self.catalog = catalog or load_catalog()

    def select(self, case_id: str, revision: int, request: LoanRequest, facts: list[dict], *, now: datetime | None = None) -> ProductSelection:
        now = now or datetime.now(timezone.utc)
        profile = confirmed_profile(facts, request.borrower_id, now)
        needs = structural_needs(request)
        candidates, excluded = [], []
        for card in self.catalog.products:
            matches = [needs[need] for need in card.needs if need in needs]
            if not matches:
                excluded.append(ConditionCheck(code=card.product_id, label=card.name, status='NO_MATCH', reason='Структура не соответствует известной потребности; можно пересмотреть после уточнения.', provenance='PROJECT_ROUTING'))
                continue
            route_status, priority, reason = sorted(matches, key=lambda item: item[1])[0]
            current = card.approved and card.effective_from is not None and card.effective_until is not None and card.effective_from <= now.date() <= card.effective_until
            checks = [ConditionCheck(code='NEED', label='Соответствие потребности', status=route_status, reason=reason, provenance='REPORTED'),
                      ConditionCheck(code='CARD_VALIDITY', label='Актуальность утверждённой карточки', status='MATCH' if current else 'UNKNOWN', reason='Версия условий действует' if current else 'Утверждённая актуальная карточка не подтверждена; рекламная ссылка не задаёт пороги.', provenance='CATALOG')]
            for rule in card.rules:
                verified = rule.field in profile
                value = profile.get(rule.field, getattr(request, rule.field, None))
                bounds = {'minimum': rule.minimum, 'maximum': rule.maximum, 'allowed': rule.allowed, 'expected_bool': rule.expected_bool}
                known_rule = rule.allowed is not None or rule.expected_bool is not None or rule.minimum is not None or rule.maximum is not None
                status, explanation = 'UNKNOWN', 'Недостаточно данных или неизвестно продуктовое условие'
                if verified and value is None:
                    explanation = 'Подтверждённые источники противоречат друг другу; значение требует уточнения'
                if current and known_rule and value is not None:
                    if rule.verified_only and not verified:
                        explanation = 'Есть только сведения клиента; требуется подтверждение профильным источником'
                    else:
                        passed = True
                        if rule.allowed is not None:
                            passed = value in rule.allowed
                        elif rule.expected_bool is not None:
                            passed = type(value) is bool and value is rule.expected_bool
                        elif type(value) is int:
                            passed = (rule.minimum is None or value >= rule.minimum) and (rule.maximum is None or value <= rule.maximum)
                        else:
                            passed = None
                        if passed is not None:
                            complete = rule.allowed is not None or rule.expected_bool is not None or ((rule.minimum is not None or rule.unbounded_minimum) and (rule.maximum is not None or rule.unbounded_maximum))
                            status = 'NO_MATCH' if not passed else 'MATCH' if complete else 'UNKNOWN'
                            explanation = 'Известное условие выполнено' if status == 'MATCH' else 'Неизвестна одна из границ условия' if status == 'UNKNOWN' else 'Известное формальное ограничение не выполнено; это не банковский отказ'
                checks.append(ConditionCheck(code=rule.code, label=rule.label, status=status, reason=explanation, actual=value, expected=bounds, provenance='VERIFIED' if verified else 'REPORTED' if value is not None else 'UNKNOWN'))
            eligibility = 'NO_MATCH' if any(check.status == 'NO_MATCH' for check in checks) else 'UNKNOWN' if any(check.status == 'UNKNOWN' for check in checks) else 'MATCH'
            candidates.append(ProductCandidate(product_id=card.product_id, product_family=card.product_family, name=card.name,
                process=card.process, eligibility=eligibility, priority=priority, reasons=[reason], checks=checks,
                missing_checks=[check.code for check in checks if check.status == 'UNKNOWN'], limitations=card.limitations,
                requirements=card.requirements, requirements_ref=f'REQ:{card.product_id}:{card.rule_version}',
                source_url=card.source_url, source_version=card.source_version, rule_version=card.rule_version))
        candidates.sort(key=lambda item: (item.eligibility == 'NO_MATCH', item.priority, item.product_id))
        viable = any(item.eligibility != 'NO_MATCH' for item in candidates)
        return ProductSelection(case_id=case_id, revision=revision, borrower_id=request.borrower_id, evaluated_at=now,
            status='PRODUCTS_READY' if viable else 'NEEDS_CLARIFICATION', catalog_version=self.catalog.version,
            context_hash=context_hash(request, facts, self.catalog, now), candidates=candidates, excluded=excluded,
            next_module=3 if viable else None,
            clarification=None if viable else 'Уточните характер потребности или измените известные ограничения. Подходящий маршрут пока не установлен; это не кредитный отказ.')

    def requirements(self, selection: ProductSelection) -> DataRequirements:
        documents, routes = {}, []
        for candidate in selection.candidates:
            if candidate.eligibility == 'NO_MATCH':
                continue
            routes.append({'product_id': candidate.product_id, 'process': candidate.process, 'requirements_ref': candidate.requirements_ref,
                           'missing_checks': candidate.missing_checks, 'documents': [item.code for item in candidate.requirements]})
            for document in candidate.requirements:
                documents.setdefault(document.code, document)
        return DataRequirements(case_id=selection.case_id, revision=selection.revision, catalog_version=selection.catalog_version,
            product_selection_ref=f'products:{selection.case_id}:{selection.revision}:{selection.context_hash}',
            routes=routes, documents=list(documents.values()))


class ProductModuleAdapter:
    """Pure/read-only module 2 operations; modules 3–5 remain unavailable."""
    def __init__(self, matcher: ProductMatcher | None = None):
        self.matcher = matcher or ProductMatcher()

    def supports(self, operation: str) -> bool:
        return operation in {'get_product_candidates', 'get_data_requirements'}

    def needs_refresh(self, case: Case) -> bool:
        selection = case.product_selection
        return selection is None or selection.context_hash != context_hash(case.request, case.verified_facts, self.matcher.catalog, datetime.now(timezone.utc))

    def call(self, operation: str, envelope: dict, idempotency_key: str) -> ModuleResult:
        if not self.supports(operation):
            raise ModuleUnavailable(operation)
        request = LoanRequest.model_validate(envelope['request'])
        selection = self.matcher.select(envelope['case_id'], envelope['revision'], request, envelope.get('verified_facts', []))
        ref = f'products:{selection.case_id}:{selection.revision}:{selection.context_hash}'
        if operation == 'get_product_candidates':
            data = {'selection': selection.model_dump(mode='json')}
        else:
            if envelope['result_refs'].get('products') != ref:
                return ModuleResult(ok=False, code='STALE_PRODUCT_SELECTION', case_id=selection.case_id, revision=selection.revision, borrower_id=selection.borrower_id)
            requirements = self.matcher.requirements(selection)
            data, ref = {'requirements': requirements.model_dump(mode='json')}, 'requirements:' + ref
        return ModuleResult(ok=True, code='PRODUCTS_READY' if operation == 'get_product_candidates' else 'REQUIREMENTS_READY',
            case_id=selection.case_id, revision=selection.revision, borrower_id=selection.borrower_id, result_ref=ref, data=data)
