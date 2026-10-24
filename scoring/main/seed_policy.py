"""Versioned MVP policy seed. Default: dry run, --apply: commit atomically.

No overwriting existing values, closing existing policies, or reloading users.
"""
import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .config import Settings
from .schemas import ConfigurationError

BASELINE_PATH = Path(__file__).parent / "decision_engine/baseline_20261024.json"


def load_baseline(path=BASELINE_PATH):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("demo_only") is not True:
        raise ConfigurationError("This seed installs explicitly marked MVP assumptions only")
    if set(document["products"]) != {"R01", "R02", "R03"}:
        raise ConfigurationError("Expected exactly R01/R02/R03")
    return document


def seed_baseline(connection, document):
    """Transaction is owned by caller; any conflict aborts the entire seed."""
    from sqlalchemy import text
    connection.execute(text("LOCK TABLE public.risk_policy_parameters, public.macro_indicators IN SHARE ROW EXCLUSIVE MODE"))
    start, end = (date.fromisoformat(document[key]) for key in ("effective_from", "effective_to"))
    version = document["policy_version"]
    values = {key: Decimal(document[key]) for key in ("funding_spread_pct", "operating_cost_pct", "required_margin_pct", "lgd_pct")}
    if not (start <= end and values["lgd_pct"] > 0):
        raise ConfigurationError("Invalid baseline interval or LGD")
    summary = {"policy_version": version, "policies_inserted": 0, "macro_inserted": 0, "policies_unchanged": 0}
    for product in document["products"]:
        if connection.execute(text("SELECT 1 FROM public.credit_products WHERE product_code=:p"), {"p": product}).first() is None:
            raise ConfigurationError(f"Product {product} does not exist")
        existing = connection.execute(text("SELECT * FROM public.risk_policy_parameters WHERE product_code=:p AND policy_version=:v"),
                                      {"p": product, "v": version}).mappings().one_or_none()
        if existing:
            if any(existing[key] != value for key, value in values.items()) or existing["effective_from"] != start or existing["effective_to"] != end:
                raise ConfigurationError(f"Existing {product}/{version} differs; create a new policy version")
            summary["policies_unchanged"] += 1
        else:
            overlap = connection.execute(text("""SELECT policy_version FROM public.risk_policy_parameters
                WHERE product_code=:p AND effective_from<=:end
                AND (effective_to IS NULL OR effective_to>=:start)"""), {"p": product, "start": start, "end": end}).first()
            if overlap:
                raise ConfigurationError(f"Policy overlap for {product}: {overlap[0]}; refusing to change existing data")
            connection.execute(text("""INSERT INTO public.risk_policy_parameters
                (product_code,policy_version,funding_spread_pct,operating_cost_pct,required_margin_pct,lgd_pct,effective_from,effective_to)
                VALUES (:p,:v,:funding_spread_pct,:operating_cost_pct,:required_margin_pct,:lgd_pct,:start,:end)"""),
                dict(values, p=product, v=version, start=start, end=end))
            summary["policies_inserted"] += 1
    indicator = document["key_rate"]
    observation = date.fromisoformat(indicator["effective_date"])
    amount = Decimal(indicator["indicator_value"])
    rows = connection.execute(text("SELECT * FROM public.macro_indicators WHERE indicator_code='KEY_RATE' AND effective_date=:d"),
                              {"d": observation}).mappings().all()
    if rows:
        if len(rows) != 1 or rows[0]["indicator_value"] != amount:
            raise ConfigurationError("Conflicting key rate observation; existing data were not overwritten")
    else:
        connection.execute(text("""INSERT INTO public.macro_indicators (indicator_code,indicator_value,effective_date,source)
            VALUES ('KEY_RATE',:value,:d,:source)"""), {"value": amount, "d": observation, "source": indicator["source"]})
        summary["macro_inserted"] = 1
    return summary


def install_baseline(settings=None, apply=False, path=BASELINE_PATH):
    from sqlalchemy import create_engine
    settings = settings or Settings.from_env()
    if not settings.database_url:
        raise ConfigurationError("Set DATABASE_URL")
    document = load_baseline(path)
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            with connection.begin() as transaction:
                result = seed_baseline(connection, document)
                if not apply:
                    transaction.rollback()
                result["committed"] = apply
                return result
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install_baseline(apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
