from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

from .config import Paths
from .schemas import ChangeProposal


def write_proposal(paths: Paths, proposal: ChangeProposal) -> Path:
    paths.proposals.mkdir(parents=True, exist_ok=True)
    out = paths.proposals / f"{proposal.proposal_id}.json"
    out.write_text(json.dumps(proposal.to_dict(), indent=2), encoding="utf-8")

    md = paths.proposals / f"{proposal.proposal_id}.md"
    md.write_text(_proposal_markdown(proposal), encoding="utf-8")
    return out


def _proposal_markdown(proposal: ChangeProposal) -> str:
    return f"""# CHANGE_PROPOSAL: {proposal.proposal_id}

## Title
{proposal.title}

## Summary
{proposal.summary}

## Baseline vs Candidate
- Win rate: {proposal.baseline_metrics.win_rate:.3f} -> {proposal.candidate_metrics.win_rate:.3f}
- Avg R: {proposal.baseline_metrics.avg_r:.3f} -> {proposal.candidate_metrics.avg_r:.3f}
- Max DD: {proposal.baseline_metrics.max_drawdown:.3f} -> {proposal.candidate_metrics.max_drawdown:.3f}
- Tail loss: {proposal.baseline_metrics.tail_loss:.3f} -> {proposal.candidate_metrics.tail_loss:.3f}
- Slippage sensitivity: {proposal.baseline_metrics.slippage_sensitivity:.3f} -> {proposal.candidate_metrics.slippage_sensitivity:.3f}

## Monte Carlo Stress
- Scenarios: {', '.join(proposal.monte_carlo.scenarios)}
- P5/P50/P95: {proposal.monte_carlo.p5_return:.3f} / {proposal.monte_carlo.p50_return:.3f} / {proposal.monte_carlo.p95_return:.3f}

## Out-of-sample delta
{proposal.out_of_sample_delta:.4f}

## Tests passed
{proposal.tests_passed}

## Rollback plan
{proposal.rollback_plan}

## Approval
Manual approval required. Promote only after sign-off.
"""


def promote_proposal(paths: Paths, proposal_file: Path, approver: str) -> Tuple[Path, Path]:
    data = json.loads(proposal_file.read_text(encoding="utf-8"))
    if data.get("status") == "UNVERIFIED":
        raise RuntimeError("Cannot promote UNVERIFIED proposal")
    if not data.get("tests_passed"):
        raise RuntimeError("Cannot promote proposal without passing tests")

    approved = paths.decisions_approved / proposal_file.name
    pending = paths.decisions_pending / proposal_file.name
    pending.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(proposal_file, pending)

    data["status"] = "APPROVED"
    data["approved_at"] = datetime.now(timezone.utc).isoformat()
    data["approved_by"] = approver
    approved.write_text(json.dumps(data, indent=2), encoding="utf-8")

    _create_snapshot(paths)
    return pending, approved


def reject_proposal(paths: Paths, proposal_file: Path, reason: str) -> Path:
    data = json.loads(proposal_file.read_text(encoding="utf-8"))
    data["status"] = "REJECTED"
    data["rejected_reason"] = reason
    out = paths.decisions_rejected / proposal_file.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out


def _create_snapshot(paths: Paths) -> Path:
    paths.snapshots.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = paths.snapshots / f"kb-{ts}"
    shutil.copytree(paths.kb, dst)
    return dst


def rollback_latest(paths: Paths) -> Path:
    snaps = sorted(paths.snapshots.glob("kb-*"))
    if not snaps:
        raise RuntimeError("No snapshots available for rollback")
    latest = snaps[-1]
    if paths.kb.exists():
        shutil.rmtree(paths.kb)
    shutil.copytree(latest, paths.kb)
    return latest
