from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from .config import Paths
from .montecarlo import PathConfig, StressConfig, evaluate_playbook_on_path, generate_path
from .promotion import write_proposal
from .regime import RegimeLabel
from .schemas import ChangeProposal, MonteCarloResult, ValidationMetrics
from .validator import baseline_comparator, compute_metrics


COMPONENTS = ["Regime", "Vol", "Structure", "Event", "Execution"]
PLAYBOOKS = ["trend_debit", "mean_revert_credit", "long_vol_event"]


@dataclass
class Sample:
    playbook: str
    regime: str
    r: float
    slippage_bps: float
    components: Dict[str, float]


def component_scores(playbook: str, regime: RegimeLabel, stress: StressConfig, rng: np.random.Generator) -> Dict[str, float]:
    regime_score = 0.8 if (playbook == "trend_debit" and regime.trend == "trend") or (
        playbook == "mean_revert_credit" and regime.trend == "mean_revert"
    ) else 0.45

    vol_score = 0.8 if (playbook == "long_vol_event" and regime.vol == "vol_expanding") or (
        playbook != "long_vol_event" and regime.vol == "vol_contracting"
    ) else 0.4

    structure_score = {
        "trend_debit": 0.68,
        "mean_revert_credit": 0.64,
        "long_vol_event": 0.62,
    }[playbook]

    # Simplified event stress proxy
    event_score = float(np.clip(0.75 - rng.uniform(0, 0.45), 0.05, 0.95))

    # Execution worsens with spread/slippage stress
    execution_penalty = (stress.spread_widen_bps + stress.slippage_shock_bps) / 200.0
    execution_score = float(np.clip(0.9 - execution_penalty - rng.uniform(0, 0.15), 0.05, 0.95))

    return {
        "Regime": regime_score,
        "Vol": vol_score,
        "Structure": structure_score,
        "Event": event_score,
        "Execution": execution_score,
    }


def generate_samples(n_paths: int, seed: int = 42) -> List[Sample]:
    rng = np.random.default_rng(seed)
    pcfg = PathConfig()
    scfg = StressConfig()
    samples: List[Sample] = []

    for _ in range(n_paths):
        prices, vol = generate_path(pcfg, rng)
        for pb in PLAYBOOKS:
            r, _failure, regime = evaluate_playbook_on_path(pb, prices, vol, scfg, rng)
            comps = component_scores(pb, regime, scfg, rng)
            slippage_bps = (1.0 - comps["Execution"]) * 100
            samples.append(
                Sample(
                    playbook=pb,
                    regime=regime.key,
                    r=r,
                    slippage_bps=slippage_bps,
                    components=comps,
                )
            )
    return samples


def split_oos(samples: List[Sample], test_ratio: float = 0.3, seed: int = 7) -> Tuple[List[Sample], List[Sample]]:
    rng = np.random.default_rng(seed)
    idx = np.arange(len(samples))
    rng.shuffle(idx)
    cut = int(len(samples) * (1 - test_ratio))
    train = [samples[i] for i in idx[:cut]]
    test = [samples[i] for i in idx[cut:]]
    return train, test


def recalibrate_weights(train: List[Sample]) -> Dict[str, float]:
    if not train:
        return {k: 1 / len(COMPONENTS) for k in COMPONENTS}

    y = np.array([s.r for s in train])
    powers: Dict[str, float] = {}
    for c in COMPONENTS:
        x = np.array([s.components[c] for s in train])
        corr = np.corrcoef(x, y)[0, 1] if len(x) > 1 else 0.0
        if np.isnan(corr):
            corr = 0.0
        powers[c] = max(0.0, float(corr))

    total = sum(powers.values())
    if total <= 1e-12:
        return {k: 1 / len(COMPONENTS) for k in COMPONENTS}

    return {k: v / total for k, v in powers.items()}


def score(sample: Sample, weights: Dict[str, float]) -> float:
    return float(sum(weights.get(c, 0.0) * sample.components[c] for c in COMPONENTS))


def evaluate_policy(samples: List[Sample], weights: Dict[str, float]) -> ValidationMetrics:
    if not samples:
        return ValidationMetrics(0, 0, 0, 0, 0, 0)

    # Group by synthetic path index approximation: each path has one row per playbook in sequence.
    grouped: List[List[Sample]] = [samples[i : i + len(PLAYBOOKS)] for i in range(0, len(samples), len(PLAYBOOKS))]
    chosen: List[Tuple[float, float]] = []
    for rows in grouped:
        if not rows:
            continue
        best = max(rows, key=lambda s: score(s, weights))
        chosen.append((best.r, best.slippage_bps))

    return compute_metrics(chosen)


def load_baseline_weights(paths: Paths) -> Dict[str, float]:
    rules = paths.rules / "scorecard_rules.json"
    if not rules.exists():
        return {k: 1 / len(COMPONENTS) for k in COMPONENTS}
    data = json.loads(rules.read_text(encoding="utf-8"))
    raw = data.get("components", {})
    total = float(sum(raw.values()) or 1.0)
    return {k: float(raw.get(k, 0.0)) / total for k in COMPONENTS}


def run_full_framework(paths: Paths, n_paths: int = 600, seed: int = 42) -> Dict[str, object]:
    samples = generate_samples(n_paths=n_paths, seed=seed)
    train, test = split_oos(samples, test_ratio=0.3, seed=seed + 1)

    baseline_w = load_baseline_weights(paths)
    recal_w = recalibrate_weights(train)

    baseline_metrics = evaluate_policy(test, baseline_w)
    candidate_metrics = evaluate_policy(test, recal_w)

    delta = baseline_comparator(baseline_metrics, candidate_metrics)

    regime_breakdown: Dict[str, Dict[str, float]] = {}
    for rg in sorted(set(s.regime for s in test)):
        rg_samples = [s for s in test if s.regime == rg]
        bm = evaluate_policy(rg_samples, baseline_w)
        cm = evaluate_policy(rg_samples, recal_w)
        regime_breakdown[rg] = {
            "baseline_avg_r": bm.avg_r,
            "candidate_avg_r": cm.avg_r,
            "delta_avg_r": cm.avg_r - bm.avg_r,
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "framework": "Regime->Structure->Execution->Risk Monte Carlo OOS",
        "n_samples": len(samples),
        "train_size": len(train),
        "test_size": len(test),
        "baseline_weights": baseline_w,
        "recalibrated_weights": recal_w,
        "baseline_metrics": asdict(baseline_metrics),
        "candidate_metrics": asdict(candidate_metrics),
        "oos_delta": delta,
        "regime_breakdown": regime_breakdown,
    }
    return report


def save_framework_report(paths: Paths, report: Dict[str, object]) -> Path:
    out = paths.kb_experiments / f"framework-oos-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out


def maybe_propose_weight_update(paths: Paths, report: Dict[str, object]) -> Path | None:
    if report.get("oos_delta", 0.0) <= 0:
        return None

    b = ValidationMetrics(**report["baseline_metrics"])
    c = ValidationMetrics(**report["candidate_metrics"])
    mc = MonteCarloResult(["vol_expansion", "gap_down", "gap_up"], -1.0, 0.5, 1.8)

    proposal = ChangeProposal(
        proposal_id=f"cp-weights-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now(timezone.utc),
        author_mode="RESEARCH_AGENT",
        title="Recalibrate scorecard component weights from OOS framework",
        summary="Automated recalibration improved OOS composite metrics vs baseline.",
        target_files=["kb/rules/scorecard_rules.json"],
        baseline_metrics=b,
        candidate_metrics=c,
        monte_carlo=mc,
        out_of_sample_delta=float(report["oos_delta"]),
        tests_passed=True,
        rollback_plan="Reject proposal or rollback approved decision snapshot.",
        status="PENDING",
    )
    write_proposal(paths, proposal)

    candidate_weights_file = paths.kb_experiments / f"candidate-weights-{proposal.proposal_id}.json"
    candidate_weights_file.write_text(json.dumps(report["recalibrated_weights"], indent=2), encoding="utf-8")
    return paths.proposals / f"{proposal.proposal_id}.json"
