"""Public contracts. Monetary calculations use Decimal; PD uses float."""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


class ConfigurationError(ValueError):
    """Missing or ambiguous internal configuration; never a client question."""


class InputError(ValueError):
    """The upstream service has not supplied a valid assessment snapshot."""


def money(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise InputError("Non-finite monetary value")
    return result.quantize(Decimal("0.01"))


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


@dataclass
class ScoringResult:
    model_version: str
    monthly_hazard: list[float]
    cumulative_pd: list[float]
    pd_by_horizon: dict[int, float]
    term_months: int

    @property
    def pd_term(self) -> float:
        return self.cumulative_pd[-1]


@dataclass
class Offer:
    amount: Decimal
    term_months: int
    annual_rate_pct: Decimal
    repayment_type: str
    max_monthly_payment: Decimal
    affordability_payment: Decimal
    monthly_schedule: list[dict[str, Any]]
    economics: dict[str, Any] = field(default_factory=dict)


@dataclass
class Assessment:
    application_id: int
    decision: str
    eligibility_status: str
    reasons: list[dict[str, str]]
    policy_version: str
    offer: Offer | None = None
    scoring: ScoringResult | None = None
    audit: dict[str, Any] = field(default_factory=dict)
    automatic_recommendation: str = "REVIEW_REQUIRED"
    risk_assessment: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json_value(asdict(self))
