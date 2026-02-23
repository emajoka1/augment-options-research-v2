from __future__ import annotations

import random
from dataclasses import asdict
from statistics import mean
from typing import Iterable, List, Sequence, Tuple

from .config import RiskConfig
from .schemas import MonteCarloResult, ValidationMetrics


Trade = Tuple[float, float]  # (R_multiple, slippage_bps)


def _max_drawdown(returns: Sequence[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for r in returns:
        equity += r
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
    return max_dd


def compute_metrics(trades: Iterable[Trade]) -> ValidationMetrics:
    rows = list(trades)
    if not rows:
        return ValidationMetrics(0, 0, 0, 0, 0, 0)

    r_values = [r for r, _ in rows]
    slips = [s for _, s in rows]

    wins = sum(1 for r in r_values if r > 0)
    win_rate = wins / len(r_values)
    avg_r = mean(r_values)
    max_dd = _max_drawdown(r_values)
    sorted_losses = sorted(r_values)
    tail_count = max(1, int(0.1 * len(sorted_losses)))
    tail_loss = mean(sorted_losses[:tail_count])
    slippage_sensitivity = mean(slips) if slips else 0.0

    return ValidationMetrics(
        win_rate=win_rate,
        avg_r=avg_r,
        max_drawdown=max_dd,
        tail_loss=tail_loss,
        slippage_sensitivity=slippage_sensitivity,
        sample_size=len(r_values),
    )


def baseline_comparator(baseline: ValidationMetrics, candidate: ValidationMetrics) -> float:
    """Weighted comparator score; >0 means candidate improved baseline."""
    return (
        0.30 * (candidate.win_rate - baseline.win_rate)
        + 0.25 * (candidate.avg_r - baseline.avg_r)
        - 0.20 * (candidate.max_drawdown - baseline.max_drawdown)
        - 0.15 * (abs(candidate.tail_loss) - abs(baseline.tail_loss))
        - 0.10 * (candidate.slippage_sensitivity - baseline.slippage_sensitivity)
    )


def monte_carlo_stress(base_trades: Sequence[Trade], runs: int = 1000) -> MonteCarloResult:
    if not base_trades:
        return MonteCarloResult(["vol_expansion", "gap_down", "gap_up"], 0.0, 0.0, 0.0)

    scenario_pnls: List[float] = []
    for _ in range(runs):
        pnl = 0.0
        for r, s in random.choices(base_trades, k=len(base_trades)):
            shock = random.choice(["vol_expansion", "gap_down", "gap_up"])
            if shock == "vol_expansion":
                pnl += r * 0.8
            elif shock == "gap_down":
                pnl += r - 0.4
            else:
                pnl += r - 0.2
            pnl -= (s / 10000)
        scenario_pnls.append(pnl)

    scenario_pnls.sort()
    n = len(scenario_pnls)
    return MonteCarloResult(
        scenarios=["vol_expansion", "gap_down", "gap_up"],
        p5_return=scenario_pnls[max(0, int(0.05 * n) - 1)],
        p50_return=scenario_pnls[int(0.50 * n)],
        p95_return=scenario_pnls[min(n - 1, int(0.95 * n))],
    )


def is_verified(metrics: ValidationMetrics, config: RiskConfig) -> bool:
    return metrics.sample_size >= config.min_sample_size
