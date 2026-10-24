"""Resolve a demo assessment by application ID using explicit server policy.

No browser-supplied financial facts and no implied client consent. Unknown
checks remain review items. Lack of history never becomes synthetic observations.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .database import _one, _rows
from .schemas import ConfigurationError, InputError

DEFAULTS_PATH = Path(__file__).parent / "decision_engine/application_defaults.json"


def industry_from_okved(okved, mapping):
    division = str(okved or "").strip().split(".")[0]
    if len(division) != 2 or not division.isdigit():
        raise InputError("Missing/invalid main OKVED for industry mapping")
    for key, category in mapping.items():
        bounds = key.split("-")
        if int(bounds[0]) <= int(division) <= int(bounds[-1]):
            return category
    raise InputError(f"No approved MVP industry mapping for OKVED division {division}")


def automatic_context(connection, application_id, policy, as_of=None):
    defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    if defaults["demo_only"] and not policy.demo_only:
        raise ConfigurationError("Application-ID defaults are an explicitly marked MVP policy")
    as_of = as_of or date.today()
    application = _one(_rows(connection, "SELECT * FROM public.credit_applications WHERE application_id=:id", id=application_id), "application")
    company = _one(_rows(connection, "SELECT * FROM public.companies WHERE company_id=:id", id=application["company_id"]), "company")
    if application.get("missing_data_status") != "COMPLETE":
        raise InputError("Questionnaire completeness has not been resolved by the upstream service")
    if company.get("registration_date") is None:
        raise InputError("Company registration date is required for model age_months")
    submission = _rows(connection, "SELECT confirmed_at FROM public.application_details WHERE application_id=:id", id=application_id)
    if not submission or not submission[0]["confirmed_at"]:
        raise InputError("Submission has not been confirmed")
    product = application["product_code"]
    terms = _one(_rows(connection, """SELECT * FROM public.credit_product_terms WHERE product_code=:p
        AND (effective_from IS NULL OR effective_from<=:d) AND (effective_to IS NULL OR effective_to>=:d)""",
                       p=product, d=as_of), "effective catalog version")
    # Existing draft offer is the explicit source for individual conditions.
    offers = _rows(connection, """SELECT * FROM public.application_product_terms WHERE application_id=:id
        AND offer_status IN ('DRAFT','PROPOSED')
        AND (offered_conditions->>'generated_by' IS DISTINCT FROM 'AURELIUS_SCORING')
        ORDER BY created_at DESC,offer_id DESC""", id=application_id)
    if offers:
        indicative = False
        offer = offers[0]
        if offer["terms_id"] != terms["terms_id"]:
            raise InputError("Existing offer uses another terms version; resolve before assessment")
        rate_id, repayment_id = offer["rate_option_id"], offer["repayment_option_id"]
        rate_pct = offer["offered_annual_rate_pct"]
        if rate_pct is None or rate_id is None or repayment_id is None:
            raise InputError("Existing draft offer lacks rate/repayment inputs")
        rate_source = f"application_product_terms.offer_id={offer['offer_id']}"
    else:
        indicative = True
        rate = _one(_rows(connection, """SELECT * FROM public.credit_product_rate_options
            WHERE terms_id=:id AND additional_service_name IS NULL""", id=terms["terms_id"]), "base rate option")
        repayment = _one(_rows(connection, """SELECT * FROM public.credit_product_repayment_options
            WHERE terms_id=:id AND repayment_type=:kind""", id=terms["terms_id"], kind=defaults["repayment_preferences"][product]), "default repayment option")
        if rate["min_annual_rate_pct"] is None:
            raise ConfigurationError("Base rate option has no lower bound")
        rate_pct = rate["min_annual_rate_pct"] + Decimal(defaults["pricing_markup_pct"])
        rate_id, repayment_id = rate["rate_option_id"], repayment["repayment_option_id"]
        rate_source = defaults["version"] + ":" + defaults["pricing_description"]
    category = industry_from_okved(company.get("okved_main"), defaults["industry_by_okved_division"])
    # Do not assert source coverage solely because at least one record exists.
    # db_auto_v2 validates observed windows/verification and reports uncertainty.
    context = {
        "as_of": as_of.isoformat(), "terms_id": terms["terms_id"], "rate_option_id": rate_id,
        "repayment_option_id": repayment_id, "individual_annual_rate_pct": str(rate_pct),
        "individual_rate_source": rate_source, "feature_contract_version": "db_auto_v3",
        "model_features": {"industry": category, "macro_stress": defaults["macro_stress_scenario"]},
        "feature_provenance": {"industry": defaults["version"] + ":companies.okved_main; " + defaults["industry_description"],
                               "macro_stress": defaults["version"] + ":" + defaults["macro_stress_description"]},
        "internal_confirmations": {}, "automatic_input_policy": defaults,
    }
    if indicative:
        context["pricing_policy"] = {"demo_only": True, "version": defaults["version"],
            "maximum_rate_pct": defaults["maximum_draft_rate_pct"],
            "step_pct": defaults["draft_rate_step_pct"],
            "source": defaults["pricing_ceiling_description"]}
    return context
