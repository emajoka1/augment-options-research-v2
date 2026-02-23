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
from ak_system.mc_options.calibration import defaults_from_market, fit_iv_params_from_snapshot, parse_chain_snapshot
from ak_system.mc_options.iv_dynamics import IVDynamicsParams
from ak_system.mc_options.metrics import compute_metrics, percentiles
from ak_system.mc_options.report import write_report_json_md
from ak_system.mc_options.simulator import FrictionConfig, simulate_strategy_paths
from ak_system.mc_options.strategy import ExitRules, make_iron_fly, make_long_straddle


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
    p.add_argument("--n-paths", type=int, default=1500)
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
    if args.snapshot_file:
        snap = parse_chain_snapshot(args.snapshot_file)
        spot = float(snap.spot)
        ivp = fit_iv_params_from_snapshot(spot=snap.spot, strikes=snap.strikes, ivs=snap.ivs)
    else:
        _, _, _, ivp = defaults_from_market(spot=spot, iv_atm=0.25)

    strategy = build_strategy(args.example, spot, expiry_years)
    exits = ExitRules(take_profit_pct=0.5, stop_loss_pct=1.0, dte_stop_days=0.25)
    friction = FrictionConfig(spread_bps=args.spread_bps, slippage_bps=args.slippage_bps, partial_fill_prob=args.partial_fill_prob)

    pnl, touch = simulate_strategy_paths(
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

    metrics = compute_metrics(pnl, touch)

    # sensitivity shocks
    pnl_wide, _ = simulate_strategy_paths(
        strategy=strategy,
        S0=spot,
        r=args.r,
        q=args.q,
        n_paths=max(400, args.n_paths // 2),
        n_steps=n_steps,
        dt=dt,
        iv_params=ivp,
        exit_rules=exits,
        friction=FrictionConfig(spread_bps=args.spread_bps * 1.8, slippage_bps=args.slippage_bps * 1.6, partial_fill_prob=min(0.6, args.partial_fill_prob * 1.5)),
        model=args.model,
        seed=args.seed + 99,
    )
    m_wide = compute_metrics(pnl_wide)

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
        "breakevens": [],
    }

    j, m = write_report_json_md(paths.kb_experiments, payload)
    print(json.dumps({"json": str(j), "md": str(m), "ev": metrics.ev, "pop": metrics.pop, "cvar95": metrics.cvar95}, indent=2))


if __name__ == "__main__":
    main()
