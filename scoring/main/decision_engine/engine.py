"""Rules operate on trusted server-side snapshots, never arbitrary client SQL."""
import operator
from datetime import date
from decimal import Decimal

from ..schemas import ConfigurationError, InputError


def reason(code, message):
    return {"code": code, "message": message}


def eligibility(snapshot):
    application, company, terms = (snapshot[k] for k in ("application", "company", "terms"))
    blocked, review = [], []
    if application.get("company_id") != company.get("company_id"):
        raise InputError("Application/company identity mismatch")
    if application.get("application_status") not in ("SUBMITTED", "UNDER_REVIEW"):
        raise InputError("Only SUBMITTED or UNDER_REVIEW applications can be assessed")
    if application.get("missing_data_status") != "COMPLETE":
        raise InputError("Questionnaire completeness must be resolved upstream")
    if not snapshot.get("submission_confirmed"):
        raise InputError("A confirmed submission is required")
    for row in (terms, snapshot["product"]):
        if row.get("product_code") != application["product_code"]:
            raise InputError("Product identity mismatch")
    if not snapshot["product"].get("active"):
        blocked.append(reason("PRODUCT_INACTIVE", "Product is inactive"))
    for key in ("rate_option", "repayment_option"):
        if snapshot[key].get("terms_id") != terms["terms_id"]:
            raise InputError(f"{key} belongs to another catalog version")
    as_of = date.fromisoformat(str(snapshot["as_of"])[:10])
    for row in (terms, snapshot.get("risk_policy", {})):
        for key, is_start in (("effective_from", True), ("effective_to", False)):
            if row.get(key):
                bound = date.fromisoformat(str(row[key])[:10])
                if (is_start and as_of < bound) or (not is_start and as_of > bound):
                    raise ConfigurationError("Catalog/policy is not effective at assessment date")
    if company.get("status") in ("BANKRUPTCY", "LIQUIDATING", "INACTIVE"):
        blocked.append(reason("COMPANY_INACTIVE", "Company is bankrupt, liquidating or inactive"))
    elif company.get("status") != "ACTIVE":
        review.append(reason("COMPANY_STATUS_UNKNOWN", "Company status needs internal review"))
    if company.get("information_reliability_status") != "VERIFIED":
        review.append(reason("COMPANY_NOT_VERIFIED", "Company information is not verified"))
    if snapshot.get("active_bankruptcy"):
        blocked.append(reason("ACTIVE_BANKRUPTCY", "Active bankruptcy proceedings"))
    if snapshot.get("active_overdue"):
        review.append(reason("ACTIVE_OVERDUE", "Current overdue debt requires internal review"))
    allowed = terms.get("allowed_entity_types")
    if allowed and company["entity_type"] not in allowed:
        blocked.append(reason("ENTITY_NOT_ALLOWED", "Borrower type is outside product conditions"))
    if terms.get("allowed_sme_categories") and company.get("sme_category") not in terms["allowed_sme_categories"]:
        review.append(reason("SME_CATEGORY", "SME category does not match confirmed catalog conditions"))
    term = application.get("requested_term_months")
    if type(term) is not int or term <= 0:
        raise InputError("requested_term_months must be an explicit positive integer")
    if terms.get("contract_term_unit") != "MONTHS":
        raise ConfigurationError("Contract term requires an explicit MONTHS catalog bound")
    for key, compare in (("min_contract_term_value", operator.lt), ("max_contract_term_value", operator.gt)):
        if terms.get(key) is not None and compare(term, terms[key]):
            blocked.append(reason("TERM_OUTSIDE_PRODUCT", "Contract term is outside product conditions"))
    for key in ("min_amount", "max_amount"):
        if terms.get(key) is None:
            raise ConfigurationError(f"Missing catalog amount bound: {key}")
    if Decimal(str(application["requested_amount"])) <= 0:
        raise InputError("Requested amount must be positive")
    if Decimal(str(application["requested_amount"])) < Decimal(str(terms["min_amount"])):
        blocked.append(reason("BELOW_PRODUCT_MINIMUM", "Requested amount is below product minimum"))
    confirmations = snapshot.get("internal_confirmations", {})
    if snapshot["rate_option"].get("additional_service_name") or snapshot.get("fees"):
        review.append(reason("SERVICE_PRICING_REVIEW", "Subscription/fee cash flows require a separate pricing adapter"))
    if terms.get("requires_collateral") and not confirmations.get("collateral_verified"):
        review.append(reason("COLLATERAL_REQUIRED", "Required collateral is not verified"))
    if terms.get("guarantor_requirement") in ("REQUIRED", "CONDITIONAL", "UNKNOWN"):
        if not confirmations.get("guarantor_requirement_resolved"):
            review.append(reason("GUARANTOR_CONDITION", "Guarantor requirement needs internal resolution"))
    for key in ("legal_checks_clear", "credit_history_checked", "fees_resolved", "purpose_resolved"):
        if confirmations.get(key) is not True:
            review.append(reason(key.upper(), f"Internal check not resolved: {key}"))
    for purpose in snapshot.get("purposes", []):
        if purpose["purpose_name"].casefold() == str(application.get("purpose", "")).casefold():
            if not purpose["is_allowed"]:
                blocked.append(reason("PURPOSE_PROHIBITED", "Requested purpose is explicitly prohibited"))
    # Arbitrary database field text is only a key in a fixed snapshot namespace.
    facts = snapshot.get("rule_facts", {})
    comparators = {"EQ": operator.eq, "NE": operator.ne, "GT": operator.gt,
                   "GTE": operator.ge, "LT": operator.lt, "LTE": operator.le,
                   "IN": lambda value, limit: value in limit}
    for rule in snapshot.get("eligibility_rules", []):
        if rule.get("terms_id") != terms["terms_id"]:
            raise ConfigurationError("Eligibility rule belongs to another terms version")
        field = rule.get("parameter_name") or rule.get("required_data_field")
        comparison = rule.get("comparison_operator")
        if comparison not in comparators or facts.get(field) is None:
            review.append(reason("RULE_UNRESOLVED", f"Cannot evaluate rule {rule['rule_code']}"))
            continue
        try:
            passed = comparators[comparison](facts[field], rule["threshold_value"])
        except (TypeError, ValueError):
            raise ConfigurationError(f"Incompatible values in rule {rule['rule_code']}")
        if not passed and rule["severity"] != "INFORMATION":
            target = blocked if rule["severity"] == "BLOCK" else review
            target.append(reason(str(rule["rule_code"]), rule["rule_description"]))
    return blocked, review


def risk_reasons(scoring, policy):
    reasons = []
    for horizon, limit in policy.pd_limits.items():
        if horizon > scoring.term_months:
            continue
        if horizon not in scoring.pd_by_horizon and not policy.allow_unvalidated_term_pd:
            reasons.append(reason("PD_HORIZON_UNVALIDATED", f"PD{horizon} is not an evaluated horizon"))
        elif scoring.cumulative_pd[horizon - 1] > limit:
            reasons.append(reason("PD_LIMIT_EXCEEDED", f"PD{horizon} exceeds configured risk appetite"))
    return reasons
