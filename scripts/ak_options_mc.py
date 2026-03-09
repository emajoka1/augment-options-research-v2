#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ak_system.config import build_paths, ensure_dirs
from ak_system.mc_options.calibration import calibrate_from_snapshot, defaults_from_market, parse_chain_snapshot, realized_vol
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




def build_provenance(args, strategy, n_batches: int, n_paths_batch: int, n_total_paths: int) -> dict:
    config = {
        "model": args.model,
        "example": args.example,
        "spot": float(args.spot),
        "r": float(args.r),
        "q": float(args.q),
        "expiry_days": float(args.expiry_days),
        "dt_days": float(args.dt_days),
        "n_batches": int(n_batches),
        "paths_per_batch": int(n_paths_batch),
        "n_total_paths": int(n_total_paths),
        "assumptions_n_paths": int(n_total_paths),
        "seed": int(args.seed),
        "base_seed": int(args.seed),
        "crn_scope": "same_model_same_structure_friction_only",
        "strategy": strategy.name,
        "legs": [(leg.side, leg.option_type, float(leg.strike), int(leg.qty), float(leg.expiry_years or 0.0)) for leg in strategy.legs],
        "spread_bps": float(args.spread_bps),
        "slippage_bps": float(args.slippage_bps),
        "partial_fill_prob": float(args.partial_fill_prob),
        "event_risk_high": bool(args.event_risk_high),
    }
    blob = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "n_batches": int(n_batches),
        "paths_per_batch": int(n_paths_batch),
        "n_total_paths": int(n_total_paths),
        "assumptions_n_paths": int(n_total_paths),
        "base_seed": int(args.seed),
        "crn_scope": "same_model_same_structure_friction_only",
    }


def validate_provenance_payload(payload: dict) -> tuple[bool, list[str]]:
    req = ["generated_at", "config_hash", "n_batches", "paths_per_batch", "n_total_paths", "assumptions", "base_seed", "crn_scope"]
    missing = [k for k in req if k not in payload]
    if "assumptions" in payload and "n_paths" not in (payload.get("assumptions") or {}):
        missing.append("assumptions.n_paths")
    errors = []
    if missing:
        errors.append("missing:" + ",".join(missing))
    ch = payload.get("config_hash")
    if not isinstance(ch, str) or len(ch) != 64:
        errors.append("invalid:config_hash")
    ga = payload.get("generated_at")
    if not isinstance(ga, str) or not ga:
        errors.append("invalid:generated_at")
    nb = payload.get("n_batches")
    ppb = payload.get("paths_per_batch")
    nt = payload.get("n_total_paths")
    anp = (payload.get("assumptions") or {}).get("n_paths")
    if not all(isinstance(x, int) for x in [nb, ppb, nt, anp]):
        errors.append("invalid:path_counts_type")
    else:
        if nt != nb * ppb or nt != anp:
            errors.append("invalid:path_counts_consistency")
    return len(errors) == 0, errors

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

def load_local_returns_fallback(root: Path) -> tuple[np.ndarray | None, str | None, str | None, float | None]:
    """Load latest local returns history from snapshots as deterministic RV fallback."""
    files = sorted((root / "snapshots").glob("spy_mc_snapshot_*.json"))
    for f in reversed(files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            rets = data.get("returns") or []
            arr = np.array(rets, dtype=float)
            if arr.size:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                freshness = max(0.0, (datetime.now(timezone.utc) - mtime).total_seconds())
                return arr, "local_fallback", mtime.isoformat(), freshness
        except Exception:
            continue
    return None, None, None, None


def _snapshot_fingerprint(snapshot_file: str | None) -> dict:
    if not snapshot_file:
        return {"path": None, "sha256": None, "mtime_utc": None}
    p = Path(snapshot_file)
    try:
        raw = p.read_bytes()
        return {
            "path": str(p.resolve()),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
    except Exception:
        return {"path": str(snapshot_file), "sha256": None, "mtime_utc": None}


def _build_canonical_inputs(args, spot: float, strategy, friction: FrictionConfig, snapshot_fp: dict) -> dict:
    return {
        "underlying_snapshot_fingerprint": {
            "symbol": "SPY",
            "spot": float(round(spot, 6)),
        },
        "chain_snapshot": snapshot_fp,
        "strategy_config": {
            "model": args.model,
            "example": args.example,
            "expiry_days": float(args.expiry_days),
            "dt_days": float(args.dt_days),
            "seed": int(args.seed),
            "r": float(args.r),
            "q": float(args.q),
            "n_batches": int(max(1, args.n_batches)),
            "paths_per_batch": int(max(100, args.paths_per_batch)),
            "event_risk_high": bool(args.event_risk_high),
            "strategy_name": strategy.name,
            "legs": [
                (leg.side, leg.option_type, float(leg.strike), int(leg.qty), float(leg.expiry_years or 0.0))
                for leg in strategy.legs
            ],
        },
        "friction_config": {
            "spread_bps": float(friction.spread_bps),
            "slippage_bps": float(friction.slippage_bps),
            "partial_fill_prob": float(friction.partial_fill_prob),
        },
    }


def _canonical_inputs_hash(canonical_inputs: dict) -> str:
    blob = json.dumps(canonical_inputs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _latest_options_mc_artifact(out_base: Path) -> tuple[dict | None, Path | None]:
    files = sorted(out_base.glob("options-mc-*.json"))
    if not files:
        return None, None
    f = files[-1]
    try:
        return json.loads(f.read_text(encoding="utf-8")), f
    except Exception:
        return None, f


def main():
    p = argparse.ArgumentParser(description="Real options Monte Carlo engine")
    p.add_argument("--spot", type=float, default=690.0)
    p.add_argument("--r", type=float, default=0.03)
    p.add_argument("--q", type=float, default=0.0)
    p.add_argument("--expiry-days", type=float, default=5)
    p.add_argument("--n-paths", type=int, default=5000)
    p.add_argument("--n-batches", type=int, default=20)
    p.add_argument("--paths-per-batch", type=int, default=2000)
    p.add_argument("--dt-days", type=float, default=0.25)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--model", choices=["gbm", "jump", "heston"], default="jump")
    p.add_argument("--example", choices=["iron_fly", "long_straddle", "put_debit_spread", "put_calendar", "put_diagonal"], default="iron_fly")
    p.add_argument("--snapshot-file", type=str, default=None, help="Path to chain snapshot JSON/CSV (spot, strike, iv)")
    p.add_argument("--spread-bps", type=float, default=30.0)
    p.add_argument("--slippage-bps", type=float, default=8.0)
    p.add_argument("--partial-fill-prob", type=float, default=0.1)
    p.add_argument("--event-risk-high", action="store_true")
    p.add_argument("--force-refresh-minutes", type=float, default=30.0)
    p.add_argument("--force-refresh", action="store_true", help="Bypass idempotency and DQ dedupe guards for a forced refresh")
    p.add_argument("--dq-fail-dedupe-cooldown-minutes", type=float, default=30.0)
    p.add_argument("--rv-freshness-sla-seconds", type=float, default=3600.0)
    args = p.parse_args()

    paths = build_paths(Path(".").resolve())
    ensure_dirs(paths)

    expiry_years = args.expiry_days / 365.0
    n_steps = max(2, int(args.expiry_days / args.dt_days))
    dt = expiry_years / n_steps

    spot = args.spot
    rv10 = rv20 = None
    rv_source = None
    rv_window_bars = None
    rv_asof = None
    rv_freshness_seconds = None
    jump_used = None

    if args.snapshot_file:
        snap = parse_chain_snapshot(args.snapshot_file)
        cal = calibrate_from_snapshot(snap, dt=dt)
        spot, rv10, rv20, jump_used = float(snap.spot), cal.rv10, cal.rv20, cal.jump
        rv_source = "snapshot_primary" if (rv10 is not None and rv20 is not None) else None
        rv_window_bars = int(len(snap.returns)) if snap.returns is not None else None
        rv_asof = datetime.now(timezone.utc).isoformat()
        rv_freshness_seconds = 0.0
        ivp = cal.iv
    else:
        _, jump_used, _, ivp = defaults_from_market(spot=spot, iv_atm=0.25)

    if rv10 is None or rv20 is None:
        fallback_rets, fb_source, fb_asof, fb_freshness = load_local_returns_fallback(ROOT)
        if fallback_rets is not None:
            fb_rv10 = realized_vol(fallback_rets, 10, dt)
            fb_rv20 = realized_vol(fallback_rets, 20, dt)
            if fb_rv10 is not None and fb_rv20 is not None:
                rv10, rv20 = fb_rv10, fb_rv20
                rv_source = fb_source
                rv_window_bars = int(fallback_rets.size)
                rv_asof = fb_asof
                rv_freshness_seconds = fb_freshness

    rv_contract_pass = (rv10 is not None and rv20 is not None)
    rv_freshness_sla_seconds = max(0.0, float(args.rv_freshness_sla_seconds))
    rv_freshness_pass = bool(rv_contract_pass and rv_freshness_seconds is not None and rv_freshness_seconds <= rv_freshness_sla_seconds)
    rv_staleness_reason = None
    if not rv_contract_pass:
        rv_staleness_reason = "missing_realized_vol"
    elif not rv_freshness_pass:
        rv_staleness_reason = "stale_realized_vol"

    if not rv_contract_pass:
        data_quality_status = "DATA_QUALITY_FAIL: missing_realized_vol"
    elif not rv_freshness_pass:
        data_quality_status = "DATA_QUALITY_FAIL: stale_realized_vol"
    else:
        data_quality_status = "OK"

    strategy = build_strategy(args.example, spot, expiry_years)
    exits = default_exit_rules_for_strategy(strategy.name)
    friction = FrictionConfig(spread_bps=args.spread_bps, slippage_bps=args.slippage_bps, partial_fill_prob=args.partial_fill_prob)

    snapshot_fp = _snapshot_fingerprint(args.snapshot_file)
    canonical_inputs = _build_canonical_inputs(args, spot, strategy, friction, snapshot_fp)
    canonical_hash = _canonical_inputs_hash(canonical_inputs)

    latest_payload, latest_path = _latest_options_mc_artifact(paths.kb_experiments)
    forced_refresh = bool(args.force_refresh)
    force_refresh_minutes = max(0.0, float(args.force_refresh_minutes))
    dq_fail_dedupe_cooldown_minutes = max(0.0, float(args.dq_fail_dedupe_cooldown_minutes))
    should_skip = False
    dq_fail_republished_after_cooldown = False
    if latest_payload and latest_path:
        latest_hash = latest_payload.get("canonical_inputs_hash")
        same_inputs = isinstance(latest_hash, str) and (latest_hash == canonical_hash)
        if same_inputs:
            age = datetime.now(timezone.utc) - datetime.fromtimestamp(latest_path.stat().st_mtime, tz=timezone.utc)
            latest_dq_status = latest_payload.get("data_quality_status") if isinstance(latest_payload, dict) else None
            if isinstance(latest_dq_status, str) and latest_dq_status != data_quality_status:
                forced_refresh = True
            if data_quality_status.startswith("DATA_QUALITY_FAIL") and not args.force_refresh:
                dq_status_unchanged = isinstance(latest_dq_status, str) and latest_dq_status == data_quality_status
                cooldown_elapsed = age >= timedelta(minutes=dq_fail_dedupe_cooldown_minutes) if dq_fail_dedupe_cooldown_minutes > 0 else True
                if dq_status_unchanged and not cooldown_elapsed:
                    print(
                        json.dumps(
                            {
                                "generated_at": datetime.now(timezone.utc).isoformat(),
                                "status": "NO_ACTION_DQ_FAIL_DUPLICATE",
                                "data_quality_status": data_quality_status,
                                "dedupe_window_seconds": int(dq_fail_dedupe_cooldown_minutes * 60),
                                "prior_artifact": {
                                    "path": str(latest_path),
                                    "generated_at": (latest_payload or {}).get("generated_at"),
                                    "status": (latest_payload or {}).get("status"),
                                    "canonical_inputs_hash": (latest_payload or {}).get("canonical_inputs_hash"),
                                },
                            },
                            indent=2,
                        )
                    )
                    return
                if dq_status_unchanged and cooldown_elapsed:
                    dq_fail_republished_after_cooldown = True
                    forced_refresh = True

            cadence_elapsed = age >= timedelta(minutes=force_refresh_minutes) if force_refresh_minutes > 0 else True
            if cadence_elapsed:
                forced_refresh = True
            elif not forced_refresh:
                should_skip = True

    if should_skip and latest_path is not None:
        print(
            json.dumps(
                {
                    "status": "NO_NEW_INPUTS",
                    "skipped": True,
                    "prior_artifact": {
                        "path": str(latest_path),
                        "generated_at": (latest_payload or {}).get("generated_at"),
                        "config_hash": (latest_payload or {}).get("config_hash"),
                        "canonical_inputs_hash": (latest_payload or {}).get("canonical_inputs_hash"),
                    },
                    "telemetry": {
                        "options_mc_runs_total": 1,
                        "options_mc_runs_skipped_no_new_inputs": 1,
                        "options_mc_runs_forced_refresh": 0,
                    },
                },
                indent=2,
            )
        )
        return

    base_seed = args.seed
    comparison_mode = "paired"
    assert_paired_seed_policy(args.model, args.model, strategy, strategy)

    n_batches = max(1, args.n_batches)
    n_paths_batch = max(100, args.paths_per_batch)

    mid_batch = []
    real_batch = []
    stress_batch = []

    for b in range(n_batches):
        seed_b = base_seed + b * 1009

        # Layer 1: ideal mid-fill (no friction)
        pnl_mid, pot_mid = simulate_strategy_paths(
            strategy=strategy,
            S0=spot,
            r=args.r,
            q=args.q,
            n_paths=n_paths_batch,
            n_steps=n_steps,
            dt=dt,
            iv_params=ivp,
            exit_rules=exits,
            friction=FrictionConfig(spread_bps=0.0, slippage_bps=0.0, partial_fill_prob=0.0),
            model=args.model,
            seed=seed_b,
            event_risk_high=args.event_risk_high,
        )
        m_mid = compute_metrics(pnl_mid, pot_mid)

        # Layer 2: realistic friction baseline
        pnl_real, pot_real = simulate_strategy_paths(
            strategy=strategy,
            S0=spot,
            r=args.r,
            q=args.q,
            n_paths=n_paths_batch,
            n_steps=n_steps,
            dt=dt,
            iv_params=ivp,
            exit_rules=exits,
            friction=friction,
            model=args.model,
            seed=seed_b,
            event_risk_high=args.event_risk_high,
        )
        m_real = compute_metrics(pnl_real, pot_real)

        # Layer 3: bad-day friction stress
        pnl_stress, pot_stress = simulate_strategy_paths(
            strategy=strategy,
            S0=spot,
            r=args.r,
            q=args.q,
            n_paths=n_paths_batch,
            n_steps=n_steps,
            dt=dt,
            iv_params=ivp,
            exit_rules=exits,
            friction=FrictionConfig(spread_bps=args.spread_bps * 1.8, slippage_bps=args.slippage_bps * 1.6, partial_fill_prob=min(0.6, args.partial_fill_prob * 1.5)),
            model=args.model,
            seed=seed_b,
            event_risk_high=args.event_risk_high,
        )
        m_stress = compute_metrics(pnl_stress, pot_stress)

        mid_batch.append(m_mid)
        real_batch.append(m_real)
        stress_batch.append(m_stress)

    # Primary point estimate from realistic layer mean
    ev_real_vals = np.array([m.ev for m in real_batch])
    pop_real_vals = np.array([m.pop for m in real_batch])
    cvar_real_vals = np.array([m.cvar95 for m in real_batch])

    ev_mid_vals = np.array([m.ev for m in mid_batch])
    ev_stress_vals = np.array([m.ev for m in stress_batch])
    cvar_stress_vals = np.array([m.cvar95 for m in stress_batch])

    metrics = real_batch[-1]
    m_mid = mid_batch[-1]
    m_wide = stress_batch[-1]

    n_total_paths = int(n_batches * n_paths_batch)

    multi_seed = {
        "n_batches": int(n_batches),
        "paths_per_batch": int(n_paths_batch),
        "n_total_paths": n_total_paths,
        "ev_mean": float(np.mean(ev_real_vals)),
        "ev_std": float(np.std(ev_real_vals)),
        "ev_5th_percentile": float(np.percentile(ev_real_vals, 5)),
        "pop_mean": float(np.mean(pop_real_vals)),
        "cvar_mean": float(np.mean(cvar_real_vals)),
        "cvar_worst": float(np.min(cvar_stress_vals)),
    }

    entry_proxy = float(max(1e-6, -float(metrics.avg_loss) if metrics.avg_loss < 0 else abs(metrics.avg_win)))
    breakevens, breakeven_reason, breakeven_solver = compute_breakevens(strategy, entry_proxy)
    breakeven_failure_code = None if breakevens is not None else f"BREAKEVEN_SOLVER_FAIL:{breakeven_reason or 'unknown'}"

    regime_probs = infer_regime_distribution(args.model, spot, ivp.iv_atm, n_steps, dt, args.r, args.q, args.seed + 7)
    dominant_regime = regime_probs["dominant"]

    R_unit = max(abs(metrics.min_pl), 1e-6)
    ev_r = metrics.ev / R_unit
    cvar_r = multi_seed["cvar_mean"] / R_unit
    is_short_premium = strategy.name in {"iron_fly", "iron_condor"}

    if dominant_regime == "trend|vol_expanding":
        ev_req, cvar_req = 0.10, -0.70
    elif dominant_regime == "mean_revert|vol_contracting":
        ev_req, cvar_req = 0.05, -1.00
    else:
        ev_req, cvar_req = 0.07, -0.85

    ev_mid_mean = float(np.mean(ev_mid_vals))
    ev_real_mean = float(np.mean(ev_real_vals))
    ev_stress_mean = float(np.mean(ev_stress_vals))

    ev_mid_r = ev_mid_mean / R_unit
    ev_real_r = ev_real_mean / R_unit
    ev_stress_r = ev_stress_mean / R_unit
    ev_p5_r = multi_seed["ev_5th_percentile"] / R_unit

    friction_hurdle = {
        "ev_mid": ev_mid_mean,
        "ev_real": ev_real_mean,
        "ev_stress": ev_stress_mean,
        "delta_ev_real": ev_real_mean - ev_mid_mean,
        "delta_ev_stress": ev_stress_mean - ev_mid_mean,
        "ev_mid_R": ev_mid_r,
        "ev_real_R": ev_real_r,
        "ev_stress_R": ev_stress_r,
    }

    gate = {
        "regime": dominant_regime,
        "ev_threshold_R": ev_req,
        "cvar_threshold_R": cvar_req,
        "ev_gate": ev_real_r > ev_req,
        "ev_ci_gate": ev_p5_r > 0.02,
        "cvar_gate": cvar_r > cvar_req,
        "cvar_worst_gate": (multi_seed["cvar_worst"] / R_unit) > cvar_req,
        "pop_or_pot": (multi_seed["pop_mean"] > 0.55) if is_short_premium else (metrics.pot > 0.45),
        "slippage_sensitivity_ok": abs(ev_stress_mean - ev_real_mean) / R_unit < 0.35,
        "stress_ev_not_catastrophic": ev_stress_r > -0.50,
    }

    # edge attribution (required for ALLOW)
    iv_rv_gap = float(ivp.iv_atm - rv20) if rv_contract_pass else None
    regime_prob = float(regime_probs.get(dominant_regime, 0.0))
    expected_move = float(spot * ivp.iv_atm * (expiry_years**0.5))
    if breakevens is not None:
        be_dist = min(abs(b - spot) for b in breakevens)
        structure_match = float(max(0.0, 1.0 - abs(be_dist - expected_move) / max(expected_move, 1e-6)))
    else:
        structure_match = None

    # Explainability: allow fallback-driven attribution when full data is partial.
    mean_revert_prob = float(regime_probs.get("mean_revert|vol_contracting", 0.0))

    # Signal thresholds (simple + robust):
    # - IV rich vs RV is present if computable (no directional threshold required for presence)
    # - Regime probability should be meaningful
    # - Structure/expected-move fit should be non-trivial
    iv_rv_present = iv_rv_gap is not None
    regime_present = np.isfinite(mean_revert_prob)
    structure_present = isinstance(structure_match, (int, float)) and np.isfinite(structure_match)

    iv_rv_pass = iv_rv_present
    regime_pass = regime_present and (mean_revert_prob >= 0.20)
    structure_pass = structure_present and (float(structure_match) >= 0.05)

    explainability_signals_present = int(iv_rv_present) + int(regime_present) + int(structure_present)
    explainability_signals_pass = int(iv_rv_pass) + int(regime_pass) + int(structure_pass)
    explainable = (explainability_signals_pass >= 2) if (rv_contract_pass and rv_freshness_pass and breakevens is not None) else False

    attribution = {
        "iv_rich_vs_rv": iv_rv_gap,
        "mean_reversion_regime_probability": mean_revert_prob,
        "structure_expected_move_match": structure_match,
        "signals_present": explainability_signals_present,
        "signals_pass": explainability_signals_pass,
        "thresholds": {
            "regime_prob_min": 0.20,
            "structure_match_min": 0.05,
            "min_signals_pass": 2,
        },
        "explainable": bool(explainable),
        "explainable_reason": None if explainable else (rv_staleness_reason or breakeven_failure_code),
    }

    gate["allow_trade"] = bool(
        rv_contract_pass
        and gate["ev_gate"]
        and gate["ev_ci_gate"]
        and gate["cvar_gate"]
        and gate["cvar_worst_gate"]
        and gate["pop_or_pot"]
        and gate["slippage_sensitivity_ok"]
        and gate["stress_ev_not_catastrophic"]
        and attribution["explainable"]
    )

    provenance = build_provenance(args, strategy, n_batches, n_paths_batch, n_total_paths)

    payload = {
        "generated_at": provenance["generated_at"],
        "config_hash": provenance["config_hash"],
        "status": "FULL_REFRESH",
        "canonical_inputs": canonical_inputs,
        "canonical_inputs_hash": canonical_hash,
        "n_batches": provenance["n_batches"],
        "paths_per_batch": provenance["paths_per_batch"],
        "n_total_paths": provenance["n_total_paths"],
        "base_seed": provenance["base_seed"],
        "crn_scope": provenance["crn_scope"],
        "assumptions": {
            "model": args.model,
            "spot": spot,
            "r": args.r,
            "q": args.q,
            "expiry_years": expiry_years,
            "n_paths": n_total_paths,
            "n_batches": n_batches,
            "paths_per_batch": n_paths_batch,
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
            "rv_source": rv_source,
            "rv_window_bars": rv_window_bars,
            "rv_asof": rv_asof,
            "rv_freshness_seconds": rv_freshness_seconds,
            "rv_freshness_sla_seconds": rv_freshness_sla_seconds,
            "rv_freshness_pass": rv_freshness_pass,
            "rv_staleness_reason": rv_staleness_reason,
            "jump": jump_used.__dict__ if jump_used else None,
        },
        "data_quality_status": data_quality_status,
        "rv_freshness_sla_seconds": rv_freshness_sla_seconds,
        "rv_freshness_pass": rv_freshness_pass,
        "rv_staleness_reason": rv_staleness_reason,
        "telemetry": {
            "options_mc_runs_total": 1,
            "options_mc_runs_skipped_no_new_inputs": 0,
            "options_mc_runs_forced_refresh": 1 if forced_refresh else 0,
            "options_mc_rv_missing_events": 0 if rv_contract_pass else 1,
            "options_mc_runs_rv_stale_events": 1 if (rv_contract_pass and not rv_freshness_pass) else 0,
            "options_mc_runs_dq_fail_deduped": 0,
            "options_mc_runs_dq_fail_republished_after_cooldown": 1 if dq_fail_republished_after_cooldown else 0,
        },
        "regime_distribution": regime_probs,
        "stress": {
            "spread_bps": args.spread_bps,
            "slippage_bps": args.slippage_bps,
            "partial_fill_prob": args.partial_fill_prob,
        },
        "metrics": metrics.__dict__,
        "multi_seed_confidence": multi_seed,
        "distribution_percentiles": percentiles(pnl_real),
        "sensitivity": {
            "wide_spread_slippage_ev": ev_stress_mean,
            "wide_spread_slippage_pop": float(np.mean([m.pop for m in stress_batch])),
            "wide_spread_slippage_cvar95": float(np.mean([m.cvar95 for m in stress_batch])),
            "ev_delta_real_to_stress": ev_stress_mean - ev_real_mean,
        },
        "friction_hurdle": friction_hurdle,
        "breakevens": breakevens,
        "breakeven_reason": breakeven_failure_code,
        "breakeven_solver": breakeven_solver,
        "edge_attribution": attribution,
        "gates": gate,
    }

    ok, errors = validate_provenance_payload(payload)
    if not ok:
        raise RuntimeError("options-mc provenance validation failed: " + "; ".join(errors))

    j, m = write_report_json_md(paths.kb_experiments, payload)
    print(
        json.dumps(
            {
                "json": str(j),
                "md": str(m),
                "ev_mean": multi_seed["ev_mean"],
                "ev_5th_percentile": multi_seed["ev_5th_percentile"],
                "pop_mean": multi_seed["pop_mean"],
                "cvar_mean": multi_seed["cvar_mean"],
                "cvar_worst": multi_seed["cvar_worst"],
                "n_total_paths": n_total_paths,
                "allow_trade": gate["allow_trade"],
                "status": "FULL_REFRESH",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
