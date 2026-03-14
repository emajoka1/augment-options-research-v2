from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    root: Path
    kb: Path
    sources: Path
    summaries: Path
    concepts: Path
    playbooks: Path
    rules: Path
    kb_experiments: Path
    decisions: Path
    decisions_approved: Path
    decisions_pending: Path
    decisions_rejected: Path
    trade_logs: Path
    experiments: Path
    proposals: Path
    snapshots: Path


@dataclass(frozen=True)
class RiskConfig:
    min_sample_size: int = 30
    min_confidence: float = 0.6


@dataclass(frozen=True)
class Schedules:
    collect_minutes: int = 30
    distill_minutes: int = 60
    validate_minutes: int = 120
    propose_minutes: int = 180
    promote_minutes: int = 240


def build_paths(root: Path) -> Paths:
    kb = root / "kb"
    decisions = kb / "decisions"
    return Paths(
        root=root,
        kb=kb,
        sources=kb / "sources",
        summaries=kb / "summaries",
        concepts=kb / "concepts",
        playbooks=kb / "playbooks",
        rules=kb / "rules",
        kb_experiments=kb / "experiments",
        decisions=decisions,
        decisions_approved=decisions / "approved",
        decisions_pending=decisions / "pending",
        decisions_rejected=decisions / "rejected",
        trade_logs=kb / "trade_logs",
        experiments=root / "experiments",
        proposals=root / "proposals",
        snapshots=root / "snapshots",
    )


def ensure_dirs(paths: Paths) -> None:
    for p in paths.__dict__.values():
        if isinstance(p, Path):
            if p.suffix:
                continue
            p.mkdir(parents=True, exist_ok=True)
