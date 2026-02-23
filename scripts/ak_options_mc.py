#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ak_system.config import build_paths, ensure_dirs
from ak_system.mc_options.calibration import calibrate_from_snapshot, defaults_from_market, parse_chain_snapshot
from ak_system.mc_options.metrics import compute_metrics, percentiles
from ak_system.mc_options.models import GBMParams, HestonParams, JumpDiffusionParams, simulate_gbm_paths, simulate_heston_paths, simulate_jump_diffusion_paths
from ak_system.mc_options.report import write_report_json_md
from ak_system.mc_options.simulator import FrictionConfig, simulate_strategy_paths
from ak_system.mc_options.strategy import (
    compute_breakevens,
    default_exit_rules_for_strategy,
    make_iron_fly,
    make_long_straddle,
    make_put_calendar,
    make_put_debit_spread,
    make_put_diagonal,
)
from ak_system.regime import classify_regime_rule_based


def build_strategy(example: str, spot: float, expiry_years: float):
    k = round(spot)
    if example == "iron_fly":
        return make_iron_fly(center=k, wing=max(2.0, round(spot * 0.01)), expiry_years=expiry_years, qty=1)
    if example == "long_straddle":
        return make_long_straddle(K=k, expiry_years=expiry_years, qty=1)
    if example == "put_debit_spread":
        return make_put_debit_spread(long_strike=k, short_strike=k - max(1.0, round(spot * 0.003)), expiry_years=expiry_years, qty=1)
    if example == "put_calendar":
        return make_put_calendar(strike=k, front_expiry_years=max(expiry_years * 0.4, 1 / 365), back_expiry_years=expiry_years, qty=1)
    if example == "put_diagonal":
        return make_put_diagonal(
            long_strike=k - max(1.0, round(spot * 0.004)),
            short_strike=k,
            front_expiry_years=max(expiry_years * 0.4, 1 / 365),
            back_expiry_years=expiry_years,
            qty=1,
        )
    raise ValueError("unknown example")


def strategy_signature(strategy) -> tuple:
    legs = tuple((leg.side, leg.option_type, float(leg.strike), int(leg.qty), float(leg.expiry_years or 0.0)) for leg in strategy.legs)
    return strategy.name, legs


def assert_paired_seed_policy(
    baseline_model: str,
    sensitivity_model: str,
    baseline_strategy,
    sensitivity_strategy,
):
    if baseline_model != sensitivity_model:
        raise ValueError("Seed policy assertion failed: paired comparison requires identical model")

    b_name, b_legs = strategy_signature(baseline_strategy)
    s_name, s_legs = strategy_signature(sensitivity_strategy)
    if b_name != s_name:
        raise ValueError("Seed policy assertion failed: paired comparison requires identical strategy name")
    if b_legs != s_legs:
        raise ValueError("Seed policy assertion failed: paired comparison requires identical structural legs")


def infer_regime_distribution(model: str, spot: float, iv_atm: float, n_steps: int, dt: float, r: float, q: float, seed: int) -> dict:
    n_probe = 300
    if model == "gbm":
        paths = simulate_gbm_paths(spot, n_probe, n_steps, dt, params=GBMParams(mu=r - q, sigma=max(0.05, iv_atm)), seed=seed)
    elif model == "heston":
        paths, _ = simulate_heston_paths(
            spot,
            n_probe,
            n_steps,
            dt,
            params=HestonParams(mu=r - q, v0=max(1e-8, iv_atm**2), theta=max(1e-8, iv_atm**2)),
            seed=seed,
        )
    else:
        paths = simulate_jump_diffusion_paths(
            spot,
            n_probe,
            n_steps,
            dt,
            params=JumpDiffusionParams(mu=r - q, sigma=max(0.05, iv_atm), jump_lambda=0.35, jump_mu=-0.05, jump_sigma=0.18),
            seed=seed,
        )

    counts = {}
    for i in range(n_probe):
        p = paths[i]
        ret = (p[1:] / p[:-1] - 1.0)
        lbl = classify_regime_rule_based(p, abs(ret), lookback=min(20, len(ret))).key
        counts[lbl] = counts.get(lbl, 0) + 1

    total = max(1, sum(counts.values()))
    probs = {k: v / total for k, v in counts.items()}
    probs["dominant"] = max(counts.items(), key=lambda kv: kv[1])[0]
    return probs


def main():
    p = argparse.ArgumentParser(description="Real options Monte Carlo engine")
    p.add_argument("--spot", type=float, default=690.0)
    p.add_argument("--r", type=float, default=0.03)
    p.add_argument("--q", type=float, default=0.0)
    p.add_argument("--expiry-days", type=float, default=5)
    p.add_argument("--n-paths", type=int, default=5000)
    p.add_argument("--dt-days", type=float, default=0.25)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--model", choices=["gbm", "jump", "heston"], default="jump")
    p.add_argument("--example", choices=["iron_fly", "long_straddle", "put_debit_spread", "put_calendar", "put_diagonal"], default="iron_fly")
    p.add_argument("--snapshot-file", type=str, default=None, help="Path to chain snapshot JSON/CSV (spot, strike, iv)")
    p.add_argument("--spread-bps", type=float, default=30.0)
    p.add_argument("--slippage-bps", type=float, default=8.0)
    p.add_argument("--partial-fill-prob", type=float, default=0.1)
    p.add_argument("--event-risk-high", action="store_true")
    args = p.parse_args()

    paths = build_paths(Path(".").resolve())
    ensure_dirs(paths)

    expiry_years = args.expiry_days / 365.0
    n_steps = max(2, int(args.expiry_days / args.dt_days))
    dt = expiry_years / n_steps

    spot = args.spot
    rv10 = rv20 = None
    jump_used = None

    if args.snapshot_file:
        snap = parse_chain_snapshot(args.snapshot_file)
        cal = calibrate_from_snapshot(snap, dt=dt)
        spot, rv10, rv20, jump_used = float(snap.spot), cal.rv10, cal.rv20, cal.jump
        ivp = cal.iv
    else:
        _, jump_used, _, ivp = defaults_from_market(spot=spot, iv_atm=0.25)

    strategy = build_strategy(args.example, spot, expiry_years)
    exits = default_exit_rules_for_strategy(strategy.name)
    friction = FrictionConfig(spread_bps=args.spread_bps, slippage_bps=args.slippage_bps, partial_fill_prob=args.partial_fill_prob)

    base_seed = args.seed
    comparison_mode = "paired"
    assert_paired_seed_policy(args.model, args.model, strategy, strategy)

    # Layer 1: ideal mid-fill (no friction)
    pnl_mid, pot_mid = simulate_strategy_paths(
        strategy=strategy,
        S0=spot,
        r=args.r,
        q=args.q,
        n_paths=args.n_paths,
        n_steps=n_steps,
        dt=dt,
        iv_params=ivp,
        exit_rules=exits,
        friction=FrictionConfig(spread_bps=0.0, slippage_bps=0.0, partial_fill_prob=0.0),
        model=args.model,
        seed=base_seed,
        event_risk_high=args.event_risk_high,
    )
    m_mid = compute_metrics(pnl_mid, pot_mid)

    # Layer 2: realistic friction baseline
    pnl, pot_flags = simulate_strategy_paths(
        strategy=strategy,
        S0=spot,
        r=args.r,
        q=args.q,
        n_paths=args.n_paths,
        n_steps=n_steps,
        dt=dt,
        iv_params=ivp,
        exit_rules=exits,
        friction=friction,
        model=args.model,
        seed=base_seed,
        event_risk_high=args.event_risk_high,
    )
    metrics = compute_metrics(pnl, pot_flags)

    # Layer 3: bad-day friction stress
    pnl_wide, pot_wide = simulate_strategy_paths(
        strategy=strategy,
        S0=spot,
        r=args.r,
        q=args.q,
        n_paths=max(1000, args.n_paths // 2),
        n_steps=n_steps,
        dt=dt,
        iv_params=ivp,
        exit_rules=exits,
        friction=FrictionConfig(spread_bps=args.spread_bps * 1.8, slippage_bps=args.slippage_bps * 1.6, partial_fill_prob=min(0.6, args.partial_fill_prob * 1.5)),
        model=args.model,
        seed=base_seed,
        event_risk_high=args.event_risk_high,
    )
    m_wide = compute_metrics(pnl_wide, pot_wide)

    entry_proxy = float(max(1e-6, -float(metrics.avg_loss) if metrics.avg_loss < 0 else abs(metrics.avg_win)))
    breakevens = compute_breakevens(strategy, entry_proxy)

    regime_probs = infer_regime_distribution(args.model, spot, ivp.iv_atm, n_steps, dt, args.r, args.q, args.seed + 7)
    dominant_regime = regime_probs["dominant"]

    R_unit = max(abs(metrics.min_pl), 1e-6)
    ev_r = metrics.ev / R_unit
    cvar_r = metrics.cvar95 / R_unit
    is_short_premium = strategy.name in {"iron_fly", "iron_condor"}

    if dominant_regime == "trend|vol_expanding":
        ev_req, cvar_req = 0.10, -0.70
    elif dominant_regime == "mean_revert|vol_contracting":
        ev_req, cvar_req = 0.05, -1.00
    else:
        ev_req, cvar_req = 0.07, -0.85

    ev_mid_r = m_mid.ev / R_unit
    ev_real_r = metrics.ev / R_unit
    ev_stress_r = m_wide.ev / R_unit
    friction_hurdle = {
        "ev_mid": m_mid.ev,
        "ev_real": metrics.ev,
        "ev_stress": m_wide.ev,
        "delta_ev_real": metrics.ev - m_mid.ev,
        "delta_ev_stress": m_wide.ev - m_mid.ev,
        "ev_mid_R": ev_mid_r,
        "ev_real_R": ev_real_r,
        "ev_stress_R": ev_stress_r,
    }

    gate = {
        "regime": dominant_regime,
        "ev_threshold_R": ev_req,
        "cvar_threshold_R": cvar_req,
        "ev_gate": ev_real_r > ev_req,
        "cvar_gate": cvar_r > cvar_req,
        "pop_or_pot": (metrics.pop > 0.55) if is_short_premium else (metrics.pot > 0.45),
        "slippage_sensitivity_ok": abs(m_wide.ev - metrics.ev) / R_unit < 0.35,
        "stress_ev_not_catastrophic": ev_stress_r > -0.50,
    }

    # edge attribution (required for ALLOW)
    iv_rv_gap = None if rv20 is None else float(ivp.iv_atm - rv20)
    regime_prob = float(regime_probs.get(dominant_regime, 0.0))
    expected_move = float(spot * ivp.iv_atm * (expiry_years**0.5))
    if breakevens:
        be_dist = min(abs(b - spot) for b in breakevens)
        structure_match = float(max(0.0, 1.0 - abs(be_dist - expected_move) / max(expected_move, 1e-6)))
    else:
        structure_match = 0.0

    attribution = {
        "iv_rich_vs_rv": iv_rv_gap,
        "mean_reversion_regime_probability": float(regime_probs.get("mean_revert|vol_contracting", 0.0)),
        "structure_expected_move_match": structure_match,
        "explainable": bool(iv_rv_gap is not None and regime_prob > 0 and structure_match > 0),
    }

    gate["allow_trade"] = bool(
        gate["ev_gate"]
        and gate["cvar_gate"]
        and gate["pop_or_pot"]
        and gate["slippage_sensitivity_ok"]
        and gate["stress_ev_not_catastrophic"]
        and attribution["explainable"]
    )

    payload = {
        "assumptions": {
            "model": args.model,
            "spot": spot,
            "r": args.r,
            "q": args.q,
            "expiry_years": expiry_years,
            "n_paths": args.n_paths,
            "dt": dt,
            "seed": args.seed,
            "strategy": strategy.name,
            "legs": [leg.__dict__ for leg in strategy.legs],
            "snapshot_file": args.snapshot_file,
            "event_risk_high": args.event_risk_high,
        },
        "randomness_policy": {
            "comparison_mode": comparison_mode,
            "base_seed": base_seed,
            "sensitivity_seed": base_seed,
            "crn_scope": "same_model_same_structure_friction_only",
            "cross_model_or_cross_structure": "unpaired_independent_seeds_required",
        },
        "calibration": {
            "iv_atm": ivp.iv_atm,
            "skew": ivp.skew,
            "curv": ivp.curv,
            "term": ivp.term,
            "rv10": rv10,
            "rv20": rv20,
            "jump": jump_used.__dict__ if jump_used else None,
        },
        "regime_distribution": regime_probs,
        "stress": {
            "spread_bps": args.spread_bps,
            "slippage_bps": args.slippage_bps,
            "partial_fill_prob": args.partial_fill_prob,
        },
        "metrics": metrics.__dict__,
        "distribution_percentiles": percentiles(pnl),
        "sensitivity": {
            "wide_spread_slippage_ev": m_wide.ev,
            "wide_spread_slippage_pop": m_wide.pop,
            "wide_spread_slippage_cvar95": m_wide.cvar95,
            "ev_delta_real_to_stress": m_wide.ev - metrics.ev,
        },
        "friction_hurdle": friction_hurdle,
        "breakevens": breakevens,
        "edge_attribution": attribution,
        "gates": gate,
    }

    j, m = write_report_json_md(paths.kb_experiments, payload)
    print(json.dumps({"json": str(j), "md": str(m), "ev": metrics.ev, "pop": metrics.pop, "pot": metrics.pot, "cvar95": metrics.cvar95, "allow_trade": gate["allow_trade"]}, indent=2))


if __name__ == "__main__":
    main()
