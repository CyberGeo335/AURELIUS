"""Bounded draft pricing. Explicit individual quotes are never repriced."""
from decimal import Decimal

from ..schemas import ConfigurationError


def candidate_rates(snapshot, initial_rate, policy):
    pricing = snapshot.get("pricing_policy")
    if not pricing:
        return [initial_rate]
    if not policy.demo_only or not pricing.get("demo_only") or not pricing.get("source"):
        raise ConfigurationError("Draft pricing requires an explicit versioned demo policy")
    try:
        maximum = Decimal(str(pricing["maximum_rate_pct"]))
        step = Decimal(str(pricing["step_pct"]))
        if not maximum.is_finite() or not step.is_finite() or step <= 0 or maximum < initial_rate:
            raise ValueError("Invalid draft rate interval")
        # Model was trained on annual_rate in [.10,.36]. No silent extrapolation.
        if maximum > 36 or initial_rate < 10:
            raise ValueError("Draft rate interval is outside the training generator domain")
        catalog_maximum = snapshot["rate_option"].get("max_annual_rate_pct")
        if catalog_maximum is not None:
            maximum = min(maximum, Decimal(str(catalog_maximum)))
        if maximum < initial_rate:
            raise ValueError("Catalog maximum is below starting rate")
        count = int((maximum - initial_rate) // step)
        if count > 100:
            raise ValueError("Draft rate grid is too large")
        return sorted({initial_rate + step * i for i in range(count + 1)} | {maximum})
    except (KeyError, ValueError, ArithmeticError) as exc:
        raise ConfigurationError(f"Invalid draft pricing policy: {exc}") from exc
