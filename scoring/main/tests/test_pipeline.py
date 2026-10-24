import copy
import json
import unittest
from decimal import Decimal
from pathlib import Path

from main.credit_offer.calculator import build_offer, candidate_amounts, evaluate_economics
from main.decision_engine.policy import Policy, annual_pd_limit, validate_economic_inputs
from main.ml_scoring.feature_builder import build_features, build_db_proxy_inputs
from main.pipeline import evaluate_application
from main.schemas import ConfigurationError, InputError, ScoringResult

MAIN = Path(__file__).resolve().parents[1]


def example():
    return json.loads((MAIN / "examples/application.json").read_text(encoding="utf-8"))


def demo_policy():
    return Policy.load(MAIN / "decision_engine/policy.demo.json")


class FixedPredictor:
    model_sha256 = "test-deterministic-model"

    def __init__(self, hazard=0.001):
        self.hazard = hazard
        self.amounts = []

    def predict(self, features, term):
        self.amounts.append(features["requested_amount"])
        # Explicit dependence on amount is exercised by tests below.
        hazard = self.hazard(features) if callable(self.hazard) else self.hazard
        curve = [1 - (1 - hazard) ** month for month in range(1, term + 1)]
        return ScoringResult("fixture", [hazard] * term, curve,
                             {h: curve[h - 1] for h in (6, 12, 24) if h < term}, term)


class PipelineTests(unittest.TestCase):
    def test_okved_mapping_never_defaults_unknown_industry(self):
        from main.application_service import industry_from_okved, DEFAULTS_PATH
        mapping = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))["industry_by_okved_division"]
        self.assertEqual(industry_from_okved("46.90", mapping), "retail")
        self.assertEqual(industry_from_okved("41.20", mapping), "construction")
        self.assertEqual(industry_from_okved("62.01", mapping), "services")
        with self.assertRaises(InputError):
            industry_from_okved("64.19", mapping)
    def test_approval_and_input_immutability(self):
        snapshot = example()
        original = copy.deepcopy(snapshot)
        result = evaluate_application(snapshot, demo_policy(), FixedPredictor())
        self.assertEqual(result.decision, "MANUAL_REVIEW")
        self.assertEqual(result.automatic_recommendation, "POSITIVE")
        self.assertEqual(result.offer.amount, Decimal("3000000.00"))
        self.assertEqual(snapshot, original)
        json.dumps(result.to_dict(), allow_nan=False)

    def test_reduced_offer_rescored_at_actual_amount(self):
        snapshot = example()
        snapshot["capacity"]["monthly_cash_available_for_debt_service"] = "200000"
        predictor = FixedPredictor()
        result = evaluate_application(snapshot, demo_policy(), predictor)
        self.assertEqual(result.decision, "MANUAL_REVIEW")
        self.assertEqual(result.automatic_recommendation, "POSITIVE")
        self.assertLess(result.offer.amount, Decimal("3000000"))
        self.assertEqual(float(result.offer.amount), predictor.amounts[-1])
        self.assertLessEqual(result.offer.affordability_payment, Decimal("200000") / Decimal("1.2") - 100000)

    def test_no_capacity_rejects_without_model(self):
        snapshot = example()
        snapshot["capacity"]["monthly_cash_available_for_debt_service"] = "100000"
        predictor = FixedPredictor()
        result = evaluate_application(snapshot, demo_policy(), predictor)
        self.assertEqual(result.decision, "REJECT")
        self.assertIsNone(result.offer)
        self.assertEqual(predictor.amounts, [])

    def test_profitability_and_lgd(self):
        policy = demo_policy()
        object.__setattr__(policy, "decision_method", "monthly_cashflow")
        result = evaluate_application(example(), policy, FixedPredictor(0.20))
        self.assertEqual(result.decision, "REJECT")
        self.assertIn("NEGATIVE_EXPECTED_RETURN", [r["code"] for r in result.reasons])
        snapshot = example()
        snapshot["risk_policy"]["lgd_pct"] = "0"
        offer = build_offer(snapshot, Decimal("300000"), Decimal("28"))
        scoring = FixedPredictor().predict({"requested_amount": 300000}, 36)
        economics = evaluate_economics(offer, scoring, validate_economic_inputs(snapshot), demo_policy())
        self.assertEqual(economics["discounted_expected_credit_loss"], 0)

    def test_annual_limit_units_and_bank_confirmation(self):
        snapshot = example()
        inputs = validate_economic_inputs(snapshot)
        limit = annual_pd_limit(28, inputs)
        # (28 - (15+1) - 1 - 2) percentage points / 45% LGD = 20% PD.
        self.assertAlmostEqual(limit["pd_limit_1y"], 0.20)
        result = evaluate_application(snapshot, demo_policy(), FixedPredictor())
        self.assertEqual(result.decision, "MANUAL_REVIEW")
        self.assertEqual(result.automatic_recommendation, "POSITIVE")
        self.assertAlmostEqual(result.risk_assessment["pd_application_1y"], 1 - 0.999 ** 12)
        self.assertEqual(result.risk_assessment["comparison_horizon_months"], 12)
        self.assertTrue(result.risk_assessment["passes_pd_limit"])
        self.assertIsNotNone(result.offer)

    def test_annual_limit_failure_and_invalid_lgd(self):
        result = evaluate_application(example(), demo_policy(), FixedPredictor(0.03))
        self.assertEqual(result.decision, "REJECT")
        self.assertFalse(result.risk_assessment["passes_pd_limit"])
        snapshot = example()
        snapshot["risk_policy"]["lgd_pct"] = 0
        with self.assertRaises(ConfigurationError):
            evaluate_application(snapshot, demo_policy(), FixedPredictor())
        inputs = validate_economic_inputs(example())
        limit = annual_pd_limit(10, inputs)
        self.assertEqual(limit["pd_limit_1y"], 0)
        self.assertFalse(limit["positive_headroom"])
        self.assertLess(limit["pd_limit_1y_raw"], 0)

    def test_draft_pricing_finds_lowest_feasible_rate_and_preserves_quote(self):
        snapshot = example()
        snapshot["pricing_policy"] = {"demo_only": True, "maximum_rate_pct": "30", "step_pct": ".5", "source": "TEST pricing ceiling"}
        result = evaluate_application(snapshot, demo_policy(), FixedPredictor(.02))
        self.assertEqual(result.decision, "MANUAL_REVIEW")
        self.assertEqual(result.offer.amount, Decimal("3000000"))
        self.assertEqual(result.offer.annual_rate_pct, Decimal("29"))
        self.assertEqual(result.audit["scored_features"]["annual_rate"], .29)
        self.assertAlmostEqual(result.risk_assessment["pd_limit_1y"], 10/45)
        fixed = example()
        quoted = evaluate_application(fixed, demo_policy(), FixedPredictor(.02))
        self.assertEqual(quoted.decision, "REJECT")

    def test_draft_pricing_never_exceeds_ceiling(self):
        snapshot = example()
        snapshot["pricing_policy"] = {"demo_only": True, "maximum_rate_pct": "30", "step_pct": ".5", "source": "TEST pricing ceiling"}
        result = evaluate_application(snapshot, demo_policy(), FixedPredictor(.03))
        self.assertEqual(result.decision, "REJECT")
        self.assertIsNone(result.offer)
        self.assertTrue(all(Decimal(row["annual_rate_pct"]) <= 30 for row in result.audit["evaluations"]))

    def test_nonmonotone_risk_uses_descending_grid(self):
        policy = demo_policy()
        object.__setattr__(policy, "pd_limits", {12: 0.10})
        predictor = FixedPredictor(lambda f: 0.02 if f["requested_amount"] > 2850000 else 0.001)
        result = evaluate_application(example(), policy, predictor)
        self.assertEqual(result.offer.amount, Decimal("2850000.00"))
        self.assertEqual(len(predictor.amounts), 4)

    def test_product_and_identity_isolation(self):
        for mutate in (
            lambda x: x["company"].update(company_id=2),
            lambda x: x["rate_option"].update(terms_id=2),
            lambda x: x["repayment_option"].update(terms_id=2),
        ):
            snapshot = example()
            mutate(snapshot)
            with self.assertRaises(InputError):
                evaluate_application(snapshot, demo_policy(), FixedPredictor())

    def test_upstream_incomplete_is_error_not_client_question(self):
        snapshot = example()
        snapshot["application"]["missing_data_status"] = "PARTIAL"
        with self.assertRaises(InputError):
            evaluate_application(snapshot, demo_policy(), FixedPredictor())

    def test_missing_policy_is_configuration_error(self):
        snapshot = example()
        snapshot["risk_policy"] = {}
        with self.assertRaises(ConfigurationError):
            evaluate_application(snapshot, demo_policy(), FixedPredictor())

    def test_unknown_features_are_never_filled(self):
        snapshot = example()
        del snapshot["model_features"]["macro_stress"]
        with self.assertRaises(InputError):
            build_features(snapshot, 28)
        snapshot = example()
        snapshot["model_features"]["macro_stress"] = float("nan")
        with self.assertRaises(InputError):
            build_features(snapshot, 28)

    def test_feature_units_and_category_mapping(self):
        features, _ = build_features(example(), 28, 123456)
        self.assertEqual(features["entity_type"], "OOO")
        self.assertEqual(features["annual_rate"], 0.28)
        self.assertEqual(features["requested_amount"], 123456)
        self.assertEqual(features["age_months"], 93)

    def test_hard_negative_and_unknown_conditions(self):
        snapshot = example()
        snapshot["active_bankruptcy"] = True
        self.assertEqual(evaluate_application(snapshot, demo_policy(), FixedPredictor()).decision, "REJECT")
        snapshot = example()
        del snapshot["internal_confirmations"]["guarantor_requirement_resolved"]
        self.assertEqual(evaluate_application(snapshot, demo_policy(), FixedPredictor()).decision, "MANUAL_REVIEW")

    def test_schedule_principal_conservation(self):
        for kind in ("ANNUITY", "EQUAL_PRINCIPAL"):
            for rate in (Decimal(0), Decimal(28)):
                snapshot = example()
                snapshot["repayment_option"]["repayment_type"] = kind
                offer = build_offer(snapshot, Decimal("300000.01"), rate)
                self.assertEqual(sum(row["principal"] for row in offer.monthly_schedule), offer.amount)
                self.assertEqual(offer.monthly_schedule[-1]["closing_balance"], 0)
                self.assertTrue(all(row["closing_balance"] >= 0 for row in offer.monthly_schedule))

    def test_revolving_capacity_uses_tranche_not_contract(self):
        snapshot = example()
        snapshot["application"].update(product_code="R02", requested_term_months=18)
        snapshot["product"]["product_code"] = "R02"
        snapshot["terms"].update(product_code="R02", min_contract_term_value=None,
                                  max_contract_term_value=18, max_tranche_term_value=6, tranche_term_unit="MONTHS")
        snapshot["product_details"] = {"max_tranche_term_value": 6, "max_tranche_term_unit": "MONTHS"}
        snapshot["repayment_option"]["repayment_type"] = "BULLET"
        offer = build_offer(snapshot, Decimal("600000"), Decimal(24))
        self.assertEqual(offer.affordability_payment, Decimal("112000.00"))
        self.assertEqual(offer.monthly_schedule[-1]["principal"], Decimal("600000.00"))
        self.assertEqual(offer.monthly_schedule[6]["opening_balance"], Decimal("600000.00"))

    def test_overdraft_conservative_reserve(self):
        snapshot = example()
        snapshot["application"].update(product_code="R03", requested_term_months=12)
        snapshot["repayment_option"]["repayment_type"] = "OTHER"
        snapshot["rate_option"]["max_tranche_term_days"] = 60
        snapshot["product_details"] = {"max_tranche_term_value": 60, "max_tranche_term_unit": "DAYS"}
        offer = build_offer(snapshot, Decimal("50000"), Decimal(24))
        self.assertEqual(offer.affordability_payment, Decimal("51000.00"))

    def test_grid_and_budget(self):
        self.assertEqual(candidate_amounts(Decimal(301), Decimal(300), Decimal(123), Decimal(100), 10),
                         [Decimal(300), Decimal(200), Decimal(123)])
        with self.assertRaises(ConfigurationError):
            candidate_amounts(Decimal(1000000), Decimal(1000000), Decimal(1), Decimal(1), 10)

    def test_future_key_rate_and_policy_dates(self):
        snapshot = example()
        snapshot["key_rate_effective_date"] = "2027-01-01"
        with self.assertRaises(ConfigurationError):
            evaluate_application(snapshot, demo_policy(), FixedPredictor())
        snapshot = example()
        snapshot["risk_policy"]["effective_from"] = "2027-01-01"
        with self.assertRaises(ConfigurationError):
            evaluate_application(snapshot, demo_policy(), FixedPredictor())

    def test_db_proxy_complete_months_and_provenance(self):
        snapshot = example()
        snapshot["feature_contract_version"] = "db_proxy_v1"
        snapshot["internal_confirmations"]["financial_history_complete"] = True
        transactions = []
        # Sep 2025 .. Sep 2026; Oct 2026 remains outside the complete window.
        for index in range(2025 * 12 + 8, 2026 * 12 + 9):
            year, month = divmod(index, 12)
            transactions.append({"transaction_date": f"{year}-{month + 1:02d}-15",
                                 "direction": "IN", "operation_category": "REVENUE", "currency": "RUB", "amount": 1000000})
        statements = [{"period_end": "2026-09-30", "is_verified": True,
                       "operating_profit": 3000000, "revenue": 12000000, "cash_and_equivalents": 2000000}]
        obligations = [{"obligation_status": "ACTIVE", "monthly_payment": 100000, "outstanding_balance": 500000}]
        updates = build_db_proxy_inputs(snapshot, transactions, statements, obligations, [])
        self.assertEqual(updates["model_features"]["monthly_revenue"], 1000000)
        self.assertEqual(updates["model_features"]["dscr"], 2.5)
        self.assertEqual(updates["model_features"]["debt_to_revenue"], 0.5)
        self.assertIn("PROXY", updates["feature_provenance"]["debt_to_revenue"])
        with self.assertRaises(InputError):
            build_db_proxy_inputs(snapshot, transactions[1:], statements, obligations, [])
        diagnostic = dict(snapshot, feature_contract_version="db_diagnostic_v1")
        approximate = build_db_proxy_inputs(diagnostic, transactions[2:], statements, obligations, [])
        self.assertEqual(approximate["model_features"]["revenue_trend_12m"], 0)
        self.assertIn("APPROXIMATION", approximate["feature_provenance"]["revenue_trend_12m"])
        # The same short history remains forbidden by the normal DB contract.
        with self.assertRaises(InputError):
            build_db_proxy_inputs(snapshot, transactions[2:], statements, obligations, [])

        corrected = dict(snapshot, feature_contract_version="db_proxy_v2")
        fixed = build_db_proxy_inputs(corrected, transactions, statements, obligations, [])
        self.assertAlmostEqual(fixed["model_features"]["debt_to_revenue"], .625)
        self.assertEqual(fixed["financial_observations"]["outstanding_debt_to_monthly_revenue"], .5)
        self.assertIn("0.16", fixed["feature_provenance"]["debt_to_revenue"])
        tiny_service = [dict(obligations[0], monthly_payment=1000)]
        high_dscr = build_db_proxy_inputs(corrected, transactions, statements, tiny_service, [])
        self.assertEqual(high_dscr["model_features"]["dscr"], 8)
        self.assertEqual(high_dscr["financial_observations"]["raw_dscr"], 250)
        self.assertEqual(high_dscr["feature_adjustments"]["dscr"]["raw"], 250)


if __name__ == "__main__":
    unittest.main()
