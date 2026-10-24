"""Business-semantic regressions for the actual bundled classifier."""
import unittest

from main.ml_scoring.predictor import Predictor


class PredictorSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor = Predictor()
        cls.base = {"age_months": 30, "industry": "retail", "entity_type": "OOO",
                    "monthly_revenue": 1200000, "revenue_trend_12m": 0,
                    "revenue_volatility": 0, "operating_margin": .27,
                    "cash_buffer_months": 1, "dscr": 3.6,
                    "debt_to_revenue": .46875, "prior_overdue_30d": 0,
                    "requested_amount": 3000000, "annual_rate": .255, "macro_stress": 0}

    def assert_monotone(self, key, values, direction):
        curves = [self.predictor.predict(dict(self.base, **{key: value}), 36).cumulative_pd for value in values]
        for left, right in zip(curves, curves[1:]):
            for low, high in zip(left, right):
                self.assertGreaterEqual(direction * (high - low), -1e-10, (key, values))

    def test_increasing_dscr_never_increases_pd(self):
        self.assert_monotone("dscr", [.05, .9, 1.5, 3.6, 8, 18], -1)

    def test_increasing_debt_never_reduces_pd(self):
        self.assert_monotone("debt_to_revenue", [.03, .1, .3, 1, 3, 15], 1)

    def test_increasing_cash_buffer_never_increases_pd(self):
        self.assert_monotone("cash_buffer_months", [0, .5, 1, 3, 8, 18], -1)

    def test_increasing_requested_amount_never_reduces_pd(self):
        self.assert_monotone("requested_amount", [50000, 300000, 1000000, 3000000, 30000000], 1)

    def test_better_operating_margin_never_increases_pd(self):
        self.assert_monotone("operating_margin", [-.28, 0, .1, .27, .48], -1)

    def test_higher_rate_never_artificially_reduces_pd(self):
        self.assert_monotone("annual_rate", [.10,.15,.19,.255,.30,.36], 1)

    def test_higher_volatility_never_reduces_pd(self):
        self.assert_monotone("revenue_volatility", [0,.03,.1,.3,.65,1,3], 1)
