"""Build only features whose meaning can be established from the snapshot.

Financial/model-specific aggregates arrive as a versioned, trusted feature
snapshot. We deliberately do not equate account credits with revenue or the
central bank key rate with the synthetic training macro_stress variable.
"""
import math
from datetime import date
from decimal import Decimal

from ..schemas import InputError

BASE_FEATURES = (
    "age_months", "industry", "entity_type", "monthly_revenue", "revenue_trend_12m",
    "revenue_volatility", "operating_margin", "cash_buffer_months", "dscr",
    "debt_to_revenue", "prior_overdue_30d", "requested_amount", "annual_rate", "macro_stress",
)
INDUSTRIES = {"retail", "services", "manufacturing", "construction", "transport", "agriculture"}
ENTITY_MAP = {"LEGAL_ENTITY": "OOO", "INDIVIDUAL_ENTREPRENEUR": "IP"}


def build_automatic_db_inputs(snapshot, transactions, statements, obligations, history):
    """Explicit MVP proxies with observed coverage checks, no invented history."""
    if not snapshot.get("automatic_input_policy", {}).get("demo_only"):
        raise InputError("Automatic DB inputs require the explicit MVP input policy")
    if not history or any(row.get("overdue_days") is None for row in history):
        raise InputError("Insufficient credit repayment history to determine prior_overdue_30d")
    for row in obligations:
        if row.get("outstanding_balance") is not None and row["outstanding_balance"] < 0:
            raise InputError("Negative debt balance")
    proxy = dict(snapshot, feature_contract_version="db_proxy_v2",
                 internal_confirmations={"financial_history_complete": True})
    # This internal flag enables the shared calculator after source coverage is
    # checked there. It is not copied into the external snapshot as a claim that
    # every account or credit bureau exposure has been verified.
    updates = build_db_proxy_inputs(proxy, transactions, statements, obligations, history)
    updates["feature_contract_version"] = "db_auto_v3"
    updates["input_limitations"] = [
        "Observed monthly revenue coverage does not prove coverage of all borrower bank accounts",
        "Credit history coverage across all lenders requires bank employee confirmation",
        "Statement operating profit approximates operating cash flow",
        "Synthetic base_debt is approximated from existing debt service / (0.16 * historical mean monthly revenue); observed outstanding/revenue is kept separately",
        "macro_stress is an explicit neutral synthetic scenario, not a measured index",
    ]
    return updates


def build_db_proxy_inputs(snapshot: dict, transactions: list, statements: list,
                          obligations: list, repayment_history: list) -> dict:
    """Versioned opt-in synthetic-to-DB feature contracts.

    Legacy v1 retains its old outstanding/revenue approximation for research
    comparisons only. v2 estimates the generator's latent base_debt by inverting
    its debt-service equation and applies its original clipping transforms.
    Operating profit remains a cash-flow proxy. Neither version is calibrated
    to real bank outcomes. Industry and macro_stress remain explicit inputs.
    """
    contract = snapshot.get("feature_contract_version")
    diagnostic = contract in ("db_diagnostic_v1", "db_diagnostic_v2")
    corrected = contract in ("db_proxy_v2", "db_diagnostic_v2")
    if contract not in ("db_proxy_v1", "db_proxy_v2", "db_diagnostic_v1", "db_diagnostic_v2"):
        raise InputError("DB proxy requires explicit feature_contract_version=db_proxy_v1")
    confirmed = snapshot.get("internal_confirmations", {})
    if confirmed.get("financial_history_complete") is not True:
        raise InputError("DB proxy requires confirmed financial history coverage")
    as_of = date.fromisoformat(str(snapshot["as_of"])[:10])
    current_index = as_of.year * 12 + as_of.month - 1
    # Only fully completed calendar months, including the same month last year.
    indices = list(range(current_index - 13, current_index))
    revenue = {index: Decimal(0) for index in indices}
    observed = set()
    for row in transactions:
        day = date.fromisoformat(str(row["transaction_date"])[:10])
        index = day.year * 12 + day.month - 1
        if index not in revenue or row.get("direction") != "IN" or row.get("operation_category") != "REVENUE":
            continue
        if str(row.get("currency", "RUB")).strip() != "RUB":
            raise InputError("DB proxy does not convert foreign currency revenues")
        revenue[index] += Decimal(str(row["amount"]))
        observed.add(index)
    complete = observed == set(indices) and all(value > 0 for value in revenue.values())
    if not complete and not diagnostic:
        raise InputError("DB proxy needs 13 complete positive-revenue months; no zero-filling missing history")
    measured = sorted(observed) if diagnostic else indices
    if diagnostic and (len(measured) < 6 or measured[-1] != current_index - 1
                       or any(b - a != 1 for a, b in zip(measured, measured[1:]))):
        raise InputError("Diagnostic proxy needs >=6 consecutive observed months ending at last completed month")
    series = [float(revenue[index]) for index in measured]
    if any(value <= 0 for value in series):
        raise InputError("Nonpositive observed monthly revenue")
    last = series[-1]
    window = series[-12:]
    mean = sum(window) / len(window)
    volatility = math.sqrt(sum((value - mean) ** 2 for value in window) / len(window)) / mean
    trend = last / series[0] - 1
    if diagnostic and not complete:
        center = (len(series) - 1) / 2
        logs = [math.log(value) for value in series]
        average_log = sum(logs) / len(logs)
        slope = sum((i - center) * (value - average_log) for i, value in enumerate(logs)) / sum((i - center) ** 2 for i in range(len(series)))
        trend = max(-0.9, min(3, math.exp(max(-20, min(20, slope * 12))) - 1))
    usable = [row for row in statements if row.get("is_verified") is True
              and date.fromisoformat(str(row["period_end"])[:10]) <= as_of]
    if not usable:
        raise InputError("DB proxy needs a verified financial statement")
    usable.sort(key=lambda row: str(row["period_end"]), reverse=True)
    statement = usable[0]
    if sum(str(row["period_end"]) == str(statement["period_end"]) for row in usable) > 1:
        raise InputError("Ambiguous latest financial statement; select upstream")
    for key in ("operating_profit", "revenue", "cash_and_equivalents"):
        if statement.get(key) is None:
            raise InputError(f"DB proxy requires financial_statements.{key}")
    if Decimal(str(statement["revenue"])) <= 0:
        raise InputError("Nonpositive statement revenue")
    margin = float(statement["operating_profit"]) / float(statement["revenue"])
    active = [row for row in obligations if row.get("obligation_status") in ("ACTIVE", "OVERDUE", "RESTRUCTURED")]
    if any(row.get("obligation_status") == "UNKNOWN" for row in obligations):
        raise InputError("Unknown obligation status")
    if any(row.get(key) is None for row in active for key in ("monthly_payment", "outstanding_balance")):
        raise InputError("Debt coverage is incomplete")
    service = sum(float(row["monthly_payment"]) for row in active)
    debt = sum(float(row["outstanding_balance"]) for row in active)
    if service <= 0 or (margin <= 0 and not corrected):
        raise InputError("DB proxy DSCR is undefined/nonpositive; supply a reviewed model feature snapshot")
    prior = any((row.get("overdue_days") or 0) >= 30 for row in repayment_history)
    supplied = dict(snapshot.get("model_features", {}))
    supplied.update(monthly_revenue=last, revenue_trend_12m=trend,
                    revenue_volatility=volatility, operating_margin=margin,
                    cash_buffer_months=float(statement["cash_and_equivalents"]) / last,
                    dscr=last * margin / service, debt_to_revenue=debt / last,
                    prior_overdue_30d=int(prior))
    sources = dict(snapshot.get("feature_provenance", {}))
    for key in ("monthly_revenue", "revenue_trend_12m", "revenue_volatility"):
        sources[key] = "db_proxy_v1: complete calendar RUB REVENUE inflows; last completed month"
    if diagnostic:
        sources["revenue_trend_12m"] = ("db_diagnostic_v1: exact 13-point ratio" if complete else
            f"db_diagnostic_v1: APPROXIMATION annualized log-linear slope over {len(series)} observed completed months; no fabricated transactions")
        sources["revenue_volatility"] = f"db_diagnostic_v1: population CV over {len(window)} observed completed months"
    sources.update(
        operating_margin="db_proxy_v1: verified statement operating_profit/revenue; CASH FLOW PROXY",
        cash_buffer_months="db_proxy_v1: latest verified cash / last monthly revenue",
        dscr="db_proxy_v1: last revenue * statement margin / existing monthly payments; CASH FLOW PROXY",
        debt_to_revenue="db_proxy_v1: outstanding debt / monthly revenue; PROXY FOR SYNTHETIC BASE_DEBT",
        prior_overdue_30d="db_proxy_v1: complete credit repayment history, overdue_days>=30",
    )
    updates = {"model_features": supplied, "feature_provenance": sources}
    if corrected:
        # In generate_survival_v2 the latent base_debt is NOT outstanding / revenue.
        # Existing service = latent base_revenue * base_debt * 0.16.
        # Historical mean revenue approximates unobserved base_revenue. This
        # remains an explicit synthetic-model proxy, not a banking debt ratio.
        raw = {"dscr": max(0, last * margin) / service,
               "debt_to_revenue": service / (mean * .16),
               "cash_buffer_months": supplied["cash_buffer_months"],
               "revenue_trend_12m": supplied["revenue_trend_12m"],
               "revenue_volatility": supplied["revenue_volatility"],
               "operating_margin": margin}
        bounds = {"dscr": (.05, 8), "debt_to_revenue": (.03, 3), "cash_buffer_months": (0,18),
                  "revenue_trend_12m": (-.9,3), "revenue_volatility": (0,3), "operating_margin": (-.28,.48)}
        adjusted = {}
        for key, value in raw.items():
            low, high = bounds[key]
            supplied[key] = max(low, min(high, value))
            if supplied[key] != value:
                adjusted[key] = {"raw": value, "model_input": supplied[key], "range": [low, high]}
        sources["debt_to_revenue"] = "db_proxy_v2: existing monthly debt service / (0.16 * observed historical mean revenue), proxy for generator base_debt; clipped to generator [.03,3]"
        sources["dscr"] = "db_proxy_v2: max(0,last revenue * statement margin)/existing debt service; same generator clipping [.05,8]"
        for key in bounds:
            if key not in ("debt_to_revenue", "dscr"):
                sources[key] += "; generator-domain clipping " + str(bounds[key])
        updates["feature_adjustments"] = adjusted
        updates["financial_observations"] = {"outstanding_debt_to_monthly_revenue": debt / last,
            "raw_dscr": raw["dscr"], "existing_monthly_debt_service": service,
            "monthly_cash_available_for_debt_service": last * margin,
            "historical_mean_revenue": mean}
    if not snapshot.get("capacity"):
        updates["capacity"] = {"monthly_cash_available_for_debt_service": str(last * margin),
                               "existing_monthly_debt_service": str(service),
                               "source": "db_proxy_v1 operating profit proxy; explicitly selected by backend"}
    return updates


def build_features(snapshot: dict, annual_rate_pct, amount=None) -> tuple[dict, dict]:
    application, company = snapshot["application"], snapshot["company"]
    supplied = snapshot.get("model_features", {})
    provenance = snapshot.get("feature_provenance", {})
    if not snapshot.get("feature_contract_version"):
        raise InputError("feature_contract_version is required for financial aggregates")
    features = {key: supplied[key] for key in BASE_FEATURES if key in supplied}
    sources = {key: provenance.get(key) for key in features}
    as_of = date.fromisoformat(str(snapshot["as_of"])[:10])
    if company.get("registration_date"):
        registered = date.fromisoformat(str(company["registration_date"])[:10])
        if registered > as_of:
            raise InputError("Registration is after assessment date")
        features["age_months"] = ((as_of.year - registered.year) * 12 + as_of.month
                                  - registered.month - (as_of.day < registered.day))
        sources["age_months"] = "companies.registration_date; completed calendar months"
    if company.get("entity_type") not in ENTITY_MAP:
        raise InputError("Unknown borrower entity_type")
    features["entity_type"] = ENTITY_MAP[company["entity_type"]]
    sources["entity_type"] = "companies.entity_type"
    features["requested_amount"] = float(amount if amount is not None else application["requested_amount"])
    features["annual_rate"] = float(annual_rate_pct) / 100
    sources.update(requested_amount="candidate offer amount", annual_rate="individual offer rate / 100")
    missing = [key for key in BASE_FEATURES if features.get(key) is None]
    if missing:
        raise InputError(f"Upstream feature snapshot is incomplete: {missing}")
    if any(not sources.get(key) for key in BASE_FEATURES):
        raise InputError("Every supplied model feature must have feature_provenance")
    if features["industry"] not in INDUSTRIES:
        raise InputError("industry must use the training taxonomy; explicit OKVED mapping required")
    for key in BASE_FEATURES:
        if key not in ("industry", "entity_type"):
            try:
                features[key] = float(features[key])
            except (TypeError, ValueError) as exc:
                raise InputError(f"Non-numeric feature: {key}") from exc
            if not math.isfinite(features[key]):
                raise InputError(f"Non-finite feature: {key}")
    for key in ("age_months", "revenue_volatility", "cash_buffer_months", "debt_to_revenue", "annual_rate"):
        if features[key] < 0:
            raise InputError(f"Negative feature: {key}")
    if features["monthly_revenue"] <= 0 or features["dscr"] <= 0:
        raise InputError("monthly_revenue and dscr must be positive")
    if features["prior_overdue_30d"] not in (0, 1):
        raise InputError("prior_overdue_30d must be binary")
    return features, sources
