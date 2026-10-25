"""Domain/contract regression for the new workflow; no Ollama, HTTP or business DB."""
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import Extraction, LoanRequest
from personalCab.prom_v2.agent import Agent
from personalCab.prom_v2.models import Action, Actor, Command, Grant, Scope, utcnow
from personalCab.prom_v2.repository import AccessDenied, Conflict, MemoryRepository


def test_legacy_payload_with_advanced_cutoff_cannot_reuse_its_offer():
    from personalCab.prom_v2.models import Case
    now = utcnow()
    case = Case(case_id='legacy-stale',owner_id='client',company_id=40,borrower_id='business',
                request=LoanRequest(borrower_id='business'),status='ACCEPTED',
                data_cutoff_at=now,data_context={'decision_at':(now-timedelta(minutes=1)).isoformat()},
                assessment={'assessment_id':'old'},bank_application={'offer':{'offer_id':'old'}})
    assert case.evidence_stale
    agent = Agent(MemoryRepository())
    view = agent._view(Actor(actor_id='client',company_id=40,borrower_id='business'),case,agent._question(case))
    assert view.evidence_stale and view.assessment is None and view.bank_application is None


def test_dependent_inn_conflict_and_corrected_value_clear(setup):
    result=send(setup,'UPDATE_REQUEST',arguments={'patch':{'legal_form':'IP','inn':'771234567890','amount_rub':1500000}})
    result=send(setup,'UPDATE_REQUEST',arguments={'patch':{'legal_form':'OOO'}})
    assert any(g.field=='inn' and g.status=='CONFLICT' for g in result.data_resolution.gaps)
    result=send(setup,'UPDATE_REQUEST',arguments={'patch':{'legal_form':'IP'}})
    assert not any(g.field=='inn' for g in result.data_resolution.gaps)
    result=send(setup,'UPDATE_REQUEST',arguments={'patch':{'amount_rub':-100}})
    assert result.status=='NEEDS_INFO'
    result=send(setup,'UPDATE_REQUEST',arguments={'patch':{'amount_rub':1500000}})
    assert result.status=='DRAFT' and not any(g.field=='amount_rub' for g in result.data_resolution.gaps)


def test_action_policy_projects_the_same_denials_it_executes(setup):
    actor,agent,_,created=setup
    class Modules:
        def supports(self, action):return True
        def execute(self,*args):raise AssertionError('Denied actions must not call a service')
    agent.modules=Modules()
    view=agent.state(actor,created.case_id)
    assert 'ASSESS' not in view.allowed_actions
    assert 'ASSESS' in view.action_reasons
    denied=send(setup,'ASSESS')
    assert denied.error_code=='CONSENT_REQUIRED' and denied.allowed_actions==view.allowed_actions


@pytest.fixture
def setup():
    actor = Actor(actor_id="client-v2", company_id=40, borrower_id="business-40")
    repository = MemoryRepository()
    agent = Agent(repository)
    created = agent.handle(actor, Command(request_id="create", action="CREATE", expected_version=0))
    return actor, agent, repository, created


def send(setup, action, *, arguments=None, text="", view=None, request_id=None):
    actor, agent, _, created = setup
    current = view or agent.state(actor, created.case_id)
    return agent.handle(actor, Command(request_id=request_id or uuid4().hex, action=action,
                                      case_id=current.case_id, expected_version=current.version,
                                      arguments=arguments or {}, text=text))


def test_create_is_idempotent_and_not_a_business_application(setup):
    actor, agent, _, created = setup
    assert agent.handle(actor, Command(request_id="create", action="CREATE", expected_version=0)) == created
    assert len(agent.cases(actor)) == 1
    assert created.request.borrower_id == actor.borrower_id
    assert created.assessment is None and created.bank_application is None


def test_receipt_precedes_version_check_and_rejects_different_input(setup):
    args = {"patch": {"amount_rub": 1500000}}
    first = send(setup, "UPDATE_REQUEST", arguments=args, view=setup[3], request_id="edit")
    assert send(setup, "UPDATE_REQUEST", arguments=args, view=setup[3], request_id="edit") == first
    with pytest.raises(Conflict, match="REQUEST_ID_REUSED"):
        send(setup, "UPDATE_REQUEST", arguments={"patch": {"amount_rub": 2000000}}, view=setup[3], request_id="edit")
    with pytest.raises(Conflict, match="STALE_CASE_VERSION"):
        send(setup, "UPDATE_REQUEST", arguments=args, view=setup[3])


def test_invalid_field_preserves_value_and_accepts_valid_sibling(setup):
    original = send(setup, "UPDATE_REQUEST", arguments={"patch": {"amount_rub": 1500000}})
    result = send(setup, "UPDATE_REQUEST", arguments={"patch": {"amount_rub": -100, "term_months": 18}})
    assert result.request.amount_rub == original.request.amount_rub
    assert result.request.term_months == 18 and result.revision == original.revision + 1
    assert any(gap.field == "amount_rub" and gap.status == "INVALID" for gap in result.data_resolution.gaps)
    fixed = send(setup, "UPDATE_REQUEST", arguments={"patch": {"amount_rub": 1600000}})
    assert not any(gap.field == "amount_rub" for gap in fixed.data_resolution.gaps)


@pytest.mark.parametrize("value", [True, "1500000", 1.5])
def test_strict_form_values(setup, value):
    result = send(setup, "UPDATE_REQUEST", arguments={"patch": {"amount_rub": value}})
    assert result.request.amount_rub is None
    assert result.data_resolution.gaps[0].status == "INVALID"


def test_quote_backed_proposal_needs_confirmation_and_is_invalidated_by_form(setup):
    class Extractor:
        def extract(self, text, case):
            return Extraction(patch=LoanRequest(amount_rub=1500000), evidence={"amount_rub": text})

    setup[1].extractor = Extractor()
    proposed = send(setup, "CHAT", text="Нужно 1500000 рублей")
    assert proposed.request.amount_rub is None and proposed.pending.patch["amount_rub"] == 1500000
    confirmed = send(setup, "CONFIRM_FACTS", arguments={"proposal_id": proposed.pending.proposal_id})
    assert confirmed.request.amount_rub == 1500000 and confirmed.pending is None
    proposed = send(setup, "CHAT", text="Нужно 2000000 рублей")
    # The fake extractor contradicts the numeric quote; there must be no usable proposal.
    assert proposed.pending is None
    assert any(gap.field == "amount_rub" for gap in proposed.data_resolution.gaps)


def test_old_proposal_cannot_override_newer_form(setup):
    class Extractor:
        def extract(self, text, case):
            return Extraction(patch=LoanRequest(term_months=12), evidence={"term_months": text})

    setup[1].extractor = Extractor()
    proposal = send(setup, "CHAT", text="На 12 месяцев")
    send(setup, "UPDATE_REQUEST", arguments={"patch": {"term_months": 24}})
    with pytest.raises(Conflict, match="STALE_PROPOSAL"):
        send(setup, "CONFIRM_FACTS", arguments={"proposal_id": proposal.pending.proposal_id})


def test_rag_preserves_unconfirmed_proposal_and_current_legal_form(setup):
    class Extractor:
        def extract(self, text, case):
            return Extraction(patch=LoanRequest(amount_rub=1500000), evidence={"amount_rub": text})

    send(setup, "UPDATE_REQUEST", arguments={"patch": {"legal_form": "IP"}})
    setup[1].extractor = Extractor()
    proposal = send(setup, "CHAT", text="Нужно 1500000 рублей")
    answer = send(setup, "CHAT", text="Какой формат ИНН для R01 ООО?")
    assert answer.pending == proposal.pending
    assert answer.request.legal_form == "IP" and answer.revision == proposal.revision


def test_form_inn_and_legal_form_mismatch_is_not_accepted(setup):
    result = send(setup, "UPDATE_REQUEST", arguments={"patch": {"inn": "123456789012", "legal_form": "OOO"}})
    assert result.request.legal_form == "OOO" and result.request.inn is None
    assert any(gap.field == "inn" and gap.status == "INVALID" for gap in result.data_resolution.gaps)


def test_unquoted_extraction_never_changes_request(setup):
    class Extractor:
        def extract(self, text, case):
            return Extraction(patch=LoanRequest(amount_rub=1500000), evidence={"amount_rub": "другая фраза"})

    setup[1].extractor = Extractor()
    result = send(setup, "CHAT", text="Нужны деньги на товар")
    assert result.pending is None and result.request.amount_rub is None
    assert any(gap.status == "UNGROUNDED" for gap in result.data_resolution.gaps)


def test_rag_bypasses_extraction_and_preserves_request_proposal_revision(setup):
    class ForbiddenExtractor:
        def extract(self, text, case):
            raise AssertionError("RAG must not call the model")

    setup[1].extractor = ForbiddenExtractor()
    before = send(setup, "UPDATE_REQUEST", arguments={"patch": {"amount_rub": 1500000}})
    answer = send(setup, "CHAT", text="Объясни поле R01_06", request_id="rag")
    assert answer.knowledge_answer.status == "FOUND"
    assert answer.knowledge_answer.source_sha256 and answer.knowledge_answer.citations
    assert any(hit.target_db_field == "credit_applications.requested_term_months" for hit in answer.knowledge_answer.citations)
    assert answer.request == before.request and answer.revision == before.revision
    assert answer.version == before.version + 1
    restored = setup[1].state(setup[0], answer.case_id)
    assert restored.last_knowledge_answer == answer.knowledge_answer
    assert setup[1].handle(setup[0], Command(request_id="rag", action="CHAT", text="Объясни поле R01_06",
                                          case_id=before.case_id, expected_version=before.version)) == answer


def test_missing_model_does_not_block_form_or_rag(setup):
    offline = send(setup, "CHAT", text="Нужно финансирование")
    assert offline.error_code == "EXTRACTION_UNAVAILABLE"
    form = send(setup, "UPDATE_REQUEST", arguments={"patch": {"term_months": 12}})
    assert form.request.term_months == 12
    assert send(setup, "CHAT", text="Какие требования к ИНН R02 для ООО?").knowledge_answer.status == "FOUND"


@pytest.mark.parametrize("change", [{"actor_id": "other"}, {"company_id": 41}, {"borrower_id": "business-41"}])
def test_subject_isolation(setup, change):
    actor = setup[0].model_copy(update=change)
    with pytest.raises(AccessDenied):
        setup[1].state(actor, setup[3].case_id)
    assert setup[1].cases(actor) == []


def test_identity_and_consent_cannot_be_supplied_by_command(setup):
    with pytest.raises(ValueError):
        send(setup, "UPDATE_REQUEST", arguments={"patch": {"borrower_id": "other"}})
    with pytest.raises(ValidationError):
        Command(request_id="hack", action="CANCEL", case_id=setup[3].case_id, expected_version=1, role="OPERATOR")
    with pytest.raises(AccessDenied):
        setup[1].handle(setup[0].model_copy(update={"role": "READER"}), Command(request_id="read", action="CANCEL", case_id=setup[3].case_id, expected_version=1))


def test_product_mapping_and_unsupported_routes_are_explicit(setup):
    from personalCab.prom_v2.adapters import CatalogProducts
    catalog = CatalogProducts().matcher.catalog
    assert len(catalog.products) == 16
    assert sum(card.database_supported for card in catalog.products) == 3
    result = send(setup, "UPDATE_REQUEST", arguments={"patch": {"legal_form": "IP", "amount_rub": 1500000,
                                                                               "term_months": 12, "purpose": "VEHICLE", "financing_need": "VEHICLE"}})
    candidate = next(item for item in result.product_selection.candidates if not item.database_supported and item.eligibility != "NO_MATCH")
    selected = send(setup, "SELECT_PRODUCT", arguments={"product_id": candidate.product_id})
    assert selected.selected_product_id == candidate.product_id
    assert selected.error_code == "DATABASE_ROUTE_UNSUPPORTED"
    assert all(item.eligibility != "MATCH" for item in selected.product_selection.candidates)


def test_unavailable_business_module_is_engineering_not_rejection(setup):
    result = send(setup, "ASSESS")
    assert result.error_code == "SERVICE_NOT_CONFIGURED"
    assert result.status == "DRAFT" and result.assessment is None
    assert any(gap.resolution == "ENGINEERING" for gap in result.data_resolution.gaps)


def test_business_action_needs_live_consent_even_if_adapter_exists(setup):
    class Adapter:
        def supports(self, action):
            return True

        def execute(self, actor, case, command):
            pytest.fail("No consent: must not invoke adapter")

    setup[1].modules = Adapter()
    assert send(setup, "REFRESH_EVIDENCE").error_code == "CONSENT_REQUIRED"
    at = utcnow()
    expired = Grant(scope="EVIDENCE_COLLECTION", granted_at=at - timedelta(hours=2), expires_at=at - timedelta(hours=1))
    revoked = Grant(scope="EVIDENCE_COLLECTION", granted_at=at - timedelta(minutes=1), expires_at=at + timedelta(hours=1), revoked=True)
    for grant in (expired, revoked):
        assert not setup[0].model_copy(update={"grants": [grant]}).permits(Scope.EVIDENCE_COLLECTION, at)


def test_business_result_from_another_case_rolls_back(setup):
    class Adapter:
        def supports(self, action):
            return action == "REFRESH_EVIDENCE"

        def execute(self, actor, case, command):
            return {"case_id": "another-case", "revision": case.revision,
                    "company_id": case.company_id, "borrower_id": case.borrower_id, "data_context": {}}

    actor, agent, repository, _ = setup
    at = utcnow()
    actor = actor.model_copy(update={"grants": [Grant(scope="EVIDENCE_COLLECTION", granted_at=at-timedelta(minutes=1), expires_at=at+timedelta(hours=1))]})
    agent.modules = Adapter()
    view = send(setup, "UPDATE_REQUEST", arguments={"patch": {"legal_form": "IP", "purpose": "INVENTORY", "amount_rub": 1500000, "term_months": 12}})
    selected = send(setup, "SELECT_PRODUCT", arguments={"product_id": "term"})
    before = repository.get(actor, selected.case_id)
    with pytest.raises(ValueError, match="scope mismatch"):
        agent.handle(actor, Command(request_id="foreign-output", action="REFRESH_EVIDENCE", case_id=selected.case_id, expected_version=selected.version))
    assert repository.get(actor, selected.case_id) == before


def test_failed_transaction_does_not_save_a_case_or_receipt(setup):
    actor, agent, repository, created = setup
    before = repository.get(actor, created.case_id)
    with pytest.raises(ValueError):
        send(setup, "SELECT_PRODUCT", arguments={"product_id": "does-not-exist"}, request_id="retryable")
    assert repository.get(actor, created.case_id) == before
    assert send(setup, "CANCEL", request_id="retryable").status == "CANCELLED"


def test_explicit_case_target_survives_another_case_in_same_actor(setup):
    actor, agent, _, first = setup
    second = agent.handle(actor, Command(request_id="create-second", action="CREATE", expected_version=0))
    send(setup, "UPDATE_REQUEST", arguments={"patch": {"amount_rub": 1000000}}, view=first)
    assert agent.state(actor, first.case_id).request.amount_rub == 1000000
    assert agent.state(actor, second.case_id).request.amount_rub is None


def test_cancel_is_explicit_and_new_case_preserves_closed_history(setup):
    cancelled = send(setup, "CANCEL")
    assert cancelled.status == "CANCELLED"
    rejected = send(setup, "UPDATE_REQUEST", arguments={"patch": {"amount_rub": 1000000}})
    assert rejected.error_code == "CASE_CLOSED" and rejected.request.amount_rub is None
    second = setup[1].handle(setup[0], Command(request_id="new-case", action="CREATE", expected_version=0))
    assert second.case_id != cancelled.case_id
    assert len(setup[1].cases(setup[0])) == 2
