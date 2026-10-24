from decimal import Decimal, ROUND_FLOOR

from ..schemas import ConfigurationError, InputError, Offer, money
from .products import repayment_parameters


def build_offer(snapshot, amount: Decimal, annual_rate_pct: Decimal) -> Offer:
    kind, repayment_months = repayment_parameters(snapshot)
    term = snapshot["application"]["requested_term_months"]
    rate = annual_rate_pct / Decimal(1200)
    rows = []
    balance = amount
    annuity = money(amount / term if rate == 0 else
                    amount * rate / (1 - (1 + rate) ** (-term)))
    for month in range(1, term + 1):
        opening = balance
        if kind.startswith("REVOLVING"):
            # Stress: the full limit is outstanding throughout the contract.
            # Reserve is a capacity requirement, never counted as bank income.
            interest = money(amount * rate)
            principal = Decimal(0)
            capacity = interest + amount / repayment_months
            if month == term:
                principal = amount
        else:
            interest = money(opening * rate)
            principal = annuity - interest if kind == "ANNUITY" else money(amount / term)
            if month == term:
                principal = balance
            principal = min(balance, principal)
            capacity = principal + interest
        balance = max(Decimal(0), balance - principal)
        rows.append({"month": month, "opening_balance": money(opening),
                     "principal": money(principal), "interest": money(interest),
                     "payment": money(principal + interest), "closing_balance": money(balance),
                     "capacity_requirement": money(capacity)})
    return Offer(money(amount), term, annual_rate_pct, kind,
                 max(row["payment"] for row in rows),
                 max(row["capacity_requirement"] for row in rows), rows)


def available_payment(snapshot, minimum_dscr: Decimal) -> Decimal:
    capacity = snapshot.get("capacity", {})
    if not capacity.get("source"):
        raise InputError("capacity.source is required")
    # Operating cash available for debt service must be supplied independently
    # of model DSCR; model DSCR is not an algebraic substitute for cash flow.
    try:
        cash = money(capacity["monthly_cash_available_for_debt_service"])
        existing = money(capacity["existing_monthly_debt_service"])
    except KeyError as exc:
        raise InputError(f"Missing capacity input: {exc}") from exc
    if existing < 0:
        raise InputError("Negative existing debt service")
    return max(Decimal(0), cash / minimum_dscr - existing)


def candidate_amounts(requested, maximum, minimum, step, budget):
    """Descending exhaustive grid; no assumption that model PD is monotone."""
    upper = money(min(requested, maximum))
    lower = money(minimum)
    if upper < lower:
        return []
    first_grid = (upper / step).to_integral_value(rounding=ROUND_FLOOR) * step
    count = max(0, int((first_grid - lower) // step) + 1) if first_grid >= lower else 0
    if count + 2 > budget:
        raise ConfigurationError("Candidate grid exceeds max_candidates; increase step or budget")
    values = {upper, lower}
    values.update(first_grid - step * i for i in range(count))
    return sorted(values, reverse=True)


def evaluate_economics(offer, scoring, inputs, policy):
    """Monthly expected contribution after funding, losses and required return.

    EAD is opening principal. Funding/costs apply to survival at month start;
    interest is collected only on survival to month end. Default loss is LGD
    times opening EAD times the unconditional monthly default probability.
    Capital cost is an explicit policy charge on EAD; no regulatory claim.
    """
    annual_cost = (inputs["key_rate_pct"] + inputs["funding_spread_pct"]
                   + inputs["operating_cost_pct"] + inputs["required_margin_pct"]
                   + policy.capital_cost_pct) / Decimal(1200)
    lgd = inputs["lgd_pct"] / 100
    survival = Decimal(1)
    contribution = Decimal(0)
    expected_loss = Decimal(0)
    discount = 1 + policy.discount_rate_pct / Decimal(1200)
    for row, hazard in zip(offer.monthly_schedule, scoring.monthly_hazard):
        probability = Decimal(str(hazard))
        end_survival = survival * (1 - probability)
        loss = survival * probability * row["opening_balance"] * lgd
        cost = survival * row["opening_balance"] * annual_cost
        income = end_survival * row["interest"]
        contribution += (income - cost - loss) / discount ** row["month"]
        expected_loss += loss / discount ** row["month"]
        survival = end_survival
    return {"expected_contribution_after_required_return": money(contribution),
            "discounted_expected_credit_loss": money(expected_loss),
            "method": "monthly_survival_opening_ead_v1", "profitable": contribution >= 0,
            "fees_included": False}
