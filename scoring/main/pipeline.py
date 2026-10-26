"""Single entry point for blocks 4–6; also runnable with python -m main.pipeline."""
import argparse
import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from .credit_offer.calculator import available_payment, build_offer, candidate_amounts, evaluate_economics
from .credit_offer.pricing import candidate_rates
from .decision_engine.engine import eligibility, reason, risk_reasons
from .decision_engine.policy import Policy, annual_pd_limit, validate_economic_inputs
from .ml_scoring.feature_builder import build_features
from .ml_scoring.predictor import Predictor
from .schemas import Assessment, ConfigurationError, InputError, json_value, money


def evaluate_application(snapshot: dict, policy: Policy, predictor=None) -> Assessment:
    """Evaluate an immutable trusted snapshot, with no DB writes or network calls.

    Returns the largest passing amount on the policy grid, capped by request.
    A model feature depending on candidate debt must be supplied by a dedicated
    builder before using a different feature contract. The supplied training
    DSCR describes existing debt at origination and remains frozen here.
    """
    application = snapshot["application"]
    result = Assessment(int(application["application_id"]), "MANUAL_REVIEW", "ELIGIBLE", [], policy.version)
    fingerprint = hashlib.sha256(json.dumps(json_value({"snapshot": snapshot, "policy": asdict(policy)}),
                                              sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    result.audit = {"input_fingerprint": fingerprint, "demo_only": policy.demo_only,
                    "as_of": snapshot["as_of"], "policy": json_value(asdict(policy)),
                    "snapshot": json_value(snapshot)}
    blocked, review = eligibility(snapshot)
    if blocked:
        result.decision, result.eligibility_status, result.reasons = "REJECT", "INELIGIBLE", blocked
        result.automatic_recommendation = "NEGATIVE"
        return result
    if review and not snapshot.get("automatic_input_policy"):
        result.reasons = review
        return result
    economic = validate_economic_inputs(snapshot)
    if snapshot.get("automatic_input_policy"):
        review.append(reason("MVP_INPUTS_CONFIRMATION", "Bank employee must confirm indicative pricing, financial source coverage and model proxy assumptions"))
    if snapshot.get('reported_company_facts'):
        review.append(reason('REPORTED_COMPANY_FACTS', 'Application-scoped company facts require independent employee verification'))
        result.audit['reported_company_facts'] = snapshot['reported_company_facts']
    if snapshot.get("economic_policy_metadata", {}).get("demo_only") and not policy.demo_only:
        raise ConfigurationError("Seeded MVP economics requires an explicitly marked demo policy")
    if snapshot.get("feature_contract_version") in ("db_proxy_v1", "db_proxy_v2", "db_auto_v2", "db_auto_v3", "db_diagnostic_v1", "db_diagnostic_v2") and not policy.demo_only:
        raise ConfigurationError("db_proxy_v1 is limited to explicitly marked demo policies")
    try:
        rate = Decimal(str(snapshot["individual_annual_rate_pct"]))
    except (KeyError, ArithmeticError) as exc:
        raise ConfigurationError("An individual annual rate is required; catalog 'from' is insufficient") from exc
    if not rate.is_finite() or rate < 0 or not snapshot.get("individual_rate_source"):
        raise ConfigurationError("Invalid individual rate or missing source")
    rate_option = snapshot["rate_option"]
    for field, compare in (("min_annual_rate_pct", lambda x, y: x < y),
                           ("max_annual_rate_pct", lambda x, y: x > y)):
        if rate_option.get(field) is not None and compare(rate, Decimal(str(rate_option[field]))):
            raise ConfigurationError("Individual rate is outside selected rate option")
    result.risk_assessment = annual_pd_limit(rate, economic) if economic["lgd_pct"] > 0 else {
        "method": policy.decision_method, "pd_limit_1y": None, "comparison_horizon_months": 12}
    if policy.decision_method == "annual_pd_limit" and economic["lgd_pct"] <= 0:
        raise ConfigurationError("annual_pd_limit requires LGD > 0")
    result.risk_assessment.update(pd_application_1y=None, pd_application_term=None,
                                  scored_amount=None, term_months=application["requested_term_months"],
                                  decision_method=policy.decision_method)
    if policy.decision_method == "monthly_cashflow" and not policy.allow_unvalidated_term_pd:
        result.reasons = [reason("FULL_CURVE_REVIEW", "Monthly economics requires explicit authorization of full-term model curves")]
        return result
    budget = available_payment(snapshot, policy.minimum_dscr)
    result.audit["available_monthly_payment"] = str(money(budget))
    features, sources = build_features(snapshot, rate)
    minimum_age = snapshot["terms"].get("min_business_age_months")
    if minimum_age is not None and features["age_months"] < minimum_age:
        result.decision, result.eligibility_status = "REJECT", "INELIGIBLE"
        result.automatic_recommendation = "NEGATIVE"
        result.reasons = [reason("BUSINESS_TOO_YOUNG", "Business age is below catalog minimum")]
        return result
    predictor = predictor or Predictor()
    result.audit["feature_sources"] = sources
    result.audit["feature_adjustments"] = snapshot.get("feature_adjustments", {})
    result.audit["financial_observations"] = snapshot.get("financial_observations", {})
    result.audit["model_sha256"] = getattr(predictor, "model_sha256", None)
    result.audit["economics_inputs"] = json_value(economic)
    result.audit["amount_search"] = {"method": "descending_exhaustive_grid", "step": str(policy.amount_step),
                                   "maximum_is_grid_bound": True}
    terms = snapshot["terms"]
    rates = candidate_rates(snapshot, rate, policy)
    result.audit["pricing_search"] = {"rates_pct": [str(r) for r in rates],
                                      "source": snapshot.get("pricing_policy", {}).get("source", "Fixed individual quote"),
                                      "objective": "largest feasible amount, then lowest passing rate"}
    candidates = candidate_amounts(money(application["requested_amount"]), money(terms["max_amount"]),
                                   money(terms["min_amount"]), policy.amount_step, policy.max_candidates)
    failures = {}
    evaluations = []
    for amount, candidate_rate in ((amount, r) for amount in candidates for r in rates):
        offer = build_offer(snapshot, amount, candidate_rate)
        if offer.affordability_payment > budget:
            failures["CAPACITY"] = reason("INSUFFICIENT_CAPACITY", "Debt service capacity is insufficient")
            continue
        candidate_features = dict(features, requested_amount=float(amount), annual_rate=float(candidate_rate) / 100)
        scoring = predictor.predict(candidate_features, application["requested_term_months"])
        if result.scoring is None:
            result.scoring = scoring
            result.audit["scored_features"] = candidate_features
        risks = risk_reasons(scoring, policy)
        economics = evaluate_economics(offer, scoring, economic, policy)
        candidate_limit = annual_pd_limit(candidate_rate, economic) if economic["lgd_pct"] > 0 else {}
        risk_details = dict(result.risk_assessment, **candidate_limit,
                            pd_application_1y=scoring.cumulative_pd[11],
                            pd_application_term=scoring.pd_term,
                            term_months=scoring.term_months,
                            scored_amount=str(amount),
                            annual_rate_pct=str(candidate_rate),
                            pd_1y_evaluated=12 in scoring.pd_by_horizon,
                            decision_method=policy.decision_method)
        if result.scoring is scoring:
            result.risk_assessment = risk_details
        if policy.decision_method == "annual_pd_limit":
            if 12 not in scoring.pd_by_horizon and not policy.allow_unvalidated_term_pd:
                result.risk_assessment = risk_details
                result.reasons = [reason("PD12_REVIEW", "PD12 is not independently evaluated for this contractual term")]
                result.audit["evaluations"] = evaluations
                return result
            passed = risk_details["positive_headroom"] and risk_details["pd_application_1y"] <= risk_details["pd_limit_1y"]
            risk_details["passes_pd_limit"] = passed
        else:
            passed = economics["profitable"]
        evaluations.append({"amount": str(amount), "annual_rate_pct": str(candidate_rate), "pd_term": scoring.pd_term,
                            "economics": json_value(economics), "risk_reasons": risks,
                            "risk_assessment": risk_details})
        if risks:
            failures["RISK"] = risks[0]
            continue
        if not passed:
            failures["ECONOMICS"] = reason("PD_LIMIT_EXCEEDED" if policy.decision_method == "annual_pd_limit" else "NEGATIVE_EXPECTED_RETURN",
                                             "PD12 exceeds annual economic limit or income headroom is nonpositive"
                                             if policy.decision_method == "annual_pd_limit" else "Expected return is below policy requirement")
            continue
        offer.economics = economics
        result.offer, result.scoring = offer, scoring
        result.audit["scored_features"] = candidate_features
        result.decision = "MANUAL_REVIEW"
        result.automatic_recommendation = "REVIEW_REQUIRED" if review else "POSITIVE"
        result.risk_assessment = risk_details
        result.reasons = [reason("BANK_CONFIRMATION_REQUIRED" if amount == money(application["requested_amount"]) else "REDUCED_AMOUNT",
                                 "Automatic checks passed; bank employee confirmation required"
                                 if amount == money(application["requested_amount"])
                                 else "A smaller amount passes; bank employee confirmation required")]
        result.reasons.extend(review)
        break
    else:
        result.decision = "REJECT"
        result.automatic_recommendation = "NEGATIVE"
        result.reasons = list(failures.values()) or [reason("NO_FEASIBLE_AMOUNT", "No candidate amount is available")]
    result.audit["evaluations"] = evaluations
    if result.scoring:
        result.audit["pd_storage_horizon_months"] = max(result.scoring.pd_by_horizon)
        result.audit["full_term_pd_is_outside_evaluated_horizons"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Offline trusted application snapshot")
    parser.add_argument("--policy", type=Path, default=Path(__file__).parent / "decision_engine/policy.demo.json")
    parser.add_argument("--application-id", type=int)
    parser.add_argument("--context", type=Path, help="Trusted feature/capacity/rate inputs for DB mode")
    parser.add_argument("--save", action="store_true", help="Persist in DB mode only")
    args = parser.parse_args()
    policy = Policy.load(args.policy)
    try:
        if args.snapshot:
            if args.save or args.application_id or args.context:
                parser.error("--snapshot is offline; do not combine with DB arguments")
            result = evaluate_application(json.loads(args.snapshot.read_text(encoding="utf-8")), policy)
            output = result.to_dict()
        else:
            if not args.application_id:
                parser.error("DB mode requires --application-id")
            from .database import run_application
            output = run_application(args.application_id,
                                     json.loads(args.context.read_text(encoding="utf-8")) if args.context else None,
                                     policy, save=args.save)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except (ConfigurationError, InputError) as exc:
        parser.exit(2, f"{type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
