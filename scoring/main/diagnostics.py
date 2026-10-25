"""What-if financial comparison; no application lifecycle changes or DB writes."""
import json
from datetime import date
from decimal import Decimal

from .application_service import DEFAULTS_PATH, industry_from_okved
from .database import _one, _rows
from .ml_scoring.feature_builder import build_db_proxy_inputs, build_features
from .decision_engine.policy import annual_pd_limit, validate_economic_inputs
from .pipeline import evaluate_application
from .schemas import ConfigurationError, InputError


def diagnose_company(connection, company, predictor, policy, as_of, product_code, amount, term,
                     feature_contract="db_diagnostic_v2"):
    if not policy.demo_only:
        raise ConfigurationError("Diagnostic comparison is only available with an explicit demo policy")
    defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    cid = company["company_id"]
    profile = _one(_rows(connection, "SELECT * FROM public.companies WHERE company_id=:id", id=cid), "company")
    if profile.get("registration_date") is None:
        raise InputError("Missing registration_date: model age cannot be determined")
    category = industry_from_okved(profile.get("okved_main"), defaults["industry_by_okved_division"])
    terms = _one(_rows(connection, """SELECT * FROM public.credit_product_terms WHERE product_code=:p
        AND (effective_from IS NULL OR effective_from<=:d) AND (effective_to IS NULL OR effective_to>=:d)""",
        p=product_code, d=as_of), "terms")
    rate = _one(_rows(connection, "SELECT * FROM public.credit_product_rate_options WHERE terms_id=:id AND additional_service_name IS NULL", id=terms["terms_id"]), "base rate")
    repayment = _one(_rows(connection, "SELECT * FROM public.credit_product_repayment_options WHERE terms_id=:id AND repayment_type=:kind",
                          id=terms["terms_id"], kind=defaults["repayment_preferences"][product_code]), "repayment")
    risk = _one(_rows(connection, """SELECT * FROM public.risk_policy_parameters WHERE product_code=:p
        AND effective_from<=:d AND (effective_to IS NULL OR effective_to>=:d)""", p=product_code, d=as_of), "risk policy")
    macros = _rows(connection, "SELECT * FROM public.macro_indicators WHERE indicator_code='KEY_RATE' AND effective_date<=:d ORDER BY effective_date DESC", d=as_of)
    if not macros:
        raise InputError("Missing key rate")
    macro = _one([row for row in macros if row["effective_date"] == macros[0]["effective_date"]], "latest key rate")
    confirmations = {key: True for key in ("financial_history_complete", "guarantor_requirement_resolved",
                     "legal_checks_clear", "credit_history_checked", "fees_resolved", "purpose_resolved")}
    snapshot = {"as_of": as_of.isoformat(), "company": profile, "terms": terms,
        "product": _one(_rows(connection, "SELECT * FROM public.credit_products WHERE product_code=:p", p=product_code), "product"),
        "application": {"application_id": -cid, "company_id": cid, "product_code": product_code,
                        "requested_amount": str(amount), "requested_term_months": term,
                        "purpose": "Пополнение оборотных средств", "application_status": "SUBMITTED", "missing_data_status": "COMPLETE"},
        "submission_confirmed": True, "internal_confirmations": confirmations,
        "rate_option": rate, "repayment_option": repayment, "risk_policy": risk,
        "individual_annual_rate_pct": str(rate["min_annual_rate_pct"] + Decimal(defaults["pricing_markup_pct"])),
        "individual_rate_source": "DIAGNOSTIC: " + defaults["pricing_description"],
        "pricing_policy": {"demo_only": True, "version": defaults["version"],
                           "maximum_rate_pct": defaults["maximum_draft_rate_pct"], "step_pct": defaults["draft_rate_step_pct"],
                           "source": defaults["pricing_ceiling_description"]},
        "key_rate_pct": macro["indicator_value"], "key_rate_source": macro["source"], "key_rate_effective_date": macro["effective_date"],
        "economics_source": "DB policy:" + risk["policy_version"],
        "feature_contract_version": feature_contract, "model_features": {"industry": category, "macro_stress": defaults["macro_stress_scenario"]},
        "feature_provenance": {"industry": "diagnostic project OKVED mapping", "macro_stress": "diagnostic neutral synthetic scenario 0"}}
    if product_code != "R01":
        unit = terms["tranche_term_unit"]
        maximum = rate.get("max_tranche_term_days" if unit == "DAYS" else "max_tranche_term_months") or terms["max_tranche_term_value"]
        snapshot["product_details"] = {"max_tranche_term_value": maximum, "max_tranche_term_unit": unit}
    transactions = _rows(connection, "SELECT * FROM public.bank_transactions WHERE company_id=:id AND transaction_date<CAST(:d AS date)+INTERVAL '1 day'", id=cid, d=as_of)
    statements = _rows(connection, "SELECT * FROM public.financial_statements WHERE company_id=:id AND period_end<=:d", id=cid, d=as_of)
    obligations = _rows(connection, "SELECT * FROM public.credit_obligations WHERE company_id=:id AND (contract_date IS NULL OR contract_date<=:d)", id=cid, d=as_of)
    history = _rows(connection, "SELECT h.* FROM public.credit_repayment_history h JOIN public.credit_obligations o USING(obligation_id) WHERE o.company_id=:id AND h.period_date<=:d", id=cid, d=as_of)
    snapshot.update(build_db_proxy_inputs(snapshot, transactions, statements, obligations, history))
    assumptions = ["Hypothetical new request only; existing CANCELLED applications are untouched",
                   "Conditional financial outcome assuming upstream questionnaire and internal checks completed; not an actual approval",
                   "Partial history uses explicitly labeled annualized trend approximation; current month excluded",
                   "Neutral synthetic macro scenario; operating-profit cash-flow proxy; indicative risk-based pricing capped at 30% (explicit MVP assumption)"]
    result = evaluate_application(snapshot, policy, predictor)
    result.audit["diagnostic_only"] = True
    result.audit["diagnostic_assumptions"] = assumptions
    output = result.to_dict()
    features, _ = build_features(snapshot, snapshot["individual_annual_rate_pct"])
    requested = predictor.predict(features, term)
    output["diagnostic_requested_risk"] = dict(
        annual_pd_limit(snapshot["individual_annual_rate_pct"], validate_economic_inputs(snapshot)),
        pd_application_1y=requested.cumulative_pd[11], pd_application_term=requested.pd_term)
    output["diagnostic_features"] = features
    output["financial_observations"] = snapshot.get("financial_observations", {})
    output["feature_adjustments"] = snapshot.get("feature_adjustments", {})
    generator_bounds = {"dscr": (.05, 8), "debt_to_revenue": (.03, 3),
                        "cash_buffer_months": (0, 18), "operating_margin": (-.28, .48),
                        "annual_rate": (.10, .36)}
    output["generator_range_warnings"] = sorted(set(snapshot.get("feature_adjustments", {})) | {
        key for key, (low, high) in generator_bounds.items() if not low <= features[key] <= high})
    return output
