from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from personalCab.prom.rag.models import KnowledgeAnswer
from .products import DataRequirements, ProductSelection
from .resolution import DataResolutionPlan, FieldProblem


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def explicit_control_intent(intent: str, text: str) -> bool:
    """A model label alone cannot cancel a case or initiate a manual handoff."""
    if intent == "CANCEL":
        cue = r"\b(?:отмен\w*|аннулир\w*|закрой\w*|закрыть|прекрат\w*|cancel)\b"
    elif intent == "MANUAL_REVIEW":
        cue = r"\b(?:оператор\w*|специалист\w*|менеджер\w*|человек\w*|ручн\w*|human)\b"
    else:
        return True
    value = text.casefold()
    return bool(re.search(cue, value)) and not bool(re.search(r"\bне\s+" + cue.removeprefix(r"\b"), value))


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Status(StrEnum):
    DISCOVERY = "DISCOVERY"
    NEEDS_INPUT = "NEEDS_INPUT"
    WAITING_CONSENT = "WAITING_CONSENT"
    REQUEST_READY = "REQUEST_READY"
    WAITING_DOCUMENTS = "WAITING_DOCUMENTS"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Scope(StrEnum):
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    CREDIT_ASSESSMENT = "CREDIT_ASSESSMENT"
    BANK_STATUS = "BANK_STATUS"
    APPLICATION_SUBMISSION = "APPLICATION_SUBMISSION"
    DEMO_EXECUTION = "DEMO_EXECUTION"


class Consent(Model):
    consent_id: str = Field(min_length=1)
    borrower_id: str = Field(min_length=1)
    scope: Scope
    granted_at: datetime
    expires_at: datetime

    @field_validator("granted_at", "expires_at")
    @classmethod
    def aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Consent times require timezone")
        return value


class ActorContext(Model):
    """Only populated by the authentication/application boundary, never by LLM."""

    actor_id: str = Field(min_length=1, max_length=120)
    role: Literal["BORROWER", "OPERATOR", "READER"] = "BORROWER"
    allowed_borrower_ids: list[str] = Field(default_factory=list)
    active_borrower_id: str | None = None
    consents: list[Consent] = Field(default_factory=list)
    denied_scopes: list[Scope] = Field(default_factory=list)
    company_id: int | None = Field(default=None, gt=0)

    def has_consent(self, scope: Scope, borrower_id: str) -> bool:
        now = utcnow()
        return scope not in self.denied_scopes and any(
            c.scope == scope and c.borrower_id == borrower_id
            and c.granted_at <= now < c.expires_at for c in self.consents
        )


class LoanRequest(Model):
    inn: str | None = Field(default=None, pattern=r'^(?:[0-9]{10}|[0-9]{12})$')
    company_name: str | None = Field(default=None, min_length=1, max_length=500)
    ogrn: str | None = Field(default=None, pattern=r'^[0-9]{13}$')
    ogrnip: str | None = Field(default=None, pattern=r'^[0-9]{15}$')
    legal_address: str | None = Field(default=None, min_length=1, max_length=2000)
    director_name: str | None = Field(default=None, min_length=1, max_length=500)
    okved_main: str | None = Field(default=None, pattern=r'^[0-9]{2}(?:\.[0-9]{1,2}){0,2}$')
    registration_date: date | None = None
    actual_activity_description: str | None = Field(default=None, min_length=1, max_length=2000)
    project_name: str | None = Field(default=None,min_length=1,max_length=100)
    borrower_id: str | None = Field(default=None, min_length=1, max_length=120)
    legal_form: Literal["IP", "OOO", "AO", "OTHER"] | None = None
    purpose: Literal["INVENTORY", "WORKING_CAPITAL", "INVESTMENT", "REAL_ESTATE", "VEHICLE", "REFINANCING", "GUARANTEE", "OTHER"] | None = None
    amount_rub: int | None = Field(default=None, strict=True, gt=0, le=1_000_000_000_000)
    term_months: int | None = Field(default=None, strict=True, gt=0, le=600)
    needed_by: date | None = None
    repayment_source: str | None = Field(default=None, max_length=2000)
    recurring: bool | None = None
    known_obligations: str | None = Field(default=None, max_length=2000)
    seasonality: str | None = Field(default=None, max_length=1000)
    collateral: str | None = Field(default=None, max_length=2000)
    financing_need: Literal["ONE_TIME_PURCHASE", "REPEATED_PURCHASES", "CASH_GAP", "MARKETPLACE", "VEHICLE", "PREMISES", "PROPERTY_BACKED", "REFINANCING", "CONTRACT_SECURITY", "DEFERRED_PAYMENT", "STATE_SUPPORT", "CARD_EXPENSES", "SMALL_TRANCHES", "RESERVE", "PARTNER_PURCHASE", "EQUIPMENT_USE"] | None = None
    business_age_months: int | None = Field(default=None, ge=0, le=2400)
    monthly_revenue_rub: int | None = Field(default=None, ge=0)
    operating_cycle_days: int | None = Field(default=None, gt=0, le=3650)
    has_collateral: bool | None = None
    tranche_term_days: int | None = Field(default=None, strict=True, gt=0, le=3650)
    tranche_term_months: int | None = Field(default=None, strict=True, gt=0, le=600)
    drawdown_period_months: int | None = Field(default=None, strict=True, gt=0, le=600)

    @field_validator('registration_date')
    @classmethod
    def registered_in_past(cls, value):
        if value is not None and value > date.today():
            raise ValueError('Registration date cannot be in the future')
        return value


REQUIRED_FIELDS = ("borrower_id", "legal_form", "purpose", "amount_rub", "term_months")
FIELD_LABELS = {
    "company_name": "полное наименование организации", "ogrn": "ОГРН", "ogrnip": "ОГРНИП",
    "legal_address": "юридический адрес", "director_name": "ФИО руководителя",
    "okved_main": "основной ОКВЭД", "registration_date": "дата государственной регистрации",
    "actual_activity_description": "фактический вид деятельности",
    "inn": "укажите ИНН: только цифры, 12 для ИП или 10 для юридического лица",
    "borrower_id": "выберите ИП или компанию", "legal_form": "укажите форму бизнеса: ИП, ООО или другую",
    "purpose": "на что нужны деньги", "amount_rub": "какая сумма нужна в рублях",
    "term_months": "на сколько месяцев нужны деньги", "needed_by": "когда понадобятся деньги",
    "repayment_source": "из каких поступлений планируете возвращать кредит",
}


class Extraction(Model):
    intent: Literal["PROVIDE_DETAILS", "STATUS", "CANCEL", "MANUAL_REVIEW"] = "PROVIDE_DETAILS"
    patch: LoanRequest = Field(default_factory=LoanRequest)
    clear_fields: list[str] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict, description="Verbatim quote from current user text for each changed field; intent quote for cancellation/review")
    ambiguous_subjects: list[str] = Field(default_factory=list)
    multiple_purposes: list[str] = Field(default_factory=list)

    diagnostics: list[FieldProblem] = Field(default_factory=list)

    @field_validator("clear_fields")
    @classmethod
    def known_fields(cls, value: list[str]) -> list[str]:
        if set(value) - LoanRequest.model_fields.keys():
            raise ValueError("Unknown request field")
        return value


class MessageInput(Model):
    session_id: str = Field(min_length=1, max_length=120)
    message_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=12000)
    document_refs: list[str] = Field(default_factory=list, max_length=20)
    command: Literal['CHAT', 'UPDATE_REQUEST', 'REFRESH_EVIDENCE', 'ASSESS', 'SUBMIT', 'ACCEPT_OFFER', 'EXECUTE_DEMO', 'POLL_STATUS'] = 'CHAT'
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("document_refs")
    @classmethod
    def bounded_references(cls, refs: list[str]) -> list[str]:
        if any(not ref.strip() or len(ref) > 2000 for ref in refs):
            raise ValueError("Invalid document reference")
        return refs


class Case(Model):
    client_changes: list[dict[str, Any]] = Field(default_factory=list)
    case_id: str = Field(default_factory=lambda: "CASE-" + uuid4().hex)
    owner_id: str
    revision: int = 1
    storage_version: int = 0
    mode: Literal["DEMO"] = "DEMO"
    status: Status = Status.DISCOVERY
    correlation_id: str = Field(default_factory=lambda: uuid4().hex)
    request: LoanRequest = Field(default_factory=LoanRequest)
    result_refs: dict[str, str] = Field(default_factory=dict)
    # Facts need subject/validity metadata. This module never marks user text verified.
    verified_facts: list[dict[str, Any]] = Field(default_factory=list)
    document_refs: list[str] = Field(default_factory=list)
    history: list[dict[str, str]] = Field(default_factory=list)
    pending_action: str | None = None
    last_error: str | None = None
    product_selection: ProductSelection | None = None
    product_requirements: DataRequirements | None = None
    company_id: int | None = None
    data_cutoff_at: datetime = Field(default_factory=utcnow)
    data_context: dict[str, Any] | None = None
    data_resolution: DataResolutionPlan | None = None
    evidence_recheck: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
    bank_application: dict[str, Any] | None = None

    pending_clarifications: list[FieldProblem] = Field(default_factory=list)
    profile_lookup_status: str = "NOT_NEEDED"

    @property
    def unknown_fields(self) -> list[str]:
        return [name for name in LoanRequest.model_fields if getattr(self.request, name) is None]

    @property
    def missing_required(self) -> list[str]:
        return [name for name in REQUIRED_FIELDS if getattr(self.request, name) is None]


class ToolResult(Model):
    ok: bool
    code: str
    data: dict[str, Any] = Field(default_factory=dict)
    result_ref: str | None = None


class ModuleResult(ToolResult):
    case_id: str
    revision: int
    borrower_id: str


class ToolTrace(Model):
    tool_name: str
    tool_call_id: str
    revision: int
    correlation_id: str
    result: ToolResult


class DialogueResult(Model):
    client_changes: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_answer: KnowledgeAnswer | None = None
    case_id: str
    revision: int
    mode: Literal["DEMO"]
    status: Status
    correlation_id: str
    request: LoanRequest
    unknown_fields: list[str]
    next_module: int | None = None
    next_action: str
    message: str
    result_refs: dict[str, str]
    tool_traces: list[ToolTrace] = Field(default_factory=list)
    error_code: str | None = None
    product_selection: ProductSelection | None = None
    product_requirements: DataRequirements | None = None
    data_context: dict[str, Any] | None = None
    data_resolution: DataResolutionPlan | None = None
    evidence_recheck: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
    bank_application: dict[str, Any] | None = None
