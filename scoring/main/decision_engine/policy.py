import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..schemas import ConfigurationError


@dataclass(frozen=True)
class Policy:
    version: str
    demo_only: bool
    minimum_dscr: Decimal
    amount_step: Decimal
    max_candidates: int
    # Explicit authorization to use the model's full curve outside evaluated horizons.
    allow_unvalidated_term_pd: bool
    capital_cost_pct: Decimal
    discount_rate_pct: Decimal
    # Optional horizon-specific risk appetite, distinct from profitability.
    pd_limits: dict[int, float]
    decision_method: str = "monthly_cashflow"

    @classmethod
    def from_dict(cls, data):
        required = {"version", "demo_only", "minimum_dscr", "amount_step", "max_candidates",
                    "allow_unvalidated_term_pd", "capital_cost_pct", "discount_rate_pct", "pd_limits"}
        missing = required - data.keys()
        if missing:
            raise ConfigurationError(f"Missing policy parameters: {sorted(missing)}")
        try:
            for key in ("demo_only", "allow_unvalidated_term_pd"):
                if type(data[key]) is not bool:
                    raise ValueError(f"{key} must be boolean")
            result = cls(str(data["version"]), data["demo_only"], Decimal(str(data["minimum_dscr"])),
                         Decimal(str(data["amount_step"])), int(data["max_candidates"]),
                         data["allow_unvalidated_term_pd"], Decimal(str(data["capital_cost_pct"])),
                         Decimal(str(data["discount_rate_pct"])),
                         {int(k): float(v) for k, v in data["pd_limits"].items()},
                         str(data.get("decision_method", "monthly_cashflow")))
            if result.decision_method not in ("monthly_cashflow", "annual_pd_limit"):
                raise ValueError("Unknown decision_method")
            if not result.version.strip() or len(result.version) > 50:
                raise ValueError("version must contain 1..50 characters")
            if not all(x.is_finite() for x in (result.minimum_dscr, result.amount_step,
                                               result.capital_cost_pct, result.discount_rate_pct)):
                raise ValueError("non-finite policy value")
            if result.minimum_dscr < 1 or result.amount_step < Decimal("0.01") or result.max_candidates < 1:
                raise ValueError("Invalid DSCR, amount step or candidate budget")
            if result.capital_cost_pct < 0 or result.discount_rate_pct < 0:
                raise ValueError("Negative cost or discount rate")
            if any(h < 1 or not 0 <= p <= 1 for h, p in result.pd_limits.items()):
                raise ValueError("Invalid PD limit")
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise ConfigurationError(str(exc)) from exc
        return result

    @classmethod
    def load(cls, path: str | Path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def validate_economic_inputs(snapshot):
    required = ("funding_spread_pct", "operating_cost_pct", "required_margin_pct", "lgd_pct")
    raw = snapshot.get("risk_policy", {})
    if not raw.get("policy_version"):
        raise ConfigurationError("Missing DB risk policy version")
    if raw.get("product_code") != snapshot["application"]["product_code"]:
        raise ConfigurationError("Economic risk policy belongs to another product")
    if snapshot.get("key_rate_pct") is None or not snapshot.get("key_rate_source"):
        raise ConfigurationError("Missing key rate or source at assessment date")
    if not snapshot.get("key_rate_effective_date"):
        raise ConfigurationError("Missing key rate effective date")
    if date.fromisoformat(str(snapshot["key_rate_effective_date"])[:10]) > date.fromisoformat(str(snapshot["as_of"])[:10]):
        raise ConfigurationError("Key rate observation is after assessment date")
    if not snapshot.get("economics_source"):
        raise ConfigurationError("Missing source/version for economic assumptions")
    try:
        values = {key: Decimal(str(raw[key])) for key in required}
        values["key_rate_pct"] = Decimal(str(snapshot["key_rate_pct"]))
        if any(not x.is_finite() for x in values.values()):
            raise ValueError("Non-finite economic parameter")
        if any(not 0 <= values[key] <= 100 for key in (*required[1:], "key_rate_pct")):
            raise ValueError("Economic percentages outside 0..100")
        if not -100 <= values["funding_spread_pct"] <= 100:
            raise ValueError("Invalid funding spread")
        if values["key_rate_pct"] + values["funding_spread_pct"] < 0:
            raise ValueError("Negative funding cost")
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise ConfigurationError(f"Invalid economic inputs: {exc}") from exc
    return values


def annual_pd_limit(annual_rate_pct, inputs):
    """Annual simplified break-even indicator. All input rates are percentages.

    Return probabilities in fractions, preserving raw and clipped limits.
    Required margin is already a policy reserve, not a measured bank profit.
    """
    lgd = inputs["lgd_pct"] / Decimal(100)
    if lgd <= 0:
        raise ConfigurationError("annual_pd_limit requires LGD > 0")
    funding = inputs["key_rate_pct"] + inputs["funding_spread_pct"]
    headroom = Decimal(str(annual_rate_pct)) - funding - inputs["operating_cost_pct"] - inputs["required_margin_pct"]
    raw = headroom / Decimal(100) / lgd
    return {"method": "annual_pd_limit", "comparison_horizon_months": 12,
            "pd_limit_1y_raw": float(raw),
            "pd_limit_1y": float(max(Decimal(0), min(Decimal(1), raw))),
            "annual_funding_rate_pct": str(funding),
            "annual_headroom_pct": str(headroom), "positive_headroom": headroom > 0}
