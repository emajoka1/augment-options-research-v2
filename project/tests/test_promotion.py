import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ak_system.config import build_paths, ensure_dirs
from ak_system.promotion import promote_proposal
from ak_system.schemas import ChangeProposal, MonteCarloResult, ValidationMetrics


class PromotionTests(unittest.TestCase):
    def test_unverified_cannot_promote(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            paths = build_paths(root)
            ensure_dirs(paths)

            proposal = ChangeProposal(
                proposal_id="cp-test",
                created_at=datetime.now(timezone.utc),
                author_mode="RESEARCH_AGENT",
                title="t",
                summary="s",
                target_files=[],
                baseline_metrics=ValidationMetrics(0, 0, 0, 0, 0, 0),
                candidate_metrics=ValidationMetrics(0, 0, 0, 0, 0, 0),
                monte_carlo=MonteCarloResult(["vol_expansion", "gap_down", "gap_up"], 0, 0, 0),
                out_of_sample_delta=0,
                tests_passed=False,
                rollback_plan="rollback",
                status="UNVERIFIED",
            )
            pfile = root / "proposal.json"
            pfile.write_text(json.dumps(proposal.to_dict()))

            with self.assertRaises(RuntimeError):
                promote_proposal(paths, pfile, approver="human")


if __name__ == "__main__":
    unittest.main()
