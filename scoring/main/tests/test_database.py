"""Run only against an explicitly named disposable aurelius_test* database."""
import json
import os
import unittest
from pathlib import Path

from main.config import Settings
from main.database import run_application
from main.decision_engine.policy import Policy
from main.schemas import ConfigurationError
from main.tests.test_pipeline import FixedPredictor, example

URL = os.getenv("AURELIUS_TEST_DATABASE_URL")


@unittest.skipUnless(URL, "Set AURELIUS_TEST_DATABASE_URL for disposable PostgreSQL integration")
class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine, text
        cls.engine = create_engine(URL)
        with cls.engine.connect() as connection:
            name = connection.execute(text("SELECT current_database()")).scalar_one()
            if not name.startswith("aurelius_test"):
                raise RuntimeError("Refusing to write test fixtures outside aurelius_test* database")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        from sqlalchemy import text
        with self.engine.begin() as connection:
            company_id = connection.execute(text("""INSERT INTO public.companies
                (entity_type,name,registration_date,status,information_reliability_status)
                VALUES ('LEGAL_ENTITY','Integration fixture','2019-01-15','ACTIVE','VERIFIED')
                RETURNING company_id""")).scalar_one()
            self.application_id = connection.execute(text("""INSERT INTO public.credit_applications
                (company_id,product_code,requested_amount,requested_term_months,purpose,application_status,missing_data_status)
                VALUES (:c,'R01',3000000,36,'Пополнение оборотных средств','SUBMITTED','COMPLETE')
                RETURNING application_id"""), {"c": company_id}).scalar_one()
            connection.execute(text("""INSERT INTO public.application_details (application_id,confirmed_at)
                VALUES (:id,'2026-10-24')"""), {"id": self.application_id})
        snapshot = example()
        self.context = {key: value for key, value in snapshot.items() if key not in (
            "application", "company", "product", "terms", "rate_option", "repayment_option", "submission_confirmed")}
        self.context.update(terms_id=1, rate_option_id=1, repayment_option_id=6)
        self.policy = Policy.load(Path(__file__).resolve().parents[1] / "decision_engine/policy.demo.json")
        self.settings = Settings(database_url=URL)

    def test_atomic_persistence_and_idempotency(self):
        from sqlalchemy import text
        first = run_application(self.application_id, self.context, self.policy, save=True,
                                settings=self.settings, predictor=FixedPredictor())
        second = run_application(self.application_id, self.context, self.policy, save=True,
                                 settings=self.settings, predictor=FixedPredictor())
        self.assertEqual(first, second)
        self.assertEqual(first["decision"], "MANUAL_REVIEW")
        self.assertEqual(first["automatic_recommendation"], "POSITIVE")
        with self.engine.connect() as connection:
            for table in ("scoring_results", "credit_decisions", "application_product_terms", "application_snapshots"):
                count = connection.execute(text(f"SELECT count(*) FROM public.{table} WHERE application_id=:id"),
                                           {"id": self.application_id}).scalar_one()
                self.assertEqual(count, 1, table)
            snapshot = connection.execute(text("SELECT feature_snapshot FROM public.scoring_results WHERE application_id=:id"),
                                          {"id": self.application_id}).scalar_one()
            self.assertEqual(snapshot["pd_horizon_months"], 24)
            self.assertAlmostEqual(snapshot["risk_assessment"]["pd_limit_1y"], 0.2)
            decision = connection.execute(text("SELECT decision,approved_amount,approved_term_days FROM public.credit_decisions WHERE application_id=:id"),
                                          {"id": self.application_id}).mappings().one()
            self.assertEqual(decision["decision"], "MANUAL_REVIEW")
            self.assertIsNone(decision["approved_amount"])
            self.assertIsNone(decision["approved_term_days"])
            self.assertEqual(connection.execute(text("SELECT offer_status FROM public.application_product_terms WHERE application_id=:id"),
                                               {"id": self.application_id}).scalar_one(), "DRAFT")

    def test_dry_run_writes_nothing(self):
        from sqlalchemy import text
        result = run_application(self.application_id, self.context, self.policy,
                                 settings=self.settings, predictor=FixedPredictor())
        self.assertEqual(result["decision"], "MANUAL_REVIEW")
        self.assertEqual(result["automatic_recommendation"], "POSITIVE")
        with self.engine.connect() as connection:
            count = connection.execute(text("SELECT count(*) FROM public.credit_decisions WHERE application_id=:id"),
                                       {"id": self.application_id}).scalar_one()
            self.assertEqual(count, 0)

    def test_changed_context_creates_audit_revision(self):
        from sqlalchemy import text
        first = run_application(self.application_id, self.context, self.policy, save=True,
                                settings=self.settings, predictor=FixedPredictor())
        self.context["capacity"]["monthly_cash_available_for_debt_service"] = "200000"
        second = run_application(self.application_id, self.context, self.policy, save=True,
                                 settings=self.settings, predictor=FixedPredictor())
        self.assertNotEqual(first["persistence"]["decision_id"], second["persistence"]["decision_id"])
        with self.engine.connect() as connection:
            versions = connection.execute(text("SELECT snapshot_version FROM public.application_snapshots WHERE application_id=:id ORDER BY snapshot_version"),
                                          {"id": self.application_id}).scalars().all()
            self.assertEqual(versions, [1, 2])

    def test_db_proxy_reads_financial_tables(self):
        from sqlalchemy import text
        with self.engine.begin() as connection:
            cid = connection.execute(text("SELECT company_id FROM public.credit_applications WHERE application_id=:id"),
                                     {"id": self.application_id}).scalar_one()
            for index in range(2025 * 12 + 8, 2026 * 12 + 9):
                year, month = divmod(index, 12)
                connection.execute(text("""INSERT INTO public.bank_transactions
                    (company_id,transaction_date,amount,direction,operation_category)
                    VALUES (:id,:d,1000000,'IN','REVENUE')"""),
                    {"id": cid, "d": f"{year}-{month + 1:02d}-15"})
            connection.execute(text("""INSERT INTO public.financial_statements
                (company_id,period_start,period_end,statement_type,revenue,operating_profit,cash_and_equivalents,is_verified)
                VALUES (:id,'2025-10-01','2026-09-30','MANAGEMENT',12000000,3000000,2000000,true)"""), {"id": cid})
            connection.execute(text("""INSERT INTO public.credit_obligations
                (company_id,obligation_type,outstanding_balance,monthly_payment,obligation_status)
                VALUES (:id,'LOAN',300000,100000,'ACTIVE')"""), {"id": cid})
        self.context["feature_contract_version"] = "db_proxy_v1"
        self.context["internal_confirmations"]["financial_history_complete"] = True
        self.context["model_features"] = {"industry": "services", "macro_stress": 0}
        self.context.pop("capacity")
        result = run_application(self.application_id, self.context, self.policy,
                                 settings=self.settings, predictor=FixedPredictor())
        self.assertEqual(result["decision"], "MANUAL_REVIEW")
        self.assertEqual(result["automatic_recommendation"], "POSITIVE")
        self.assertEqual(result["audit"]["scored_features"]["dscr"], 2.5)
        self.assertIn("PROXY", result["audit"]["feature_sources"]["debt_to_revenue"])

    def test_failed_offer_write_rolls_back_scoring_and_decision(self):
        from sqlalchemy import text
        from unittest.mock import patch
        from main import database
        original = database.store_assessment

        def failing_store(connection, assessment, snapshot, request_key):
            # Trigger a real FK failure after scoring and decision inserts.
            snapshot["rate_option"]["rate_option_id"] = -999
            return original(connection, assessment, snapshot, request_key)

        with patch("main.database.store_assessment", side_effect=failing_store):
            with self.assertRaises(Exception):
                run_application(self.application_id, self.context, self.policy, save=True,
                                settings=self.settings, predictor=FixedPredictor())
        with self.engine.connect() as connection:
            for table in ("scoring_results", "credit_decisions", "application_snapshots"):
                count = connection.execute(text(f"SELECT count(*) FROM public.{table} WHERE application_id=:id"),
                                           {"id": self.application_id}).scalar_one()
                self.assertEqual(count, 0)

    def test_policy_ambiguity_is_not_silently_resolved(self):
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("""INSERT INTO public.risk_policy_parameters
                (product_code,policy_version,funding_spread_pct,operating_cost_pct,required_margin_pct,lgd_pct,effective_from)
                VALUES ('R01','TEST_A',1,1,2,45,'2026-01-01'),('R01','TEST_B',1,1,2,45,'2026-01-01')"""))
        try:
            with self.assertRaises(ConfigurationError):
                run_application(self.application_id, self.context, self.policy,
                                settings=self.settings, predictor=FixedPredictor())
        finally:
            with self.engine.begin() as connection:
                connection.execute(text("DELETE FROM public.risk_policy_parameters WHERE policy_version IN ('TEST_A','TEST_B')"))

    def test_baseline_seed_idempotency_and_db_source(self):
        from main.database import load_snapshot
        from main.seed_policy import load_baseline, seed_baseline
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                first = seed_baseline(connection, load_baseline())
                second = seed_baseline(connection, load_baseline())
                self.assertEqual(first["policies_inserted"], 3)
                self.assertEqual(first["macro_inserted"], 1)
                self.assertEqual(second["policies_inserted"], 0)
                self.assertEqual(second["policies_unchanged"], 3)
                context = dict(self.context)
                context.pop("economics_source")
                context.pop("risk_policy")
                context.pop("key_rate_pct")
                snapshot = load_snapshot(connection, self.application_id, context)
                self.assertEqual(float(snapshot["key_rate_pct"]), 14)
                self.assertIn("AURELIUS_MVP_", snapshot["economics_source"])
                self.assertTrue(snapshot["economic_policy_metadata"]["demo_only"])
            finally:
                transaction.rollback()

    def test_baseline_never_overwrites_conflicting_policy(self):
        from main.seed_policy import load_baseline, seed_baseline
        from sqlalchemy import text
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                document = load_baseline()
                seed_baseline(connection, document)
                document["funding_spread_pct"] = "9.99"
                with self.assertRaises(ConfigurationError):
                    seed_baseline(connection, document)
                spread = connection.execute(text("SELECT funding_spread_pct FROM public.risk_policy_parameters WHERE product_code='R01'")).scalar_one()
                self.assertEqual(float(spread), 1.5)
                document["policy_version"] = "OTHER_OVERLAPPING_VERSION"
                with self.assertRaises(ConfigurationError):
                    seed_baseline(connection, document)
            finally:
                transaction.rollback()

    def test_application_id_only_reports_missing_inputs_and_is_idempotent(self):
        first = run_application(self.application_id, save=True, settings=self.settings,
                                predictor=FixedPredictor(), as_of=__import__('datetime').date(2026, 10, 24))
        second = run_application(self.application_id, save=True, settings=self.settings,
                                 predictor=FixedPredictor(), as_of=__import__('datetime').date(2026, 10, 24))
        self.assertEqual(first, second)
        self.assertEqual(first["decision"], "MANUAL_REVIEW")
        self.assertEqual(first["automatic_recommendation"], "REVIEW_REQUIRED")
        self.assertIsNone(first["scoring"])
        self.assertEqual(first["reasons"][0]["code"], "DB_INPUTS_UNAVAILABLE")

    def test_application_id_only_builds_features_without_external_context(self):
        from datetime import date
        from sqlalchemy import text
        from main.seed_policy import load_baseline, seed_baseline
        # Reuse a verified 13-month fixture, then supply the remaining DB facts.
        self.test_db_proxy_reads_financial_tables()
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE public.companies SET okved_main='46.90' WHERE company_id=(SELECT company_id FROM public.credit_applications WHERE application_id=:id)"), {"id": self.application_id})
            oid = connection.execute(text("SELECT obligation_id FROM public.credit_obligations WHERE company_id=(SELECT company_id FROM public.credit_applications WHERE application_id=:id)"), {"id": self.application_id}).scalar_one()
            connection.execute(text("""INSERT INTO public.credit_repayment_history
                (obligation_id,period_date,overdue_days) VALUES (:id,'2026-09-01',0)"""), {"id": oid})
            seed_baseline(connection, load_baseline())
        try:
            first = run_application(self.application_id, save=True, settings=self.settings,
                                    predictor=FixedPredictor(), as_of=date(2026, 10, 24))
            second = run_application(self.application_id, save=True, settings=self.settings,
                                     predictor=FixedPredictor(), as_of=date(2026, 10, 24))
            self.assertEqual(first, second)
            self.assertEqual(first["decision"], "MANUAL_REVIEW")
            self.assertEqual(first["automatic_recommendation"], "REVIEW_REQUIRED")
            self.assertIsNotNone(first["offer"])
            self.assertEqual(first["audit"]["scored_features"]["industry"], "retail")
            self.assertEqual(first["audit"]["scored_features"]["macro_stress"], 0)
            self.assertEqual(first["audit"]["snapshot"]["feature_contract_version"], "db_auto_v3")
            self.assertTrue(first["risk_assessment"]["passes_pd_limit"])
            # Exercise the changed extractor against the actual bundled model,
            # not only the deterministic fixture predictor.
            live = run_application(self.application_id, settings=self.settings, as_of=date(2026, 10, 24))
            self.assertIsNotNone(live["scoring"])
            self.assertIn(live["decision"], ("MANUAL_REVIEW", "REJECT"))
            self.assertGreaterEqual(live["risk_assessment"]["pd_application_1y"], 0)
            self.assertLessEqual(live["risk_assessment"]["pd_application_1y"], 1)
        finally:
            with self.engine.begin() as connection:
                connection.execute(text("DELETE FROM public.risk_policy_parameters WHERE policy_version='AURELIUS_MVP_20261024_V1'"))
                connection.execute(text("DELETE FROM public.macro_indicators WHERE source='CBR official decision 2026-07-24'"))


if __name__ == "__main__":
    unittest.main()
