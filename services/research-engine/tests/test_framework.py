import tempfile
import unittest
from pathlib import Path

from ak_system.config import build_paths, ensure_dirs
from ak_system.framework import (
    COMPONENTS,
    maybe_propose_weight_update,
    recalibrate_weights,
    run_full_framework,
    save_framework_report,
)


class FrameworkTests(unittest.TestCase):
    def test_recalibrated_weights_are_valid(self):
        # empty train -> uniform
        w = recalibrate_weights([])
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)
        for c in COMPONENTS:
            self.assertGreaterEqual(w[c], 0.0)

    def test_framework_runs_and_writes_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            paths = build_paths(root)
            ensure_dirs(paths)

            report = run_full_framework(paths, n_paths=120, seed=5)
            self.assertIn("oos_delta", report)
            self.assertIn("recalibrated_weights", report)
            self.assertAlmostEqual(sum(report["recalibrated_weights"].values()), 1.0, places=5)

            out = save_framework_report(paths, report)
            self.assertTrue(out.exists())

            maybe_path = maybe_propose_weight_update(paths, report)
            if maybe_path is not None:
                self.assertTrue(maybe_path.exists())


if __name__ == "__main__":
    unittest.main()
