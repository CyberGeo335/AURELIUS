"""Read-only evaluation of the 30 demo businesses. Never creates applications."""
import argparse
import csv
import json
from decimal import Decimal
from collections import Counter
from datetime import date
from pathlib import Path

from .config import ROOT, Settings
from .database import run_application
from .decision_engine.policy import Policy
from .ml_scoring.predictor import Predictor
from .schemas import ConfigurationError, InputError


def load_companies(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    companies = [{"scenario": row.get("scenario", ""), "company_id": int(row["company_id"])} for row in rows]
    if not companies or len({row["company_id"] for row in companies}) != len(companies):
        raise InputError("Company list must be nonempty and contain unique company_id values")
    return companies


def summary_row(company, application_id=None, result=None, status=None, message=None):
    result = result or {}
    risk = result.get("risk_assessment") or {}
    offer = result.get("offer") or {}
    return dict(company, application_id=application_id, status=status or "EVALUATED",
                decision=result.get("decision"), recommendation=result.get("automatic_recommendation"),
                offered_amount=offer.get("amount"), annual_rate_pct=offer.get("annual_rate_pct"),
                pd_12m=risk.get("pd_application_1y"), pd_term=risk.get("pd_application_term"),
                pd_limit_12m=risk.get("pd_limit_1y"),
                reasons=message or "; ".join(r["code"] + ": " + r["message"] for r in result.get("reasons", [])))


def evaluate_companies(companies, settings=None, policy=None, as_of=None,
                       diagnostic=False, amount=Decimal("3000000"), term=36, product="R01"):
    from sqlalchemy import create_engine, text
    settings = settings or Settings.from_env()
    if not settings.database_url:
        raise ConfigurationError("Set DATABASE_URL")
    policy = policy or Policy.load(Path(__file__).parent / "decision_engine/policy.demo.json")
    engine = create_engine(settings.database_url, isolation_level="REPEATABLE READ")
    report, predictor = [], None
    try:
        for company in companies:
            if diagnostic:
                try:
                    from .diagnostics import diagnose_company
                    predictor = predictor or Predictor(settings)
                    with engine.connect() as connection:
                        result = diagnose_company(connection, company, predictor, policy,
                                                  as_of or date.today(), product, amount, term)
                    row = summary_row(company, result=result, status="DIAGNOSTIC_SCORED")
                    requested = result["diagnostic_requested_risk"]
                    row.update(financial_outcome="POSSIBLE_OFFER" if result["offer"] else "REJECT",
                               requested_pd_12m=requested["pd_application_1y"],
                               requested_pd_term=requested["pd_application_term"],
                               requested_base_rate_pct=str(result["audit"]["snapshot"]["individual_annual_rate_pct"]),
                               requested_base_pd_limit_12m=requested["pd_limit_1y"],
                               requested_amount=str(amount), term_months=term, product_code=product,
                               diagnostic_assumptions="; ".join(result["audit"]["diagnostic_assumptions"]),
                               generator_range_warnings=",".join(result["generator_range_warnings"]),
                               raw_dscr=result["financial_observations"].get("raw_dscr"),
                               observed_debt_to_monthly_revenue=result["financial_observations"].get("outstanding_debt_to_monthly_revenue"),
                               feature_adjustments=json.dumps(result["feature_adjustments"]),
                               **{key: result["diagnostic_features"][key] for key in
                                  ("monthly_revenue", "dscr", "debt_to_revenue", "operating_margin", "cash_buffer_months", "revenue_trend_12m")})
                    report.append(row)
                except (InputError, ConfigurationError) as exc:
                    row = summary_row(company, status="DIAGNOSTIC_UNSCORABLE", message=str(exc))
                    row.update(financial_outcome="UNSCORABLE", requested_pd_12m=None, requested_pd_term=None,
                               requested_base_rate_pct=None, requested_base_pd_limit_12m=None,
                               requested_amount=str(amount), term_months=term, product_code=product,
                               diagnostic_assumptions="No missing model inputs were invented", generator_range_warnings="",
                               raw_dscr=None, observed_debt_to_monthly_revenue=None, feature_adjustments="{}",
                               **{key: None for key in ("monthly_revenue", "dscr", "debt_to_revenue", "operating_margin", "cash_buffer_months", "revenue_trend_12m")})
                    report.append(row)
                continue
            with engine.connect() as connection:
                exists = connection.execute(text("SELECT 1 FROM public.companies WHERE company_id=:id"),
                                            {"id": company["company_id"]}).first()
                if not exists:
                    report.append(summary_row(company, status="COMPANY_NOT_FOUND", message="Company is absent from this database"))
                    continue
                application = connection.execute(text("""SELECT application_id FROM public.credit_applications
                    WHERE company_id=:id AND application_status IN ('SUBMITTED','UNDER_REVIEW')
                    ORDER BY application_date DESC,application_id DESC LIMIT 1"""), {"id": company["company_id"]}).scalar_one_or_none()
            if application is None:
                report.append(summary_row(company, status="NO_ACTIVE_APPLICATION",
                    message="No SUBMITTED/UNDER_REVIEW application. Start a new application in the cabinet; cancelled applications are not reused."))
                continue
            try:
                predictor = predictor or Predictor(settings)
                result = run_application(application, settings=settings, policy=policy,
                                         predictor=predictor, save=False, as_of=as_of)
                report.append(summary_row(company, application, result))
            except (InputError, ConfigurationError) as exc:
                report.append(summary_row(company, application, status="INPUT_OR_CONFIG_ERROR", message=str(exc)))
        return report
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies-file", type=Path, default=ROOT / "bd/seeds/aurelius_30_ids.csv")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="YYYY-MM-DD; default assessment date is today")
    parser.add_argument("--output", type=Path, default=ROOT / "main/reports")
    parser.add_argument("--diagnostic", action="store_true", help="What-if comparison of businesses, regardless of cancelled applications; no DB writes")
    parser.add_argument("--amount", type=Decimal, default=Decimal("3000000"))
    parser.add_argument("--term", type=int, default=36)
    parser.add_argument("--product", choices=("R01", "R02", "R03"), default="R01")
    args = parser.parse_args()
    report = evaluate_companies(load_companies(args.companies_file), as_of=args.as_of,
                               diagnostic=args.diagnostic, amount=args.amount, term=args.term, product=args.product)
    args.output.mkdir(parents=True, exist_ok=True)
    basename = "diagnostic" if args.diagnostic else "businesses"
    json_path, csv_path = args.output / (basename + ".json"), args.output / (basename + ".csv")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(report[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(report)
    print(json.dumps({"businesses": len(report), "statuses": dict(Counter(row["status"] for row in report)),
                      "financial_outcomes": dict(Counter(row.get("financial_outcome", "NOT_DIAGNOSTIC") for row in report)),
                      "csv": str(csv_path), "json": str(json_path), "database_changed": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
