import unittest

from main.batch import summary_row


class BatchReportTests(unittest.TestCase):
    def test_probability_and_offer_fields_are_preserved(self):
        result = {"decision": "MANUAL_REVIEW", "automatic_recommendation": "POSITIVE",
                  "risk_assessment": {"pd_application_1y": .04, "pd_application_term": .11, "pd_limit_1y": .08},
                  "offer": {"amount": "750000.00", "annual_rate_pct": "25.5"}, "reasons": []}
        row = summary_row({"scenario": "AUR-11", "company_id": 45}, 123, result)
        self.assertEqual(row["pd_12m"], .04)
        self.assertEqual(row["pd_limit_12m"], .08)
        self.assertEqual(row["offered_amount"], "750000.00")

    def test_unavailable_application_does_not_claim_model_prediction(self):
        row = summary_row({"scenario": "AUR-01", "company_id": 35}, status="NO_ACTIVE_APPLICATION")
        self.assertIsNone(row["pd_12m"])
        self.assertIsNone(row["decision"])
