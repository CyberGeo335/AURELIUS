from __future__ import annotations

from ..schemas.evidence import EvidenceSummary
from ..schemas.resolution import BusinessProfileResult, FieldProblem

from datetime import datetime
import hashlib
import json
from typing import Any, Protocol

from ..repositories.case_repository import AccessDenied, CaseRepository, ConflictError, check_access
from ..schemas.models import ActorContext, Case, Extraction, LoanRequest, ModuleResult, Scope, Status, ToolResult, utcnow
from ..schemas.products import DataRequirements, ProductSelection


class ModuleUnavailable(RuntimeError):
    pass


class ModuleAdapter(Protocol):
    def call(self, operation: str, envelope: dict[str, Any], idempotency_key: str) -> ModuleResult:
        """Mutating implementations MUST honor the stable idempotency key."""
        ...


class UnconfiguredModules:
    def call(self, operation: str, envelope: dict[str, Any], idempotency_key: str) -> ModuleResult:
        raise ModuleUnavailable(operation)


TERMINAL = {Status.COMPLETED, Status.CANCELLED}
EDITABLE = set(Status) - TERMINAL
ALLOWED_TRANSITIONS = {
    Status.DISCOVERY: {Status.DISCOVERY, Status.NEEDS_INPUT, Status.REQUEST_READY, Status.MANUAL_REVIEW, Status.CANCELLED},
    Status.NEEDS_INPUT: {Status.NEEDS_INPUT, Status.REQUEST_READY, Status.WAITING_EXTERNAL, Status.MANUAL_REVIEW, Status.CANCELLED},
    Status.REQUEST_READY: {Status.REQUEST_READY, Status.NEEDS_INPUT, Status.WAITING_DOCUMENTS, Status.WAITING_CONSENT, Status.MANUAL_REVIEW, Status.CANCELLED},
    Status.WAITING_DOCUMENTS: {Status.WAITING_DOCUMENTS, Status.REQUEST_READY, Status.NEEDS_INPUT, Status.WAITING_CONSENT, Status.WAITING_EXTERNAL, Status.MANUAL_REVIEW, Status.CANCELLED},
    Status.WAITING_CONSENT: {Status.WAITING_CONSENT, Status.REQUEST_READY, Status.NEEDS_INPUT, Status.WAITING_DOCUMENTS, Status.WAITING_EXTERNAL, Status.MANUAL_REVIEW, Status.CANCELLED},
    Status.WAITING_EXTERNAL: {Status.WAITING_EXTERNAL, Status.REQUEST_READY, Status.NEEDS_INPUT, Status.WAITING_CONSENT, Status.MANUAL_REVIEW, Status.COMPLETED, Status.CANCELLED},
    Status.MANUAL_REVIEW: {Status.MANUAL_REVIEW, Status.NEEDS_INPUT, Status.REQUEST_READY, Status.WAITING_EXTERNAL, Status.CANCELLED},
}
ALLOWED_TRANSITIONS.update({status: {status} for status in TERMINAL})


def transition(case: Case, target: Status) -> None:
    if target not in ALLOWED_TRANSITIONS[case.status]:
        raise ValueError(f"Invalid transition: {case.status} -> {target}")
    case.status = target


class ToolSession:
    """One turn's tools, bound to trusted identity, mode and the current case."""

    def __init__(self, case: Case, actor: ActorContext, repository: CaseRepository, adapter: ModuleAdapter):
        self.case, self.actor, self.repository, self.adapter = case, actor, repository, adapter

    def guard(self, operation: str) -> None:
        check_access(self.case, self.actor)
        if self.case.mode != "DEMO":
            raise AccessDenied("MODE_NOT_ALLOWED")
        if operation in {"load_case", "find_existing_application"}:
            return
        if self.actor.role not in {"BORROWER", "OPERATOR"}:
            raise AccessDenied("ROLE_NOT_ALLOWED")
        if self.case.status in TERMINAL:
            raise AccessDenied("TERMINAL_CASE")
        if operation == "update_request":
            return
        if operation == "lookup_business_profile":
            if not self.actor.company_id or not self.case.request.borrower_id:
                raise AccessDenied("COMPANY_BINDING_REQUIRED")
            if not hasattr(self.adapter, "supports") or not self.adapter.supports(operation):
                raise ModuleUnavailable(operation)
            if not self.actor.has_consent(Scope.EVIDENCE_COLLECTION, self.case.request.borrower_id):
                raise AccessDenied("CONSENT_DENIED" if Scope.EVIDENCE_COLLECTION in self.actor.denied_scopes else "CONSENT_REQUIRED")
            return
        if not self.case.request.borrower_id or self.case.missing_required:
            raise AccessDenied("INCOMPLETE_REQUEST")
        if operation in {'run_assessment','submit_application','accept_offer','execute_demo'} and self.case.pending_clarifications:
            raise AccessDenied('UNRESOLVED_CLARIFICATIONS')
        stages = {
            "get_product_candidates": {Status.REQUEST_READY},
            "get_data_requirements": {Status.REQUEST_READY},
            "request_evidence": {Status.WAITING_DOCUMENTS, Status.WAITING_CONSENT},
            "get_assessment_status": {Status.WAITING_EXTERNAL},
            "get_bank_status": {Status.WAITING_EXTERNAL},
            "run_assessment": {Status.WAITING_DOCUMENTS,Status.WAITING_EXTERNAL,Status.MANUAL_REVIEW,Status.WAITING_CONSENT,Status.NEEDS_INPUT},
            "submit_application": {Status.WAITING_DOCUMENTS,Status.WAITING_EXTERNAL,Status.MANUAL_REVIEW,Status.WAITING_CONSENT,Status.NEEDS_INPUT},
            "accept_offer": {Status.WAITING_EXTERNAL,Status.WAITING_CONSENT,Status.NEEDS_INPUT,Status.MANUAL_REVIEW},
            "execute_demo": {Status.WAITING_EXTERNAL,Status.WAITING_CONSENT,Status.NEEDS_INPUT,Status.MANUAL_REVIEW},
        }
        if operation not in stages or self.case.status not in stages[operation]:
            raise AccessDenied("INVALID_STAGE")
        dependencies = {"get_data_requirements": "products", "request_evidence": "requirements", "get_assessment_status": "assessment", "get_bank_status": "bank_application"}
        if operation in dependencies and dependencies[operation] not in self.case.result_refs:
            raise AccessDenied("MISSING_PROCESS_REFERENCE")
        if hasattr(self.adapter, "supports") and not self.adapter.supports(operation):
            raise ModuleUnavailable(operation)
        if operation == "request_evidence" and hasattr(self.adapter, "supports_evidence") and not self.adapter.supports_evidence(self.case.product_requirements.routes):
            raise AccessDenied("UNSUPPORTED_DATABASE_ROUTE")
        scope = {"request_evidence": Scope.EVIDENCE_COLLECTION, "get_assessment_status": Scope.CREDIT_ASSESSMENT,
                 "get_bank_status": Scope.BANK_STATUS,"run_assessment":Scope.CREDIT_ASSESSMENT,
                 "submit_application":Scope.APPLICATION_SUBMISSION,"accept_offer":Scope.APPLICATION_SUBMISSION,
                 "execute_demo":Scope.DEMO_EXECUTION}.get(operation)
        if operation == "request_evidence" and getattr(self.adapter, "requires_company_binding", False) and not self.actor.company_id:
            raise AccessDenied("COMPANY_BINDING_REQUIRED")
        if scope:
            if scope in self.actor.denied_scopes:
                raise AccessDenied("CONSENT_DENIED")
            if not self.actor.has_consent(scope, self.case.request.borrower_id):
                raise AccessDenied("CONSENT_REQUIRED")

    def update_request(self, patch: dict, clear_fields: list[str], *, client_reported=True) -> ToolResult:
        data = self.case.request.model_dump()
        for field in clear_fields:
            if field not in LoanRequest.model_fields:
                raise ValueError("Unknown clear field")
            data[field] = None
        data.update({key: value for key, value in LoanRequest.model_validate(patch).model_dump(exclude_none=True).items()})
        candidate = LoanRequest.model_validate(data)
        if candidate.inn:
            from .questionnaire import validate_answer
            validate_answer(candidate.inn,'text','companies.inn',candidate.legal_form)
        if candidate.borrower_id and candidate.borrower_id not in self.actor.allowed_borrower_ids:
            raise AccessDenied("SUBJECT_NOT_ALLOWED")
        old_subject = self.case.request.borrower_id
        if old_subject and candidate.borrower_id != old_subject:
            raise AccessDenied("SUBJECT_CHANGE_REQUIRES_NEW_SESSION")
        changed = candidate != self.case.request
        if changed:
            for field, value in candidate.model_dump(mode='json').items():
                previous=self.case.request.model_dump(mode='json')[field]
                if client_reported and field != 'borrower_id' and previous != value:
                    self.case.client_changes.append({'field':field,'old_value':previous,'new_value':value,
                                                     'revision':self.case.revision+int(any(v is not None for k,v in self.case.request.model_dump().items() if k!='borrower_id')),
                                                     'changed_at':utcnow().isoformat(),'review_status':'PENDING'})
            # Initial identity from the trusted session is not itself a request revision.
            had_request = any(value is not None for key, value in self.case.request.model_dump().items() if key != "borrower_id")
            if had_request:
                self.case.revision += 1
            self.case.request = candidate
            self.case.result_refs = {key: value for key, value in self.case.result_refs.items() if key == "bank_application"}
            self.case.pending_action = None
            self.case.product_selection = None
            self.case.product_requirements = None
            self.case.data_context = None
            self.case.evidence_recheck = None
            self.case.assessment = None
            self.case.bank_application = None
            self.case.result_refs.pop('bank_application', None)
            self.case.data_cutoff_at = utcnow()
            self.case.last_error = None
            transition(self.case, Status.NEEDS_INPUT if self.case.missing_required else Status.REQUEST_READY)
        return ToolResult(ok=True, code="REQUEST_UPDATED" if changed else "NO_CHANGE", data={"changed": changed, "revision": self.case.revision})

    def execute(self, operation: str, arguments: dict) -> ToolResult:
        try:
            self.guard(operation)
            if operation == "load_case":
                return ToolResult(ok=True, code="CASE_LOADED", data={"case_id": self.case.case_id, "status": self.case.status})
            if operation == "find_existing_application":
                subject = self.case.request.borrower_id
                existing = self.repository.find_existing(self.actor, subject) if subject else []
                return ToolResult(ok=True, code="EXISTING_CASES", data={"case_ids": [c.case_id for c in existing]})
            if operation == "update_request":
                return self.update_request(**arguments)
            envelope = {
                "case_id": self.case.case_id, "revision": self.case.revision, "mode": self.case.mode,
                "status": self.case.status, "correlation_id": self.case.correlation_id,
                "borrower_id": self.case.request.borrower_id, "request": self.case.request.model_dump(mode="json"),
                "result_refs": self.case.result_refs.copy(), "document_refs": self.case.document_refs.copy(),
                "verified_facts": self.case.verified_facts.copy(),
                "client_changes": self.case.client_changes.copy(),
                "company_id": self.actor.company_id, "owner_id": self.actor.actor_id,
                "decision_at": self.case.data_cutoff_at.isoformat(),
                "product_routes": self.case.product_requirements.routes if self.case.product_requirements else [],
                "data_context": self.case.data_context, "assessment":self.case.assessment,
                "arguments":arguments,
            }
            # Stable across retries/new messages; correlation_id is intentionally excluded.
            key = hashlib.sha256(json.dumps([self.case.case_id, self.case.revision, operation,
                                            self.case.data_cutoff_at.isoformat(), arguments], ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            response = ModuleResult.model_validate(self.adapter.call(operation, envelope, key))
            if (response.case_id, response.revision, response.borrower_id) != (self.case.case_id, self.case.revision, self.case.request.borrower_id):
                return ToolResult(ok=False, code="RESULT_SCOPE_MISMATCH")
            if response.ok and not response.result_ref:
                return ToolResult(ok=False, code="MISSING_RESULT_REFERENCE")
            if response.ok and operation == "lookup_business_profile":
                profile = BusinessProfileResult.model_validate(response.data.get("profile"))
                if profile.company_id != self.actor.company_id or profile.borrower_id != self.case.request.borrower_id or profile.decision_at != self.case.data_cutoff_at:
                    return ToolResult(ok=False, code="RESULT_SCOPE_MISMATCH")
                from .product_matching import confirmed_profile
                facts = [fact.model_dump(mode="json") for fact in profile.verified_facts]
                confirmed = confirmed_profile(facts, self.case.request.borrower_id, self.case.data_cutoff_at)
                # Only verified profile facts, not historical application parameters, fill gaps.
                value = confirmed.get("legal_form") if not profile.conflicts else None
                if profile.conflicts:
                    self.case.pending_clarifications = [issue for issue in self.case.pending_clarifications if issue.field != "legal_form"] + [FieldProblem(field="legal_form", code="CONFLICT")]
                if value and self.case.request.legal_form is None:
                    cutoff = self.case.data_cutoff_at
                    self.update_request({"legal_form":value}, [], client_reported=False)
                    self.case.data_cutoff_at = cutoff
                    self.case.pending_clarifications = [issue for issue in self.case.pending_clarifications if issue.field != "legal_form"]
                self.case.verified_facts = [fact for fact in self.case.verified_facts if fact.get("field") != "legal_form"] + facts
                self.case.profile_lookup_status = "FOUND" if value else "CONFLICT" if "legal_form" in confirmed or profile.conflicts else "NOT_FOUND"
            if response.ok and operation == "get_product_candidates" and "selection" in response.data:
                selection = ProductSelection.model_validate(response.data["selection"])
                if (selection.case_id, selection.revision, selection.borrower_id) != (self.case.case_id, self.case.revision, self.case.request.borrower_id):
                    return ToolResult(ok=False, code="RESULT_SCOPE_MISMATCH")
                self.case.product_selection = selection
            if response.ok and operation == "get_data_requirements" and "requirements" in response.data:
                requirements = DataRequirements.model_validate(response.data["requirements"])
                if (requirements.case_id, requirements.revision, requirements.product_selection_ref) != (self.case.case_id, self.case.revision, self.case.result_refs.get("products")):
                    return ToolResult(ok=False, code="RESULT_SCOPE_MISMATCH")
                self.case.product_requirements = requirements
            if response.ok and operation == "request_evidence" and "snapshot" in response.data:
                snapshot = EvidenceSummary.model_validate(response.data["snapshot"]).model_dump(mode="json")
                if (snapshot.get("case_id"), snapshot.get("revision"), snapshot.get("company_id")) != (self.case.case_id, self.case.revision, self.actor.company_id) or snapshot["borrower_id"] != self.case.request.borrower_id or datetime.fromisoformat(snapshot["decision_at"]) != self.case.data_cutoff_at:
                    return ToolResult(ok=False, code="RESULT_SCOPE_MISMATCH")
                self.case.data_context = snapshot
                self.case.company_id = self.actor.company_id
                self.case.verified_facts = snapshot.get("verified_facts", [])
            if response.ok and operation in {'run_assessment','get_assessment_status'} and 'assessment_id' in response.data:
                self.case.assessment = response.data
                self.case.result_refs['assessment'] = response.result_ref
            if response.ok and operation in {'submit_application','get_bank_status','accept_offer','execute_demo'} and 'lender_case_id' in response.data:
                self.case.bank_application = response.data
                self.case.result_refs['bank_application'] = response.result_ref
            return ToolResult.model_validate(response.model_dump(include=set(ToolResult.model_fields)))
        except AccessDenied as exc:
            return ToolResult(ok=False, code=str(exc))
        except ModuleUnavailable:
            return ToolResult(ok=False, code="MODULE_NOT_CONFIGURED", data={"operation": operation})
        except ConflictError:
            return ToolResult(ok=False, code='STALE_PROCESS')
        except Exception as exc:
            # Do not expose provider errors, credentials or document contents in the chat.
            return ToolResult(ok=False, code="TOOL_ERROR", data={"error_type": type(exc).__name__})


def grounded_patch(extraction: Extraction, text: str) -> tuple[dict, list[str], list[str]]:
    """Reject ungrounded values even if a model emits a valid JSON schema."""
    normalize = lambda value: " ".join(value.casefold().split())
    source = normalize(text)
    def grounded(field: str) -> bool:
        quote = normalize(extraction.evidence.get(field, ""))
        return bool(quote) and quote in source
    values = extraction.patch.model_dump(mode="json", exclude_none=True)
    rejected = [field for field in values if not grounded(field)]
    return ({field: value for field, value in values.items() if grounded(field)},
            [field for field in extraction.clear_fields if grounded(field)], rejected)
