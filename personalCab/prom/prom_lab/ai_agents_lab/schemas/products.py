"""Typed module 2 boundary. Product suitability is not a credit decision."""
from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductModel(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)


class ProductRule(ProductModel):
    code: str
    label: str
    field: str
    minimum: int | None = None
    maximum: int | None = None
    allowed: list[str] | None = None
    expected_bool: bool | None = None
    verified_only: bool = False
    unbounded_minimum: bool = False
    unbounded_maximum: bool = False

    @model_validator(mode='after')
    def valid_bounds(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('Invalid rule bounds')
        return self


class Requirement(ProductModel):
    code: str
    label: str
    source: str
    purpose: str


class ProductCard(ProductModel):
    product_id: str
    product_family: str
    name: str
    lender: str
    source_url: str
    source_version: str
    rule_version: str
    effective_from: date | None = None
    effective_until: date | None = None
    approved: bool = False
    needs: list[str]
    process: Literal['CREDIT', 'LEASING', 'FACTORING', 'GUARANTEE'] = 'CREDIT'
    rules: list[ProductRule]
    requirements: list[Requirement]
    limitations: list[str]
    # Different clocks: none of these is inferred from another.
    contract_term_months: dict[str, int | None] = Field(default_factory=dict)
    tranche_term_days: dict[str, int | None] = Field(default_factory=dict)
    drawdown_period_days: dict[str, int | None] = Field(default_factory=dict)
    published_min_rate: float | None = None


class ProductCatalog(ProductModel):
    version: str
    source: str
    products: list[ProductCard]

    @model_validator(mode='after')
    def unique_offerings(self):
        ids = [(item.product_family, item.product_id) for item in self.products]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate product offering')
        return self


class ConditionCheck(ProductModel):
    code: str
    label: str
    status: Literal['MATCH', 'NO_MATCH', 'UNKNOWN']
    reason: str
    actual: Any = None
    expected: Any = None
    provenance: str


class ProductCandidate(ProductModel):
    product_id: str
    product_family: str
    name: str
    process: str
    eligibility: Literal['MATCH', 'NO_MATCH', 'UNKNOWN']
    priority: int
    reasons: list[str]
    checks: list[ConditionCheck]
    missing_checks: list[str]
    limitations: list[str]
    requirements: list[Requirement]
    requirements_ref: str
    source_url: str
    source_version: str
    rule_version: str


class ProductSelection(ProductModel):
    case_id: str
    revision: int
    borrower_id: str
    mode: Literal['DEMO'] = 'DEMO'
    status: Literal['PRODUCTS_READY', 'NEEDS_CLARIFICATION']
    catalog_version: str
    context_hash: str
    evaluated_at: datetime
    candidates: list[ProductCandidate]
    excluded: list[ConditionCheck]
    next_module: int | None
    clarification: str | None = None


class DataRequirements(ProductModel):
    case_id: str
    revision: int
    catalog_version: str
    product_selection_ref: str
    status: Literal['REQUIREMENTS_READY'] = 'REQUIREMENTS_READY'
    routes: list[dict[str, Any]]
    documents: list[Requirement]
    note: str = 'Предварительный адресный перечень проекта. Утверждённый перечень кредитора неизвестен; сбор документов ещё не запускался.'
