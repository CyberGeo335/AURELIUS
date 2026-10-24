"""Typed diagnostics and next steps. These are application output, never LLM authority."""
from typing import Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class FieldProblem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str = Field(min_length=1, max_length=120)
    code: Literal['INVALID_VALUE', 'MISSING_QUOTE', 'UNGROUNDED_QUOTE', 'UNSUPPORTED_ASSERTION', 'CONFLICT', 'DATABASE_UNAVAILABLE']


class VerbatimEvidence(BaseModel):
    quote: str = Field(min_length=1, max_length=12000)

    @field_validator('quote')
    @classmethod
    def present_in_current_message(cls, value: str, info: ValidationInfo):
        normalize = lambda text: ' '.join(text.casefold().split())
        if not normalize(value) or normalize(value) not in normalize(info.context['text']):
            raise ValueError('Quote must occur in the current message')
        return value


class DataGap(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    status: Literal['MISSING', 'INVALID', 'UNGROUNDED', 'CONFLICT', 'UNAVAILABLE', 'UNCONFIGURED']
    resolution: Literal['ASK_USER', 'DATABASE_THEN_USER', 'ENGINEERING']
    question: str | None = None
    reason: str


class DataResolutionPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    gaps: list[DataGap] = Field(default_factory=list)
    database_lookup: Literal['NOT_NEEDED', 'CONSENT_REQUIRED', 'UNSUPPORTED', 'FOUND', 'NOT_FOUND', 'CONFLICT', 'UNAVAILABLE'] = 'NOT_NEEDED'
    ready_for_product_matching: bool = False
    ready_for_scoring: bool = False


class VerifiedProfileFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: Literal['legal_form']
    value: Literal['IP', 'OOO', 'AO', 'OTHER']
    borrower_id: str
    company_id: int = Field(gt=0)
    confirmed: Literal[True]
    scope: Literal['PRODUCT_MATCHING']
    source_ref: str = Field(min_length=1)
    verified_at: datetime
    available_at: datetime
    snapshot_as_of: datetime
    validity: Literal['AS_OF_SNAPSHOT']

    @model_validator(mode='after')
    def point_in_time(self):
        if any(value.tzinfo is None for value in (self.verified_at, self.available_at, self.snapshot_as_of)):
            raise ValueError('Fact timestamps require timezone')
        if self.verified_at > self.snapshot_as_of or self.available_at > self.snapshot_as_of:
            raise ValueError('Future fact')
        return self


class BusinessProfileResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    company_id: int = Field(gt=0)
    borrower_id: str
    decision_at: datetime
    verified_facts: list[VerifiedProfileFact] = Field(default_factory=list)
    conflicts: list[Literal["legal_form"]] = Field(default_factory=list)

    @model_validator(mode='after')
    def scope_and_cutoff(self):
        if self.decision_at.tzinfo is None:
            raise ValueError('Profile cutoff requires timezone')
        for fact in self.verified_facts:
            if (fact.company_id, fact.borrower_id, fact.snapshot_as_of) != (self.company_id, self.borrower_id, self.decision_at):
                raise ValueError('Profile fact scope mismatch')
        return self
