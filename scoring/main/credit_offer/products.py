from decimal import Decimal

from ..schemas import ConfigurationError, InputError


def repayment_parameters(snapshot: dict) -> tuple[str, int]:
    """Contract horizon remains separate from the repayment/tranche horizon."""
    product = snapshot["application"]["product_code"]
    repayment = snapshot["repayment_option"]["repayment_type"]
    months = snapshot["application"]["requested_term_months"]
    if product == "R01":
        if repayment not in ("ANNUITY", "EQUAL_PRINCIPAL"):
            raise ConfigurationError("R01 requires ANNUITY or EQUAL_PRINCIPAL")
        return repayment, months
    if product not in ("R02", "R03"):
        raise ConfigurationError(f"Unsupported product: {product}")
    details = snapshot.get("product_details", {})
    value, unit = details.get("max_tranche_term_value"), details.get("max_tranche_term_unit")
    if not value or unit not in ("DAYS", "MONTHS") or Decimal(str(value)) <= 0:
        raise InputError("A separate positive tranche duration and unit are required")
    if int(value) != Decimal(str(value)):
        raise InputError("Tranche duration must be integer")
    rate, terms = snapshot["rate_option"], snapshot["terms"]
    # Compare durations only within their explicit unit. No silent 30-day conversion.
    maximum = rate.get("max_tranche_term_days" if unit == "DAYS" else "max_tranche_term_months")
    if maximum is None and terms.get("tranche_term_unit") == unit:
        maximum = terms.get("max_tranche_term_value")
    minimum = terms.get("min_tranche_term_value") if terms.get("tranche_term_unit") == unit else None
    if maximum is None:
        raise ConfigurationError("No catalog tranche bound in the selected unit")
    if value > maximum or (minimum is not None and value < minimum):
        raise InputError("Tranche duration is outside selected catalog bounds")
    if unit == "DAYS":
        # A conservative monthly sinking fund: use complete 31-day periods.
        # This is an explicit MVP capacity convention, not a contractual schedule.
        reserve_months = max(1, int(value) // 31)
    else:
        reserve_months = int(value)
    if reserve_months > months:
        raise InputError("Tranche exceeds contract horizon")
    if product == "R02" and repayment not in ("BULLET", "EQUAL_PRINCIPAL"):
        raise ConfigurationError("Unsupported R02 repayment")
    if product == "R03" and repayment != "OTHER":
        raise ConfigurationError("Expected R03 catalog repayment OTHER")
    return ("REVOLVING_RESERVE" if product == "R03" or repayment == "BULLET"
            else "REVOLVING_EQUAL_PRINCIPAL"), reserve_months
