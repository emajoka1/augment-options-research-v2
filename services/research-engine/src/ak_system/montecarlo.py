from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

import numpy as np

from .regime import RegimeLabel, classify_regime_rule_based


@dataclass
class PathConfig:
    n_steps: int = 80
    dt: float = 1 / 252
    mu: float = 0.03
    sigma: float = 0.22
    jump_prob: float = 0.03
    jump_mu: float = -0.015
    jump_sigma: float = 0.03
    garch_alpha: float = 0.10
    garch_beta: float = 0.85


@dataclass
class StressConfig:
    spread_widen_bps: float = 20.0
    slippage_shock_bps: float = 10.0
    partial_fill_prob: float = 0.12
    gap_move_sigma: float = 1.75
    iv_crush: float = -0.20
    iv_spike: float = 0.25


def generate_path(cfg: PathConfig, rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    prices = np.zeros(cfg.n_steps + 1)
    prices[0] = 100.0

    vol = np.zeros(cfg.n_steps + 1)
    vol[0] = cfg.sigma
    eps_prev = 0.0

    for t in range(1, cfg.n_steps + 1):
        z = rng.normal()
        eps = vol[t - 1] * z
        vol[t] = np.sqrt(max(1e-8, cfg.sigma**2 * (1 - cfg.garch_alpha - cfg.garch_beta) + cfg.garch_alpha * eps_prev**2 + cfg.garch_beta * vol[t - 1] ** 2))
        eps_prev = eps

        jump = 0.0
        if rng.random() < cfg.jump_prob:
            jump = rng.normal(cfg.jump_mu, cfg.jump_sigma)

        ret = (cfg.mu - 0.5 * vol[t] ** 2) * cfg.dt + vol[t] * np.sqrt(cfg.dt) * z + jump
        prices[t] = prices[t - 1] * np.exp(ret)

    return prices, vol


def _ci95(arr: np.ndarray) -> Tuple[float, float]:
    if len(arr) == 0:
        return 0.0, 0.0
    lo, hi = np.percentile(arr, [2.5, 97.5])
    return float(lo), float(hi)


def _stress_penalty(stress: StressConfig, rng: np.random.Generator) -> float:
    penalty = 0.0
    penalty += stress.spread_widen_bps / 10000
    penalty += stress.slippage_shock_bps / 10000
    if rng.random() < stress.partial_fill_prob:
        penalty += 0.08
    gap_shock = abs(rng.normal(0, stress.gap_move_sigma)) * 0.04
    penalty += gap_shock
    return penalty


def evaluate_playbook_on_path(playbook: str, prices: np.ndarray, vol: np.ndarray, stress: StressConfig, rng: np.random.Generator) -> Tuple[float, Dict[str, float], RegimeLabel]:
    regime = classify_regime_rule_based(prices, vol)
    ret = (prices[-1] - prices[0]) / prices[0]
    realized_vol = float(np.std(np.diff(np.log(prices)))) * np.sqrt(252)

    # Simplified playbook behavior model in R-multiples.
    if playbook == "trend_debit":
        base_r = 1.6 * ret if regime.trend == "trend" else -0.6 * abs(ret)
        iv_effect = 0.20 if regime.vol == "vol_contracting" else -0.15
    elif playbook == "mean_revert_credit":
        base_r = 0.8 - 1.2 * abs(ret)
        iv_effect = 0.25 if regime.vol == "vol_contracting" else -0.35
    elif playbook == "long_vol_event":
        base_r = 0.3 + 1.0 * realized_vol
        iv_effect = -0.25 if regime.vol == "vol_contracting" else 0.30
    else:
        base_r = 0.0
        iv_effect = 0.0

    iv_shock = stress.iv_spike if regime.vol == "vol_expanding" else stress.iv_crush
    stress_penalty = _stress_penalty(stress, rng)

    r = base_r + iv_effect + 0.2 * iv_shock - stress_penalty
    failure = {
        "spread_slippage": stress_penalty,
        "gap_risk": max(0.0, stress_penalty - 0.04),
        "iv_regime_mismatch": 1.0 if (playbook == "mean_revert_credit" and regime.vol == "vol_expanding") else 0.0,
    }
    return float(r), failure, regime


def run_regime_harness(n_paths: int = 500, seed: int = 7) -> Dict[str, object]:
    rng = np.random.default_rng(seed)
    pcfg = PathConfig()
    scfg = StressConfig()
    playbooks = ["trend_debit", "mean_revert_credit", "long_vol_event"]

    by_regime: Dict[str, Dict[str, List[float]]] = {}
    failures: Dict[str, Dict[str, float]] = {p: {"spread_slippage": 0.0, "gap_risk": 0.0, "iv_regime_mismatch": 0.0} for p in playbooks}

    for _ in range(n_paths):
        prices, vol = generate_path(pcfg, rng)
        for p in playbooks:
            r, fail, regime = evaluate_playbook_on_path(p, prices, vol, scfg, rng)
            rk = regime.key
            by_regime.setdefault(rk, {}).setdefault(p, []).append(r)
            for k, v in fail.items():
                failures[p][k] += v

    ranking: Dict[str, List[Dict[str, object]]] = {}
    for rk, pb_map in by_regime.items():
        rows = []
        for p, vals in pb_map.items():
            arr = np.array(vals)
            lo, hi = _ci95(arr)
            rows.append({
                "playbook": p,
                "mean_r": float(np.mean(arr)),
                "ci95": [lo, hi],
                "n": int(len(arr)),
            })
        rows.sort(key=lambda x: x["mean_r"], reverse=True)
        ranking[rk] = rows

    # Normalize failure modes
    for p in playbooks:
        for k in failures[p]:
            failures[p][k] = float(failures[p][k] / n_paths)

    return {
        "n_paths": n_paths,
        "path_model": "GBM + jump diffusion + volatility clustering",
        "stress": asdict(scfg),
        "ranking_by_regime": ranking,
        "failure_modes": failures,
    }
