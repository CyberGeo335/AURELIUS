from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ..agents.workflow import WorkflowApp
from ..schemas.models import ActorContext, Case, Extraction, LoanRequest, MessageInput
from ..services.product_matching import ProductMatcher, ProductModuleAdapter, load_catalog
from .test_workflow import ScriptedExtractor

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


def request(**patch):
    return LoanRequest(borrower_id='PETYA-IP', legal_form='IP', purpose='INVENTORY', amount_rub=3000000, term_months=24, **patch)


def approved_catalog():
    catalog = load_catalog().model_copy(deep=True)
    card = catalog.products[0]
    card.approved = True
    card.effective_from, card.effective_until = date(2020, 1, 1), date(2040, 1, 1)
    card.rules = [rule for rule in card.rules if rule.code in {'LEGAL_FORM', 'AMOUNT'}]
    card.rules[0].allowed = ['IP', 'OOO']
    card.rules[1].minimum, card.rules[1].maximum = 100000, 10000000
    catalog.products = [card]
    catalog.version = 'TEST-APPROVED-ONLY'
    return catalog


def select(req=None, catalog=None, facts=None):
    return ProductMatcher(catalog).select('CASE-1', 1, req or request(), facts or [], now=NOW)


@pytest.mark.parametrize('need,expected', [
    ('ONE_TIME_PURCHASE', {'term'}), ('REPEATED_PURCHASES', {'rcl'}), ('CASH_GAP', {'overdraft'}),
    ('MARKETPLACE', {'sellers'}), ('VEHICLE', {'auto','leasing'}), ('PREMISES', {'mortgage'}),
    ('PROPERTY_BACKED', {'secured'}), ('REFINANCING', {'refinance'}), ('CONTRACT_SECURITY', {'guarantee'}),
    ('DEFERRED_PAYMENT', {'factoring'}), ('STATE_SUPPORT', {'state'}), ('CARD_EXPENSES', {'card'}),
    ('SMALL_TRANCHES', {'start'}), ('RESERVE', {'limit'}), ('PARTNER_PURCHASE', {'partner'}),
    ('EQUIPMENT_USE', {'leasing'}),
])
def test_every_product_route_has_reasons_checks_and_documents(need, expected):
    result = select(request(financing_need=need))
    assert {item.product_id for item in result.candidates} == expected
    assert result.status == 'PRODUCTS_READY' and result.next_module == 3
    assert all(item.reasons and item.requirements and item.checks and item.source_version for item in result.candidates)
    assert all(item.eligibility == 'UNKNOWN' for item in result.candidates)


def test_inventory_recurrence_and_priorities():
    first = select()
    assert [item.product_id for item in first.candidates] == ['term', 'rcl']
    assert [item.product_id for item in select(request(recurring=False)).candidates] == ['term']
    assert select(request(recurring=True)).candidates[0].product_id == 'rcl'
    ambiguous = select(request(recurring=False, financing_need='REPEATED_PURCHASES'))
    assert ambiguous.candidates[0].checks[0].status == 'UNKNOWN'


def test_match_no_match_unknown_and_partial_boundaries():
    catalog = approved_catalog()
    assert select(catalog=catalog).candidates[0].eligibility == 'MATCH'
    req = request().model_copy(update={'amount_rub': 11000000})
    result = select(req, catalog)
    assert result.candidates[0].eligibility == 'NO_MATCH' and result.next_module is None
    assert result.status == 'NEEDS_CLARIFICATION'
    catalog.products[0].rules[1].minimum = None
    assert select(catalog=catalog).candidates[0].eligibility == 'UNKNOWN'
    catalog.products[0].rules[1].unbounded_minimum = True
    assert select(catalog=catalog).candidates[0].eligibility == 'MATCH'
    catalog.products[0].effective_until = date(2025, 1, 1)
    assert select(req, catalog).candidates[0].eligibility == 'UNKNOWN'


def fact(value, **changes):
    return {'field':'business_age_months','value':value,'borrower_id':'PETYA-IP','scope':'PRODUCT_MATCHING',
            'source_ref':'fixture:registry','confirmed':True,'verified_at':(NOW-timedelta(days=1)).isoformat(),
            'valid_until':(NOW+timedelta(days=1)).isoformat(), **changes}


def test_verified_profiles_require_scope_validity_source_and_no_conflicts():
    catalog = approved_catalog()
    from ..schemas.products import ProductRule
    catalog.products[0].rules.append(ProductRule(code='AGE', label='Возраст', field='business_age_months', minimum=6, unbounded_maximum=True, verified_only=True))
    req = request(business_age_months=12)
    assert select(req, catalog).candidates[0].eligibility == 'UNKNOWN'
    assert select(req, catalog, [fact(12)]).candidates[0].eligibility == 'MATCH'
    assert select(req, catalog, [fact(2)]).candidates[0].eligibility == 'NO_MATCH'
    for invalid in [fact(12, borrower_id='OTHER'), fact(12, scope='OTHER'), fact(12, confirmed=False), fact(12, source_ref=''), fact(12, valid_until=(NOW-timedelta(hours=1)).isoformat()),fact(12,verified_at=(NOW+timedelta(hours=1)).isoformat())]:
        assert select(req, catalog, [invalid]).candidates[0].eligibility == 'UNKNOWN'
    assert select(req, catalog, [fact(12),fact(2)]).candidates[0].eligibility == 'UNKNOWN'


def test_specialized_requirements_and_deduplication():
    matcher = ProductMatcher()
    result = select(request(financing_need='VEHICLE'))
    requirements = matcher.requirements(result)
    assert {route['process'] for route in requirements.routes} == {'CREDIT','LEASING'}
    codes = [item.code for item in requirements.documents]
    assert len(codes) == len(set(codes)) and {'VEHICLE','LEASE'} <= set(codes)
    assert select(request(financing_need='DEFERRED_PAYMENT')).candidates[0].process == 'FACTORING'
    assert select(request(financing_need='CONTRACT_SECURITY')).candidates[0].process == 'GUARANTEE'
    bad = load_catalog().model_dump()
    bad['products'].append(bad['products'][0])
    from ..schemas.products import ProductCatalog
    with pytest.raises(ValidationError):
        ProductCatalog.model_validate(bad)


def test_term_clocks_are_not_conflated():
    card = load_catalog().products[2]
    assert card.contract_term_months != {} and card.tranche_term_days != {} and card.drawdown_period_days != {}
    check = next(item for item in card.rules if item.code == 'TRANCHE_TERM')
    assert check.field == 'operating_cycle_days' and check.maximum is None


def context():
    return ActorContext(actor_id='petya', active_borrower_id='PETYA-IP', allowed_borrower_ids=['PETYA-IP'])


def message(mid, text='Я ИП, 3000000 на товар на 24 месяца'):
    return MessageInput(session_id='module-2-test',message_id=mid,text=text)


def full_extraction(text):
    fields={'legal_form':'IP','purpose':'INVENTORY','amount_rub':3000000,'term_months':24}
    return Extraction(patch=LoanRequest(**fields),evidence={field:text for field in fields})


def test_workflow_persists_product_results_replays_and_invalidates_revision(tmp_path):
    first_message = message('1')
    extractor = ScriptedExtractor(full_extraction(first_message.text), Extraction(intent='STATUS'),
        Extraction(patch=LoanRequest(financing_need='REPEATED_PURCHASES',recurring=True), evidence={'financing_need':'Закупки постоянные','recurring':'Закупки постоянные'}))
    path = tmp_path/'m2.db'
    with WorkflowApp(path,extractor=extractor) as app:
        first = app.handle(first_message,context())
        assert first.next_module == 3 and first.status == 'WAITING_DOCUMENTS'
        assert first.error_code == 'MODULE_NOT_CONFIGURED'  # module 3, not consent solicitation
        assert first.product_selection.status == 'PRODUCTS_READY' and first.product_requirements
        assert app.handle(first_message,context()) == first and extractor.calls == 1
        second = app.handle(message('2','Статус'),context())
        assert second.product_selection == first.product_selection
        assert 'get_product_candidates' not in [item.tool_name for item in second.tool_traces]
        third = app.handle(message('3','Закупки постоянные'),context())
        assert third.revision == first.revision+1
        assert third.product_selection.candidates[0].product_id == 'rcl'
        assert third.result_refs['products'] != first.result_refs['products']
    with WorkflowApp(path,extractor=ScriptedExtractor(Extraction(intent='STATUS'))) as app:
        restored = app.handle(message('4','Статус'),context())
        assert restored.case_id == first.case_id and restored.product_selection == third.product_selection


def test_no_route_requests_clarification_and_does_not_invoke_module_3(tmp_path):
    text=message('1').text
    extraction=full_extraction(text)
    extraction.patch.purpose='OTHER'
    with WorkflowApp(tmp_path/'none.db',extractor=ScriptedExtractor(extraction,Extraction(intent='STATUS'))) as app:
        first=app.handle(message('1'),context())
        second=app.handle(message('2','Статус'),context())
        assert first.next_action == second.next_action == 'CLARIFY_PRODUCT_NEED'
        assert first.status == second.status == 'NEEDS_INPUT' and not first.product_requirements
        assert 'request_evidence' not in [trace.tool_name for trace in second.tool_traces]


def test_catalog_and_confirmed_facts_trigger_reevaluation_without_new_request(tmp_path):
    catalog=approved_catalog()
    adapter=ProductModuleAdapter(ProductMatcher(catalog))
    with WorkflowApp(tmp_path/'refresh.db',extractor=ScriptedExtractor(full_extraction(message('1').text),Extraction(intent='STATUS')),adapter=adapter) as app:
        first=app.handle(message('1'),context())
        assert first.product_selection.candidates[0].eligibility == 'MATCH'
        adapter.matcher.catalog.products[0].rules[1].maximum=1000000
        second=app.handle(message('2','Статус'),context())
        assert second.revision == first.revision and second.product_selection.context_hash != first.product_selection.context_hash
        assert second.product_selection.candidates[0].eligibility == 'NO_MATCH'
        assert second.next_action == 'CLARIFY_PRODUCT_NEED'


def test_legacy_cases_load_new_fields_as_unknown():
    case=Case.model_validate({'owner_id':'legacy','request':{'purpose':'INVENTORY'}})
    assert case.product_selection is None and case.request.financing_need is None


def test_new_confirmed_facts_recompute_same_revision(tmp_path):
    from ..schemas.products import ProductRule
    catalog=approved_catalog()
    catalog.products[0].rules.append(ProductRule(code='AGE',label='Возраст бизнеса',field='business_age_months',minimum=6,unbounded_maximum=True,verified_only=True))
    adapter=ProductModuleAdapter(ProductMatcher(catalog))
    with WorkflowApp(tmp_path/'facts.db',extractor=ScriptedExtractor(full_extraction(message('1').text),Extraction(intent='STATUS')),adapter=adapter) as app:
        first=app.handle(message('1'),context())
        assert first.product_selection.candidates[0].eligibility=='UNKNOWN'
        case=app.repository.load(first.case_id,context())
        current=datetime.now(timezone.utc)
        case.verified_facts=[fact(2,verified_at=(current-timedelta(hours=1)).isoformat(),valid_until=(current+timedelta(hours=1)).isoformat())]
        app.repository.commit(case,case.storage_version,message('trusted-update'),first)
        second=app.handle(message('2','Статус'),context())
        assert second.revision==first.revision
        assert second.product_selection.context_hash!=first.product_selection.context_hash
        assert second.product_selection.candidates[0].eligibility=='NO_MATCH'
        assert second.next_action=='CLARIFY_PRODUCT_NEED'
