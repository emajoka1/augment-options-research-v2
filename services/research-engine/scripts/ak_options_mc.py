#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ak_system.config import build_paths, ensure_dirs
from ak_system.mc_options.engine import (
    MCEngine,
    MCEngineConfig,
    build_provenance,
    build_strategy,
    infer_regime_distribution,
    load_local_returns_fallback,
    validate_provenance_payload,
)
from ak_system.mc_options.metrics import compute_metrics, percentiles
from ak_system.mc_options.report import write_report_json_md
from ak_system.mc_options.simulator import simulate_strategy_paths
from ak_system.mc_options.strategy import compute_breakevens




def _artifact_base(root: Path, paths):
    return getattr(paths, 'kb_experiments')

__all__ = [
    "MCEngine",
    "MCEngineConfig",
    "build_paths",
    "ensure_dirs",
    "build_provenance",
    "build_strategy",
    "infer_regime_distribution",
    "load_local_returns_fallback",
    "validate_provenance_payload",
    "compute_metrics",
    "percentiles",
    "simulate_strategy_paths",
    "write_report_json_md",
    "compute_breakevens",
    "main",
]


def parse_args() -> MCEngineConfig:
    p = argparse.ArgumentParser(description="Real options Monte Carlo engine")
    p.add_argument("--spot", type=float, default=690.0)
    p.add_argument("--r", type=float, default=0.03)
    p.add_argument("--q", type=float, default=0.013)
    p.add_argument("--expiry-days", type=float, default=5)
    p.add_argument("--n-paths", type=int, default=5000)
    p.add_argument("--n-batches", type=int, default=20)
    p.add_argument("--paths-per-batch", type=int, default=2000)
    p.add_argument("--dt-days", type=float, default=0.25)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--model", choices=["gbm", "jump", "heston"], default="jump")
    p.add_argument("--example", choices=["iron_fly", "long_straddle", "put_debit_spread", "put_calendar", "put_diagonal"], default="iron_fly")
    p.add_argument("--snapshot-file", type=str, default=None)
    p.add_argument("--spread-bps", type=float, default=30.0)
    p.add_argument("--slippage-bps", type=float, default=8.0)
    p.add_argument("--partial-fill-prob", type=float, default=0.1)
    p.add_argument("--event-risk-high", action="store_true")
    p.add_argument("--force-refresh-minutes", type=float, default=30.0)
    p.add_argument("--force-refresh", action="store_true")
    p.add_argument("--dq-fail-dedupe-cooldown-minutes", type=float, default=30.0)
    p.add_argument("--rv-freshness-sla-seconds", type=float, default=3600.0)
    p.add_argument("--allow-local-rv-fallback", dest="allow_local_rv_fallback", action="store_true")
    p.add_argument("--no-allow-local-rv-fallback", dest="allow_local_rv_fallback", action="store_false")
    p.set_defaults(allow_local_rv_fallback=True)
    args = p.parse_args()
    return MCEngineConfig(
        spot=args.spot,
        r=args.r,
        q=args.q,
        expiry_days=args.expiry_days,
        n_paths=args.n_paths,
        n_batches=args.n_batches,
        paths_per_batch=args.paths_per_batch,
        dt_days=args.dt_days,
        seed=args.seed,
        model=args.model,
        strategy_type=args.example,
        snapshot_file=args.snapshot_file,
        spread_bps=args.spread_bps,
        slippage_bps=args.slippage_bps,
        partial_fill_prob=args.partial_fill_prob,
        event_risk_high=args.event_risk_high,
        force_refresh_minutes=args.force_refresh_minutes,
        force_refresh=args.force_refresh,
        dq_fail_dedupe_cooldown_minutes=args.dq_fail_dedupe_cooldown_minutes,
        rv_freshness_sla_seconds=args.rv_freshness_sla_seconds,
        allow_local_rv_fallback=args.allow_local_rv_fallback,
        output_root=str(Path(".").resolve()),
        write_artifacts=True,
    )


def main() -> None:
    deps = {
        "build_paths": build_paths,
        "ensure_dirs": ensure_dirs,
        "simulate_strategy_paths": simulate_strategy_paths,
        "compute_metrics": compute_metrics,
        "percentiles": percentiles,
        "infer_regime_distribution": infer_regime_distribution,
        "load_local_returns_fallback": load_local_returns_fallback,
        "write_report_json_md": write_report_json_md,
        "compute_breakevens": compute_breakevens,
        "get_artifact_base": _artifact_base,
    }
    result = MCEngine(deps=deps).run(parse_args())
    print(json.dumps(result.summary, indent=2))


if __name__ == "__main__":
    main()
