from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from ..repositories.case_repository import AccessDenied, CaseRepository, check_access
from ..schemas.models import ActorContext, Case, Extraction, LoanRequest, ModuleResult, Scope, Status, ToolResult


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
    Status.MANUAL_REVIEW: {Status.MANUAL_REVIEW, Status.NEEDS_INPUT, Status.REQUEST_READY, Status.CANCELLED},
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
        if not self.case.request.borrower_id or self.case.missing_required:
            raise AccessDenied("INCOMPLETE_REQUEST")
        stages = {
            "get_product_candidates": {Status.REQUEST_READY},
            "get_data_requirements": {Status.REQUEST_READY},
            "request_evidence": {Status.WAITING_DOCUMENTS, Status.WAITING_CONSENT},
            "get_assessment_status": {Status.WAITING_EXTERNAL},
            "get_bank_status": {Status.WAITING_EXTERNAL},
        }
        if operation not in stages or self.case.status not in stages[operation]:
            raise AccessDenied("INVALID_STAGE")
        dependencies = {"get_data_requirements": "products", "request_evidence": "requirements", "get_assessment_status": "assessment", "get_bank_status": "bank_application"}
        if operation in dependencies and dependencies[operation] not in self.case.result_refs:
            raise AccessDenied("MISSING_PROCESS_REFERENCE")
        scope = {"request_evidence": Scope.EVIDENCE_COLLECTION, "get_assessment_status": Scope.CREDIT_ASSESSMENT, "get_bank_status": Scope.BANK_STATUS}.get(operation)
        if scope:
            if scope in self.actor.denied_scopes:
                raise AccessDenied("CONSENT_DENIED")
            if not self.actor.has_consent(scope, self.case.request.borrower_id):
                raise AccessDenied("CONSENT_REQUIRED")

    def update_request(self, patch: dict, clear_fields: list[str]) -> ToolResult:
        data = self.case.request.model_dump()
        for field in clear_fields:
            if field not in LoanRequest.model_fields:
                raise ValueError("Unknown clear field")
            data[field] = None
        data.update({key: value for key, value in LoanRequest.model_validate(patch).model_dump(exclude_none=True).items()})
        candidate = LoanRequest.model_validate(data)
        if candidate.borrower_id and candidate.borrower_id not in self.actor.allowed_borrower_ids:
            raise AccessDenied("SUBJECT_NOT_ALLOWED")
        old_subject = self.case.request.borrower_id
        if old_subject and candidate.borrower_id != old_subject:
            raise AccessDenied("SUBJECT_CHANGE_REQUIRES_NEW_SESSION")
        changed = candidate != self.case.request
        if changed:
            # Initial identity from the trusted session is not itself a request revision.
            had_request = any(value is not None for key, value in self.case.request.model_dump().items() if key != "borrower_id")
            if had_request:
                self.case.revision += 1
            self.case.request = candidate
            self.case.result_refs = {key: value for key, value in self.case.result_refs.items() if key == "bank_application"}
            self.case.pending_action = None
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
            }
            # Stable across retries/new messages; correlation_id is intentionally excluded.
            key = hashlib.sha256(json.dumps([self.case.case_id, self.case.revision, operation], ensure_ascii=False).encode()).hexdigest()
            response = ModuleResult.model_validate(self.adapter.call(operation, envelope, key))
            if (response.case_id, response.revision, response.borrower_id) != (self.case.case_id, self.case.revision, self.case.request.borrower_id):
                return ToolResult(ok=False, code="RESULT_SCOPE_MISMATCH")
            if response.ok and not response.result_ref:
                return ToolResult(ok=False, code="MISSING_RESULT_REFERENCE")
            return ToolResult.model_validate(response.model_dump(include=set(ToolResult.model_fields)))
        except AccessDenied as exc:
            return ToolResult(ok=False, code=str(exc))
        except ModuleUnavailable:
            return ToolResult(ok=False, code="MODULE_NOT_CONFIGURED", data={"operation": operation})
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
