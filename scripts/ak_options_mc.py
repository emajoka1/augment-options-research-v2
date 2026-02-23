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
from ak_system.mc_options.strategy import ExitRules, compute_breakevens, make_iron_fly, make_long_straddle
from ak_system.regime import classify_regime_rule_based


def build_strategy(example: str, spot: float, expiry_years: float):
    if example == "iron_fly":
        return make_iron_fly(center=round(spot), wing=max(2.0, round(spot * 0.01)), expiry_years=expiry_years, qty=1)
    if example == "long_straddle":
        return make_long_straddle(K=round(spot), expiry_years=expiry_years, qty=1)
    raise ValueError("unknown example")


def infer_dominant_regime(model: str, spot: float, iv_atm: float, n_steps: int, dt: float, r: float, q: float, seed: int) -> str:
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
        vol_proxy = abs(ret)
        lbl = classify_regime_rule_based(p, vol_proxy, lookback=min(20, len(vol_proxy))).key
        counts[lbl] = counts.get(lbl, 0) + 1

    return max(counts.items(), key=lambda kv: kv[1])[0]


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
    p.add_argument("--example", choices=["iron_fly", "long_straddle"], default="iron_fly")
    p.add_argument("--snapshot-file", type=str, default=None, help="Path to chain snapshot JSON/CSV (spot, strike, iv)")
    p.add_argument("--spread-bps", type=float, default=30.0)
    p.add_argument("--slippage-bps", type=float, default=8.0)
    p.add_argument("--partial-fill-prob", type=float, default=0.1)
    args = p.parse_args()

    root = Path(".").resolve()
    paths = build_paths(root)
    ensure_dirs(paths)

    expiry_years = args.expiry_days / 365.0
    n_steps = max(2, int(args.expiry_days / args.dt_days))
    dt = expiry_years / n_steps

    spot = args.spot
    rv10 = None
    rv20 = None
    jump_used = None

    if args.snapshot_file:
        snap = parse_chain_snapshot(args.snapshot_file)
        cal = calibrate_from_snapshot(snap, dt=dt)
        spot = float(snap.spot)
        ivp = cal.iv
        rv10, rv20 = cal.rv10, cal.rv20
        jump_used = cal.jump
    else:
        _, jump_default, _, ivp = defaults_from_market(spot=spot, iv_atm=0.25)
        jump_used = jump_default

    strategy = build_strategy(args.example, spot, expiry_years)
    exits = ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0, dte_stop_days=0.25)
    friction = FrictionConfig(spread_bps=args.spread_bps, slippage_bps=args.slippage_bps, partial_fill_prob=args.partial_fill_prob)

    # Common random numbers by reusing same seed in scenario comparisons.
    base_seed = args.seed

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
    )

    metrics = compute_metrics(pnl, pot_flags)

    # Randomness policy:
    # - Use CRN only for same model + same structure + friction sensitivity comparison.
    # - Use independent seeds for any cross-model or cross-structure comparison.
    sensitivity_seed = base_seed  # intentional CRN for friction-only delta

    pnl_wide, _ = simulate_strategy_paths(
        strategy=strategy,
        S0=spot,
        r=args.r,
        q=args.q,
        n_paths=max(1000, args.n_paths // 2),
        n_steps=n_steps,
        dt=dt,
        iv_params=ivp,
        exit_rules=exits,
        friction=FrictionConfig(
            spread_bps=args.spread_bps * 1.8,
            slippage_bps=args.slippage_bps * 1.6,
            partial_fill_prob=min(0.6, args.partial_fill_prob * 1.5),
        ),
        model=args.model,
        seed=sensitivity_seed,  # CRN for same-model/same-structure friction comparison
    )
    m_wide = compute_metrics(pnl_wide)

    # Breakevens from structure formula using entry premium proxy (mean positive cost).
    entry_proxy = float(max(1e-6, -float(metrics.avg_loss) if metrics.avg_loss < 0 else abs(metrics.avg_win)))
    breakevens = compute_breakevens(strategy, entry_proxy)

    # regime-conditioned survival-first gates in R-space
    R_unit = max(abs(metrics.min_pl), 1e-6)
    ev_r = metrics.ev / R_unit
    cvar_r = metrics.cvar95 / R_unit
    is_short_premium = strategy.name in {"iron_fly", "iron_condor"}

    dominant_regime = infer_dominant_regime(
        model=args.model,
        spot=spot,
        iv_atm=ivp.iv_atm,
        n_steps=n_steps,
        dt=dt,
        r=args.r,
        q=args.q,
        seed=args.seed + 7,
    )

    if dominant_regime == "trend|vol_expanding":
        ev_req = 0.10
        cvar_req = -0.70
    elif dominant_regime == "mean_revert|vol_contracting":
        ev_req = 0.05
        cvar_req = -1.00
    else:
        ev_req = 0.07
        cvar_req = -0.85

    gate = {
        "regime": dominant_regime,
        "ev_threshold_R": ev_req,
        "cvar_threshold_R": cvar_req,
        "ev_gate": ev_r > ev_req,
        "cvar_gate": cvar_r > cvar_req,
        "pop_or_pot": (metrics.pop > 0.55) if is_short_premium else (metrics.pot > 0.45),
        "slippage_sensitivity_ok": abs(m_wide.ev - metrics.ev) / R_unit < 0.35,
    }
    gate["allow_trade"] = bool(gate["ev_gate"] and gate["cvar_gate"] and gate["pop_or_pot"] and gate["slippage_sensitivity_ok"])

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
        },
        "randomness_policy": {
            "base_seed": base_seed,
            "sensitivity_seed": sensitivity_seed,
            "crn_scope": "same_model_same_structure_friction_only",
            "cross_model_or_cross_structure": "independent_seeds_required"
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
            "ev_delta": m_wide.ev - metrics.ev,
        },
        "breakevens": breakevens,
        "gates": gate,
    }

    j, m = write_report_json_md(paths.kb_experiments, payload)
    print(
        json.dumps(
            {
                "json": str(j),
                "md": str(m),
                "ev": metrics.ev,
                "pop": metrics.pop,
                "pot": metrics.pot,
                "cvar95": metrics.cvar95,
                "allow_trade": gate["allow_trade"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
