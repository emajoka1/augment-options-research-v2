from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

Status = Literal["VERIFIED", "UNVERIFIED", "REJECTED"]


@dataclass
class Evidence:
    source_id: str
    source_type: Literal["trade_log", "research_note", "market_data", "backtest", "replay"]
    excerpt: str


@dataclass
class KnowledgeItem:
    item_id: str
    title: str
    claim: str
    evidence: List[Evidence]
    confidence: float
    last_verified_date: date
    expiry: date
    status: Status
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["last_verified_date"] = self.last_verified_date.isoformat()
        d["expiry"] = self.expiry.isoformat()
        return d


@dataclass
class ValidationMetrics:
    win_rate: float
    avg_r: float
    max_drawdown: float
    tail_loss: float
    slippage_sensitivity: float
    sample_size: int


@dataclass
class MonteCarloResult:
    scenarios: List[Literal["vol_expansion", "gap_down", "gap_up"]]
    p5_return: float
    p50_return: float
    p95_return: float


@dataclass
class ChangeProposal:
    proposal_id: str
    created_at: datetime
    author_mode: Literal["RESEARCH_AGENT"]
    title: str
    summary: str
    target_files: List[str]
    baseline_metrics: ValidationMetrics
    candidate_metrics: ValidationMetrics
    monte_carlo: MonteCarloResult
    out_of_sample_delta: float
    tests_passed: bool
    rollback_plan: str
    approval_required: bool = True
    status: Literal["PENDING", "APPROVED", "REJECTED", "UNVERIFIED"] = "PENDING"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d
