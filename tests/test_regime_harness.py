import tempfile
import unittest
from pathlib import Path

import numpy as np

from ak_system.config import build_paths, ensure_dirs
from ak_system.pipeline import propose_if_improved_from_regime_report, run_regime_validation
from ak_system.regime import classify_regime_rule_based


class RegimeHarnessTests(unittest.TestCase):
    def test_rule_based_classifier_outputs_valid_labels(self):
        prices = np.linspace(100, 110, 40)
        vol = np.linspace(0.2, 0.3, 40)
        lbl = classify_regime_rule_based(prices, vol)
        self.assertIn(lbl.trend, {"trend", "mean_revert"})
        self.assertIn(lbl.vol, {"vol_expanding", "vol_contracting"})

    def test_harness_writes_report_and_maybe_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            paths = build_paths(root)
            ensure_dirs(paths)

            report = run_regime_validation(paths, n_paths=60)
            self.assertTrue(report.exists())

            proposal = propose_if_improved_from_regime_report(paths, report)
            # Can be None depending on stochastic outcomes; function should not crash.
            if proposal:
                self.assertTrue(proposal.exists())


if __name__ == "__main__":
    unittest.main()
