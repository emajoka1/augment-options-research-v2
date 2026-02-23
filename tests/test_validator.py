import unittest

from ak_system.config import RiskConfig
from ak_system.validator import baseline_comparator, compute_metrics, is_verified, monte_carlo_stress


class ValidatorTests(unittest.TestCase):
    def test_compute_metrics(self):
        trades = [(0.5, 5), (-0.2, 6), (0.3, 4), (-0.1, 7)]
        m = compute_metrics(trades)
        self.assertEqual(m.sample_size, 4)
        self.assertGreater(m.win_rate, 0)

    def test_baseline_comparator(self):
        b = compute_metrics([(0.1, 6)] * 40)
        c = compute_metrics([(0.2, 5)] * 40)
        self.assertGreater(baseline_comparator(b, c), 0)

    def test_monte_carlo(self):
        mc = monte_carlo_stress([(0.2, 5)] * 50, runs=100)
        self.assertTrue(mc.p5_return <= mc.p50_return <= mc.p95_return)

    def test_verified_gate(self):
        m = compute_metrics([(0.1, 5)] * 29)
        self.assertFalse(is_verified(m, RiskConfig(min_sample_size=30)))
        m2 = compute_metrics([(0.1, 5)] * 30)
        self.assertTrue(is_verified(m2, RiskConfig(min_sample_size=30)))


if __name__ == "__main__":
    unittest.main()
