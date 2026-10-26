"""PostgreSQL adapter for the actual versioned schema in bd/.

The calling backend must authenticate the application owner before invocation.
This package has no HTTP endpoint and must not accept a browser's context JSON.
"""
import hashlib
import json
from dataclasses import asdict
from datetime import date

from .config import Settings
from .schemas import ConfigurationError, InputError, json_value


def _rows(connection, sql, **parameters):
    from sqlalchemy import text
    return [dict(row) for row in connection.execute(text(sql), parameters).mappings()]


def _one(rows, label):
    if len(rows) != 1:
        raise ConfigurationError(f"Expected one {label}; found {len(rows)}")
    return rows[0]


def load_snapshot(connection, application_id: int, context: dict) -> dict:
    """Read catalog and identities from DB; enrich only with trusted backend inputs."""
    application = _one(_rows(connection, "SELECT * FROM public.credit_applications WHERE application_id=:id",
                             id=application_id), "application")
    company = _one(_rows(connection, "SELECT * FROM public.companies WHERE company_id=:id",
                         id=application["company_id"]), "company")
    if not context.get("as_of"):
        raise InputError("Explicit as_of date is required")
    as_of = date.fromisoformat(str(context["as_of"])[:10])
    reported_facts = {}
    if context.get('automatic_input_policy', {}).get('demo_only') is True:
        from .application_facts import application_company
        company, reported_facts = application_company(connection, application, company, as_of, demo_only=True)
    product = _one(_rows(connection, "SELECT * FROM public.credit_products WHERE product_code=:p",
                         p=application["product_code"]), "product")
    terms = _rows(connection, """SELECT * FROM public.credit_product_terms WHERE product_code=:p
        AND (effective_from IS NULL OR effective_from <= :d)
        AND (effective_to IS NULL OR effective_to >= :d)""", p=application["product_code"], d=as_of)
    if context.get("terms_id") is not None:
        terms = [row for row in terms if row["terms_id"] == context["terms_id"]]
    terms = _one(terms, "applicable catalog version")
    for key in ("rate_option_id", "repayment_option_id"):
        if context.get(key) is None:
            raise ConfigurationError(f"Select {key} explicitly")
    rate = _one(_rows(connection, """SELECT * FROM public.credit_product_rate_options
        WHERE rate_option_id=:id AND terms_id=:t""", id=context["rate_option_id"], t=terms["terms_id"]), "rate option")
    repayment = _one(_rows(connection, """SELECT * FROM public.credit_product_repayment_options
        WHERE repayment_option_id=:id AND terms_id=:t""", id=context["repayment_option_id"], t=terms["terms_id"]), "repayment option")
    details = _rows(connection, "SELECT * FROM public.application_details WHERE application_id=:id", id=application_id)
    product_details = _rows(connection, "SELECT * FROM public.application_product_details WHERE application_id=:id", id=application_id)
    policies = _rows(connection, """SELECT * FROM public.risk_policy_parameters WHERE product_code=:p
        AND effective_from <= :d AND (effective_to IS NULL OR effective_to >= :d)""",
                     p=application["product_code"], d=as_of)
    # An empty table may use explicit externally managed assumptions. Ambiguous
    # DB policies are an error even if the caller supplies a fallback.
    risk_policy = _one(policies, "risk policy") if policies else context.get("risk_policy", {})
    rates = _rows(connection, """SELECT * FROM public.macro_indicators WHERE indicator_code='KEY_RATE'
        AND effective_date <= :d ORDER BY effective_date DESC""", d=as_of)
    if rates:
        latest = [row for row in rates if row["effective_date"] == rates[0]["effective_date"]]
        key_rate = _one(latest, "latest key rate (source ambiguity)")
        key_rate_pct, key_rate_source = key_rate["indicator_value"], key_rate["source"]
        key_rate_date = key_rate["effective_date"]
    else:
        key_rate_pct, key_rate_source = context.get("key_rate_pct"), context.get("key_rate_source")
        key_rate_date = context.get("key_rate_effective_date")
    snapshot = {
        "as_of": as_of.isoformat(), "application": application, "company": company,
        "reported_company_facts": reported_facts,
        "product": product, "terms": terms, "rate_option": rate, "repayment_option": repayment,
        "product_details": product_details[0] if product_details else {},
        "submission_confirmed": bool(details and details[0].get("confirmed_at")
                                     and details[0]["confirmed_at"].date() <= as_of),
        "risk_policy": risk_policy, "key_rate_pct": key_rate_pct, "key_rate_source": key_rate_source,
        "key_rate_effective_date": key_rate_date,
        "eligibility_rules": _rows(connection, "SELECT * FROM public.credit_product_eligibility_rules WHERE terms_id=:t", t=terms["terms_id"]),
        "purposes": _rows(connection, "SELECT * FROM public.credit_product_purposes WHERE terms_id=:t", t=terms["terms_id"]),
        "fees": _rows(connection, "SELECT * FROM public.credit_product_fees WHERE terms_id=:t", t=terms["terms_id"]),
    }
    allowed = ("model_features", "feature_provenance", "feature_contract_version", "capacity", "automatic_input_policy", "pricing_policy",
               "individual_annual_rate_pct", "individual_rate_source", "economics_source",
               "internal_confirmations", "rule_facts")
    snapshot.update({key: context[key] for key in allowed if key in context})
    if policies:
        snapshot["economics_source"] = "DB risk_policy_parameters:" + risk_policy["policy_version"]
        from .seed_policy import load_baseline
        baseline = load_baseline()
        if risk_policy["policy_version"] == baseline["policy_version"]:
            snapshot["economic_policy_metadata"] = baseline
    # Preserve actual hard negative events, irrespective of caller confirmations.
    legal = _rows(connection, """SELECT legal_event_id FROM public.legal_events WHERE company_id=:id
        AND event_type='BANKRUPTCY' AND event_status IN ('OPEN','IN_PROGRESS')
        AND (event_date IS NULL OR event_date <= :d)""", id=company["company_id"], d=as_of)
    overdue = _rows(connection, """SELECT obligation_id FROM public.credit_obligations WHERE company_id=:id
        AND obligation_status='OVERDUE' AND (contract_date IS NULL OR contract_date <= :d)""",
                    id=company["company_id"], d=as_of)
    snapshot["active_bankruptcy"] = bool(legal)
    snapshot["active_overdue"] = bool(overdue)
    if snapshot.get("feature_contract_version") in ("db_proxy_v1", "db_proxy_v2", "db_auto_v2", "db_auto_v3"):
        from .ml_scoring.feature_builder import build_db_proxy_inputs, build_automatic_db_inputs
        cid = company["company_id"]
        transactions = _rows(connection, """SELECT * FROM public.bank_transactions
            WHERE company_id=:id AND transaction_date < CAST(:d AS date) + INTERVAL '1 day'""", id=cid, d=as_of)
        statements = _rows(connection, "SELECT * FROM public.financial_statements WHERE company_id=:id AND period_end<=:d", id=cid, d=as_of)
        obligations = _rows(connection, """SELECT * FROM public.credit_obligations WHERE company_id=:id
            AND (contract_date IS NULL OR contract_date<=:d)""", id=cid, d=as_of)
        history = _rows(connection, """SELECT h.* FROM public.credit_repayment_history h
            JOIN public.credit_obligations o ON o.obligation_id=h.obligation_id
            WHERE o.company_id=:id AND h.period_date<=:d""", id=cid, d=as_of)
        builder = build_automatic_db_inputs if snapshot["feature_contract_version"] in ("db_auto_v2", "db_auto_v3") else build_db_proxy_inputs
        snapshot.update(builder(snapshot, transactions, statements, obligations, history))
    return snapshot


def store_assessment(connection, assessment, snapshot, request_key):
    """Caller holds the application row lock; all three writes are atomic."""
    from sqlalchemy import text
    result = assessment.to_dict()
    scoring_id = None
    if assessment.scoring:
        scoring = assessment.scoring
        horizon = max(scoring.pd_by_horizon)
        feature_snapshot = {"features": assessment.audit["scored_features"],
                            "pd_horizon_months": horizon, "pd_by_horizon": scoring.pd_by_horizon,
                            "monthly_hazard": scoring.monthly_hazard, "cumulative_pd": scoring.cumulative_pd,
                            "model_sha256": assessment.audit["model_sha256"],
                            "feature_sources": assessment.audit["feature_sources"],
                            "scored_amount": assessment.audit["scored_features"]["requested_amount"],
                            "risk_assessment": assessment.risk_assessment}
        scoring_id = connection.execute(text("""INSERT INTO public.scoring_results
            (application_id, model_version, pd, risk_grade, feature_snapshot, source_snapshot_date)
            VALUES (:id,:model,:pd,'UNRATED',CAST(:snapshot AS jsonb),CAST(:as_of AS timestamptz))
            RETURNING scoring_result_id"""),
            {"id": assessment.application_id, "model": scoring.model_version,
             "pd": scoring.pd_by_horizon[horizon], "snapshot": json.dumps(json_value(feature_snapshot)),
             "as_of": str(snapshot["as_of"])}).scalar_one()
    # The database has approved_term_days but no approved_term_months. Do not
    # invent a month-to-day conversion. Canonical months live in offer + audit.
    approved_days = snapshot["application"].get("requested_term_days") if assessment.decision == "APPROVE" else None
    decision_id = connection.execute(text("""INSERT INTO public.credit_decisions
        (application_id,scoring_result_id,policy_version,eligibility_status,decision,
         approved_amount,approved_term_days,reasons)
        VALUES (:id,:sid,:policy,:eligibility,:decision,:amount,:days,CAST(:reasons AS jsonb))
        RETURNING decision_id"""),
        {"id": assessment.application_id, "sid": scoring_id, "policy": assessment.policy_version,
         "eligibility": assessment.eligibility_status, "decision": assessment.decision,
         "amount": assessment.offer.amount if assessment.offer and assessment.decision == "APPROVE" else None, "days": approved_days,
         "reasons": json.dumps(assessment.reasons)}).scalar_one()
    offer_id = None
    if assessment.offer:
        offer = assessment.offer
        details = snapshot.get("product_details", {})
        offer_id = connection.execute(text("""INSERT INTO public.application_product_terms
            (application_id,terms_id,rate_option_id,repayment_option_id,offered_amount,
             offered_term_months,offered_annual_rate_pct,offered_tranche_term_value,
             offered_tranche_term_unit,offered_conditions,product_code,offer_status)
            VALUES (:id,:t,:r,:rep,:amount,:months,:rate,:tranche,:unit,CAST(:conditions AS jsonb),:p,'DRAFT')
            RETURNING offer_id"""),
            {"id": assessment.application_id, "t": snapshot["terms"]["terms_id"],
             "r": snapshot["rate_option"]["rate_option_id"],
             "rep": snapshot["repayment_option"]["repayment_option_id"],
             "amount": offer.amount, "months": offer.term_months, "rate": offer.annual_rate_pct,
             "tranche": details.get("max_tranche_term_value"), "unit": details.get("max_tranche_term_unit"),
             "conditions": json.dumps(json_value({"demo_only": assessment.audit["demo_only"],
                                                   "generated_by": "AURELIUS_SCORING",
                                                   "offer": asdict(offer),
                                                   "automatic_recommendation": assessment.automatic_recommendation,
                                                   "risk_assessment": assessment.risk_assessment})),
             "p": snapshot["application"]["product_code"]}).scalar_one()
    result["persistence"] = {"scoring_result_id": scoring_id, "decision_id": decision_id, "offer_id": offer_id}
    version = connection.execute(text("""SELECT COALESCE(MAX(snapshot_version),0)+1
        FROM public.application_snapshots WHERE application_id=:id"""), {"id": assessment.application_id}).scalar_one()
    connection.execute(text("""INSERT INTO public.application_snapshots
        (application_id,snapshot_type,snapshot_data,created_by_type,snapshot_version)
        VALUES (:id,'DECISION',CAST(:data AS jsonb),'SYSTEM',:version)"""),
        {"id": assessment.application_id, "data": json.dumps({"request_key": request_key, "assessment": result}),
         "version": version})
    # Approval is a proposal, not acceptance or issuance. Keep application under
    # review until the owning backend handles acceptance of changed conditions.
    return result


def run_application(application_id, context=None, policy=None, save=False, settings=None, predictor=None, as_of=None):
    from sqlalchemy import create_engine, text
    from .ml_scoring.predictor import Predictor
    from .pipeline import evaluate_application
    from .decision_engine.policy import Policy
    from .schemas import Assessment
    from pathlib import Path
    policy = policy or Policy.load(Path(__file__).parent / "decision_engine/policy.demo.json")
    settings = settings or Settings.from_env()
    if not settings.database_url:
        raise ConfigurationError("Set DATABASE_URL")
    predictor = predictor or Predictor(settings)
    engine = create_engine(settings.database_url, isolation_level="REPEATABLE READ")
    try:
        with engine.begin() as connection:
            # Serialize assessments and submission changes for this application.
            application = connection.execute(text("SELECT * FROM public.credit_applications WHERE application_id=:id FOR UPDATE"),
                                             {"id": application_id}).mappings().one_or_none()
            if not application:
                raise InputError(f"Application {application_id} not found")
            automatic = context is None
            if automatic and application["application_status"] not in ("SUBMITTED", "UNDER_REVIEW"):
                raise InputError("Only SUBMITTED or UNDER_REVIEW applications can be assessed")
            try:
                if automatic:
                    from .application_service import automatic_context
                    context = automatic_context(connection, application_id, policy, as_of)
                snapshot = load_snapshot(connection, application_id, context)
            except InputError as exc:
                if not automatic:
                    raise
                # Data gaps are internal bank review, not invented model values
                # and not a request for the LLM to create financial history.
                snapshot = {"as_of": (as_of or date.today()).isoformat(), "application": dict(application)}
                result = Assessment(application_id, "MANUAL_REVIEW", "NEEDS_DATA",
                                    [{"code": "DB_INPUTS_UNAVAILABLE", "message": str(exc)}], policy.version,
                                    audit={"demo_only": policy.demo_only, "as_of": snapshot["as_of"],
                                           "application_id": application_id, "input_error": str(exc)})
                key = hashlib.sha256(json.dumps(json_value({"application": dict(application),
                    "error": str(exc), "policy": asdict(policy), "as_of": snapshot["as_of"]}), sort_keys=True).encode()).hexdigest()
                if save:
                    existing = _rows(connection, """SELECT snapshot_data FROM public.application_snapshots
                        WHERE application_id=:id AND snapshot_type='DECISION' AND snapshot_data->>'request_key'=:key
                        ORDER BY snapshot_version DESC LIMIT 1""", id=application_id, key=key)
                    if existing:
                        return existing[0]["snapshot_data"]["assessment"]
                    return store_assessment(connection, result, snapshot, key)
                return result.to_dict()
            request_key = hashlib.sha256(json.dumps(json_value({"snapshot": snapshot, "policy": asdict(policy),
                                                                 "model": predictor.model_sha256,
                                                                 "pipeline_version": "bank_review_monotone_contract_v3"}), sort_keys=True).encode()).hexdigest()
            if save:
                existing = _rows(connection, """SELECT snapshot_data FROM public.application_snapshots
                    WHERE application_id=:id AND snapshot_type='DECISION'
                    AND snapshot_data->>'request_key'=:key ORDER BY snapshot_version DESC LIMIT 1""",
                                 id=application_id, key=request_key)
                if existing:
                    return existing[0]["snapshot_data"]["assessment"]
            assessment = evaluate_application(snapshot, policy, predictor)
            return store_assessment(connection, assessment, snapshot, request_key) if save else assessment.to_dict()
    finally:
        engine.dispose()
