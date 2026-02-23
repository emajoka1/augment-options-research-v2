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
from ak_system.mc_options.report import write_report_json_md
from ak_system.mc_options.simulator import FrictionConfig, simulate_strategy_paths
from ak_system.mc_options.strategy import ExitRules, compute_breakevens, make_iron_fly, make_long_straddle


def build_strategy(example: str, spot: float, expiry_years: float):
    if example == "iron_fly":
        return make_iron_fly(center=round(spot), wing=max(2.0, round(spot * 0.01)), expiry_years=expiry_years, qty=1)
    if example == "long_straddle":
        return make_long_straddle(K=round(spot), expiry_years=expiry_years, qty=1)
    raise ValueError("unknown example")


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
        seed=args.seed,
    )

    metrics = compute_metrics(pnl, pot_flags)

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
        seed=args.seed,  # CRN for better comparability
    )
    m_wide = compute_metrics(pnl_wide)

    # Breakevens from structure formula using entry premium proxy (mean positive cost).
    entry_proxy = float(max(1e-6, -float(metrics.avg_loss) if metrics.avg_loss < 0 else abs(metrics.avg_win)))
    breakevens = compute_breakevens(strategy, entry_proxy)

    # survival-first gates in R-space
    R_unit = max(abs(metrics.min_pl), 1e-6)
    ev_r = metrics.ev / R_unit
    cvar_r = metrics.cvar95 / R_unit
    is_short_premium = strategy.name in {"iron_fly", "iron_condor"}

    gate = {
        "ev_gt_0.05R": ev_r > 0.05,
        "cvar95_gt_-1R": cvar_r > -1.0,
        "pop_or_pot": (metrics.pop > 0.55) if is_short_premium else (metrics.pot > 0.45),
        "slippage_sensitivity_ok": abs(m_wide.ev - metrics.ev) / R_unit < 0.35,
    }
    gate["allow_trade"] = all(gate.values())

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
