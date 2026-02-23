from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

from .config import Paths, RiskConfig
from .schemas import ChangeProposal, Evidence, KnowledgeItem
from .validator import (
    baseline_comparator,
    compute_metrics,
    is_verified,
    monte_carlo_stress,
)


def collect(paths: Paths) -> Path:
    """Collect phase: ingest available trade logs / source notes into sources index."""
    index = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source_files": [str(p.relative_to(paths.root)) for p in sorted(paths.trade_logs.glob("**/*"))],
    }
    out = paths.sources / f"collect-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return out


def distill(paths: Paths) -> Path:
    """Distill phase: create structured knowledge item candidates."""
    item = KnowledgeItem(
        item_id=f"ki-{uuid.uuid4().hex[:10]}",
        title="Short premium requires vol-context confirmation",
        claim="In neutral-to-unstable regime, only short premium when IV percentile >70 or clear vol contraction exists.",
        evidence=[
            Evidence(
                source_id="trade-log-sample",
                source_type="trade_log",
                excerpt="Reactive trades performed better than passive premium selling in unstable tape.",
            )
        ],
        confidence=0.55,
        last_verified_date=date.today(),
        expiry=date.today() + timedelta(days=14),
        status="UNVERIFIED",
        tags=["regime", "volatility", "short-premium"],
    )
    out = paths.summaries / f"{item.item_id}.json"
    out.write_text(json.dumps(item.to_dict(), indent=2), encoding="utf-8")
    return out


def _load_trade_samples(paths: Paths) -> List[tuple[float, float]]:
    """Load lightweight synthetic trades from experiments/trades.csv if present.

    CSV format: r_multiple,slippage_bps
    """
    csv_path = paths.experiments / "trades.csv"
    if not csv_path.exists():
        return []

    rows: List[tuple[float, float]] = []
    for line in csv_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "r_multiple" in line:
            continue
        r, s = line.split(",")
        rows.append((float(r.strip()), float(s.strip())))
    return rows


def validate(paths: Paths, risk: RiskConfig) -> Dict[str, object]:
    """Validate phase: run baseline comparator + monte carlo stress + verification gating."""
    candidate = _load_trade_samples(paths)
    baseline = [(0.12, 6.0), (-0.35, 7.0), (0.08, 6.0), (-0.20, 8.0), (0.15, 5.0)] * 8
    if not candidate:
        report = {
            "status": "UNVERIFIED",
            "reason": "Insufficient data",
            "required_sample": risk.min_sample_size,
            "observed_sample": 0,
        }
    else:
        b = compute_metrics(baseline)
        c = compute_metrics(candidate)
        mc = monte_carlo_stress(candidate)
        verified = is_verified(c, risk)
        report = {
            "status": "VERIFIED" if verified else "UNVERIFIED",
            "baseline_metrics": asdict(b),
            "candidate_metrics": asdict(c),
            "out_of_sample_delta": baseline_comparator(b, c),
            "monte_carlo": asdict(mc),
            "tests_required": ["unit", "backtest_or_replay", "monte_carlo", "ab_vs_baseline"],
            "tests_passed": verified,
        }

    out = paths.kb_experiments / f"validate-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def propose(paths: Paths, validation_report: Dict[str, object]) -> Path:
    from .promotion import write_proposal
    from .schemas import ChangeProposal, MonteCarloResult, ValidationMetrics

    now = datetime.now(timezone.utc)

    if validation_report.get("status") == "UNVERIFIED":
        # Still write proposal, but explicitly blocked.
        baseline = ValidationMetrics(0, 0, 0, 0, 0, 0)
        candidate = ValidationMetrics(0, 0, 0, 0, 0, 0)
        mc = MonteCarloResult(["vol_expansion", "gap_down", "gap_up"], 0, 0, 0)
        status = "UNVERIFIED"
        delta = 0.0
        tests_passed = False
    else:
        baseline = ValidationMetrics(**validation_report["baseline_metrics"])
        candidate = ValidationMetrics(**validation_report["candidate_metrics"])
        mc = MonteCarloResult(**validation_report["monte_carlo"])
        status = "PENDING"
        delta = float(validation_report["out_of_sample_delta"])
        tests_passed = bool(validation_report["tests_passed"])

    proposal = ChangeProposal(
        proposal_id=f"cp-{now.strftime('%Y%m%d-%H%M%S')}",
        created_at=now,
        author_mode="RESEARCH_AGENT",
        title="Update scorecard regime and volatility thresholds",
        summary="Candidate update calibrated from recent trades and stress-tested vs baseline.",
        target_files=["kb/rules/scorecard_rules.json", "kb/playbooks/pre_trade_checklist.md"],
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        monte_carlo=mc,
        out_of_sample_delta=delta,
        tests_passed=tests_passed,
        rollback_plan="Restore latest kb snapshot from /snapshots and revert approved decision file.",
        status=status,
    )
    return write_proposal(paths, proposal)


def promote(paths: Paths, proposal_path: Path, approver: str = "human") -> Dict[str, str]:
    from .promotion import promote_proposal

    pending, approved = promote_proposal(paths, proposal_path, approver=approver)
    return {"pending": str(pending), "approved": str(approved)}
