"""V2 wire contracts. ActorContext is supplied by a trusted boundary, not JSON commands."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Shared value contracts; neither import starts the V1 workflow or opens its DB.
from personalCab.prom.prom_lab.ai_agents_lab.schemas.models import LoanRequest
from personalCab.prom.prom_lab.ai_agents_lab.schemas.resolution import DataResolutionPlan, FieldProblem
from personalCab.prom.prom_lab.ai_agents_lab.schemas.products import ProductSelection
from personalCab.prom.rag.models import KnowledgeAnswer


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Scope(StrEnum):
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    CREDIT_ASSESSMENT = "CREDIT_ASSESSMENT"
    BANK_STATUS = "BANK_STATUS"
    APPLICATION_SUBMISSION = "APPLICATION_SUBMISSION"
    DEMO_EXECUTION = "DEMO_EXECUTION"


class Grant(Model):
    scope: Scope
    granted_at: datetime
    expires_at: datetime
    revoked: bool = False

    @model_validator(mode="after")
    def valid_times(self):
        if self.granted_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Consent timestamps need timezones")
        if self.expires_at <= self.granted_at:
            raise ValueError("Consent expiry must follow its grant")
        return self


class Actor(Model):
    actor_id: str = Field(min_length=1, max_length=120)
    company_id: int = Field(strict=True, gt=0)
    borrower_id: str = Field(min_length=1, max_length=120)
    role: Literal["BORROWER", "OPERATOR", "READER"] = "BORROWER"
    grants: list[Grant] = Field(default_factory=list)

    def permits(self, scope: Scope, at: datetime) -> bool:
        relevant = [grant for grant in self.grants if grant.scope == scope]
        # A revoked grant wins; the boundary must refresh the registry before each command.
        return not any(grant.revoked for grant in relevant) and any(
            grant.granted_at <= at < grant.expires_at for grant in relevant
        )


class Action(StrEnum):
    CREATE = "CREATE"
    LOOKUP_PROFILE = "LOOKUP_PROFILE"
    CHAT = "CHAT"
    CONFIRM_FACTS = "CONFIRM_FACTS"
    UPDATE_REQUEST = "UPDATE_REQUEST"
    SELECT_PRODUCT = "SELECT_PRODUCT"
    CANCEL = "CANCEL"
    REFRESH_EVIDENCE = "REFRESH_EVIDENCE"
    ASSESS = "ASSESS"
    SUBMIT = "SUBMIT"
    POLL_STATUS = "POLL_STATUS"
    ACCEPT_OFFER = "ACCEPT_OFFER"
    EXECUTE_DEMO = "EXECUTE_DEMO"


class Command(Model):
    request_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    action: Action
    case_id: str | None = Field(default=None, min_length=1, max_length=120)
    expected_version: int = Field(strict=True, ge=0)
    text: str = Field(default="", max_length=12000)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def explicit_context(self):
        if self.action == Action.CREATE:
            if self.case_id is not None or self.expected_version != 0 or self.text or self.arguments:
                raise ValueError("CREATE takes no case, text or arguments and version must be 0")
        elif not self.case_id or self.expected_version < 1:
            raise ValueError("An explicit case_id and expected_version are required")
        if self.action == Action.CHAT and (not self.text.strip() or self.arguments):
            raise ValueError("CHAT requires text and no command arguments")
        return self


class Proposal(Model):
    proposal_id: str = Field(default_factory=lambda: "PROP-" + uuid4().hex)
    patch: dict[str, Any]
    clear_fields: list[str] = Field(default_factory=list)
    quotes: dict[str, str]
    source_message_id: str
    source_text: str


class FollowUp(Model):
    request_id: str = Field(default_factory=lambda: "FOLLOW-" + uuid4().hex)
    fields: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=12000)
    due_at: datetime | None = None
    answered_fields: list[str] = Field(default_factory=list)
    answered_documents: list[str] = Field(default_factory=list)
    status: Literal["OPEN", "ANSWERED", "SUPERSEDED"] = "OPEN"

    @model_validator(mode="after")
    def timezone_required(self):
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError("Follow-up deadline needs a timezone")
        return self


class Case(Model):
    case_id: str
    owner_id: str
    company_id: int
    borrower_id: str
    version: int = 0
    revision: int = 1
    mode: Literal["DEMO"] = "DEMO"
    status: Literal["DRAFT", "NEEDS_INFO", "CHECKING", "MANUAL_REVIEW", "OFFERED", "ACCEPTED", "EXECUTED_DEMO", "DECLINED", "CANCELLED"] = "DRAFT"
    request: LoanRequest
    selected_product_id: str | None = None
    product_selection: ProductSelection | None = None
    pending: Proposal | None = None
    problems: list[FieldProblem] = Field(default_factory=list)
    history: list[dict[str, str]] = Field(default_factory=list)
    client_changes: list[dict[str, Any]] = Field(default_factory=list)
    data_cutoff_at: datetime = Field(default_factory=utcnow)
    data_context: dict[str, Any] | None = None
    evidence_stale: bool = False
    follow_ups: list[FollowUp] = Field(default_factory=list)
    checking_error: str | None = None
    assessment: dict[str, Any] | None = None
    bank_application: dict[str, Any] | None = None
    last_knowledge_answer: KnowledgeAnswer | None = None
    business_profile: dict[str, Any] | None = None
    profile_lookup_status: Literal['NOT_NEEDED','FOUND','NOT_FOUND','CONFLICT','UNAVAILABLE'] = 'NOT_NEEDED'
    review_owner: str | None = None
    authority_evidence: dict[str, Any] | None = None
    offer_history: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def detect_legacy_stale_evidence(self):
        # Older payloads advanced the cutoff after writes without invalidating
        # their snapshot. Fail closed for these saved cases as well.
        snapshot_cutoff = (self.data_context or {}).get("decision_at")
        if not self.evidence_stale and snapshot_cutoff and self.status not in {"EXECUTED_DEMO", "DECLINED", "CANCELLED"}:
            if datetime.fromisoformat(snapshot_cutoff) < self.data_cutoff_at:
                self.evidence_stale = True
        return self


class View(Model):
    api_version: Literal["2"] = "2"
    case_id: str
    version: int
    revision: int
    mode: Literal["DEMO"] = "DEMO"
    status: str
    request: LoanRequest
    selected_product_id: str | None
    pending: Proposal | None
    product_selection: ProductSelection | None
    data_resolution: DataResolutionPlan
    knowledge_answer: KnowledgeAnswer | None = None
    last_knowledge_answer: KnowledgeAnswer | None = None
    message: str
    error_code: str | None = None
    allowed_actions: list[Action]
    action_reasons: dict[str, str] = Field(default_factory=dict)
    allowed_operations: list[str] = Field(default_factory=list)
    capabilities: dict[str, bool]
    data_context: dict[str, Any] | None = None
    evidence_stale: bool = False
    current_data: dict[str, Any] | None = None
    follow_ups: list[FollowUp] = Field(default_factory=list)
    checking_error: str | None = None
    assessment: dict[str, Any] | None = None
    bank_application: dict[str, Any] | None = None
    history: list[dict[str, str]]
    business_profile: dict[str, Any] | None = None
    review_owner: str | None = None
    authority_evidence: dict[str, Any] | None = None
    offer_history: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
