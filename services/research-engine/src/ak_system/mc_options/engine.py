from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import numpy as np

from ak_system.config import build_paths, ensure_dirs
from ak_system.mc_options.calibration import calibrate_from_snapshot, defaults_from_market, parse_chain_snapshot, realized_vol
from ak_system.mc_options.gates import compute_edge_attribution, evaluate_survival_gates
from ak_system.mc_options.metrics import compute_metrics, percentiles
from ak_system.mc_options.models import GBMParams, HestonParams, JumpDiffusionParams, simulate_gbm_paths, simulate_heston_paths, simulate_jump_diffusion_paths
from ak_system.mc_options.iv_dynamics import evolve_iv_state, surface_iv
from ak_system.mc_options.report import write_report_json_md
from ak_system.mc_options.simulator import FrictionConfig, simulate_strategy_paths
from ak_system.mc_options.strategy import (
    Leg,
    StrategyDef,
    compute_breakevens,
    default_exit_rules_for_strategy,
    make_iron_condor,
    make_iron_fly,
    make_long_straddle,
    make_put_calendar,
    make_put_debit_spread,
    make_put_diagonal,
    make_vertical,
    strategy_mid_value,
)
from ak_system.regime import classify_regime_rule_based
from ak_system.storage import persist_mc_result
from ak_system.local_artifacts import get_service_artifact_dir
import asyncio


@dataclass
class MCEngineConfig:
    symbol: str = "SPY"
    spot: float = 690.0
    r: float = 0.03
    q: float = 0.013
    expiry_days: float = 5
    n_paths: int = 5000
    n_batches: int = 20
    paths_per_batch: int = 2000
    dt_days: float = 0.25
    seed: int = 42
    model: Literal["gbm", "jump", "heston"] = "jump"
    strategy_type: str = "iron_fly"
    strategy_legs: list[dict] | None = None
    spread_bps: float = 30.0
    slippage_bps: float = 8.0
    partial_fill_prob: float = 0.1
    event_risk_high: bool = False
    snapshot_file: str | None = None
    force_refresh_minutes: float = 30.0
    force_refresh: bool = False
    dq_fail_dedupe_cooldown_minutes: float = 30.0
    rv_freshness_sla_seconds: float = 3600.0
    output_root: str | None = None
    write_artifacts: bool = True
    strategy_name: str | None = None
    entry_cost_override: float | None = None

    @property
    def example(self) -> str:
        return self.strategy_type


@dataclass
class MCEngineResult:
    payload: dict
    metrics: object
    multi_seed: dict
    gates: dict
    edge_attribution: dict
    breakevens: list[float] | None
    allow_trade: bool
    data_quality_status: str
    artifact_json: str | None = None
    artifact_md: str | None = None
    summary: dict = field(default_factory=dict)


def build_strategy(example: str, spot: float, expiry_years: float, strategy_legs: list[dict] | None = None):
    if strategy_legs:
        return StrategyDef(example, [Leg(**leg) for leg in strategy_legs], expiry_years)

    k = round(spot)
    if example == "iron_fly":
        return make_iron_fly(center=k, wing=max(2.0, round(spot * 0.01)), expiry_years=expiry_years, qty=1)
    if example == "long_straddle":
        return make_long_straddle(K=k, expiry_years=expiry_years, qty=1)
    if example == "put_debit_spread":
        return make_put_debit_spread(long_strike=k, short_strike=k - max(1.0, round(spot * 0.003)), expiry_years=expiry_years, qty=1)
    if example == "call_debit_spread":
        return make_vertical("call", long_strike=k, short_strike=k + max(1.0, round(spot * 0.003)), expiry_years=expiry_years, qty=1)
    if example == "put_credit_spread":
        return StrategyDef("put_credit_spread", [Leg("short", "put", k, 1), Leg("long", "put", k - max(1.0, round(spot * 0.003)), 1)], expiry_years)
    if example == "iron_condor":
        wing = max(2.0, round(spot * 0.008))
        return make_iron_condor(short_put=k - wing, long_put=k - (2 * wing), short_call=k + wing, long_call=k + (2 * wing), expiry_years=expiry_years, qty=1)
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


def build_provenance(config: MCEngineConfig, strategy, n_batches: int, n_paths_batch: int, n_total_paths: int) -> dict:
    base = {
        "model": config.model,
        "example": config.example,
        "spot": float(config.spot),
        "r": float(config.r),
        "q": float(config.q),
        "expiry_days": float(config.expiry_days),
        "dt_days": float(config.dt_days),
        "n_batches": int(n_batches),
        "paths_per_batch": int(n_paths_batch),
        "n_total_paths": int(n_total_paths),
        "assumptions_n_paths": int(n_total_paths),
        "seed": int(config.seed),
        "base_seed": int(config.seed),
        "crn_scope": "same_model_same_structure_friction_only",
        "strategy": strategy.name,
        "legs": [(leg.side, leg.option_type, float(leg.strike), int(leg.qty), float(leg.expiry_years or 0.0)) for leg in strategy.legs],
        "spread_bps": float(config.spread_bps),
        "slippage_bps": float(config.slippage_bps),
        "partial_fill_prob": float(config.partial_fill_prob),
        "event_risk_high": bool(config.event_risk_high),
    }
    blob = json.dumps(base, sort_keys=True, separators=(",", ":"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "n_batches": int(n_batches),
        "paths_per_batch": int(n_paths_batch),
        "n_total_paths": int(n_total_paths),
        "assumptions_n_paths": int(n_total_paths),
        "base_seed": int(config.seed),
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
    return len(errors) == 0, errors


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


def _build_canonical_inputs(config: MCEngineConfig, spot: float, strategy, friction: FrictionConfig, snapshot_fp: dict) -> dict:
    return {
        "underlying_snapshot_fingerprint": {"symbol": config.symbol, "spot": float(round(spot, 6))},
        "chain_snapshot": snapshot_fp,
        "strategy_config": {
            "model": config.model,
            "example": config.example,
            "expiry_days": float(config.expiry_days),
            "dt_days": float(config.dt_days),
            "seed": int(config.seed),
            "r": float(config.r),
            "q": float(config.q),
            "n_batches": int(max(1, config.n_batches)),
            "paths_per_batch": int(max(100, config.paths_per_batch)),
            "event_risk_high": bool(config.event_risk_high),
            "strategy_name": strategy.name,
            "legs": [(leg.side, leg.option_type, float(leg.strike), int(leg.qty), float(leg.expiry_years or 0.0)) for leg in strategy.legs],
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


class MCEngine:
    def __init__(self, deps: dict | None = None):
        self.deps = deps or {}

    def _dep(self, name: str, default):
        return self.deps.get(name, default)

    def run(self, config: MCEngineConfig) -> MCEngineResult:
        cwd = Path(config.output_root).resolve() if config.output_root else Path(".").resolve()
        build_paths_fn = self._dep("build_paths", build_paths)
        ensure_dirs_fn = self._dep("ensure_dirs", ensure_dirs)
        simulate_strategy_paths_fn = self._dep("simulate_strategy_paths", simulate_strategy_paths)
        compute_metrics_fn = self._dep("compute_metrics", compute_metrics)
        percentiles_fn = self._dep("percentiles", percentiles)
        infer_regime_distribution_fn = self._dep("infer_regime_distribution", infer_regime_distribution)
        write_report_json_md_fn = self._dep("write_report_json_md", write_report_json_md)
        compute_breakevens_fn = self._dep("compute_breakevens", compute_breakevens)
        get_artifact_base_fn = self._dep("get_artifact_base", lambda root, paths: get_service_artifact_dir(root))

        paths = build_paths_fn(cwd)
        ensure_dirs_fn(paths)

        expiry_years = config.expiry_days / 365.0
        n_steps = max(2, int(config.expiry_days / config.dt_days))
        dt = expiry_years / n_steps

        spot = config.spot
        rv10 = rv20 = None
        rv_source = None
        rv_window_bars = None
        rv_asof = None
        rv_freshness_seconds = None
        jump_used = None

        if config.snapshot_file:
            snap = parse_chain_snapshot(config.snapshot_file)
            try:
                cal = calibrate_from_snapshot(snap, dt=dt, target_expiry_days=config.expiry_days)
            except TypeError:
                cal = calibrate_from_snapshot(snap, dt=dt)
            spot, rv10, rv20, jump_used = float(snap.spot), cal.rv10, cal.rv20, cal.jump
            rv_source = "snapshot_primary" if (rv10 is not None and rv20 is not None) else None
            rv_window_bars = int(len(snap.returns)) if snap.returns is not None else None
            rv_asof = datetime.now(timezone.utc).isoformat()
            rv_freshness_seconds = 0.0
            ivp = cal.iv
        else:
            _, jump_used, _, ivp = defaults_from_market(spot=spot, iv_atm=0.25)

        rv_contract_pass = rv10 is not None and rv20 is not None
        rv_freshness_sla_seconds = max(0.0, float(config.rv_freshness_sla_seconds))
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

        strategy = build_strategy(config.example, spot, expiry_years, strategy_legs=config.strategy_legs)
        config.strategy_name = strategy.name
        exits = default_exit_rules_for_strategy(strategy.name, expiry_days=config.expiry_days)
        friction = FrictionConfig(spread_bps=config.spread_bps, slippage_bps=config.slippage_bps, partial_fill_prob=config.partial_fill_prob)

        if strategy.name in {"put_credit_spread", "iron_condor", "iron_fly"} and (rv10 is None or rv20 is None):
            jump_used = JumpDiffusionParams(
                mu=(jump_used.mu if jump_used else (config.r - config.q)),
                sigma=max((jump_used.sigma if jump_used else ivp.iv_atm), max(0.20, ivp.iv_atm)),
                jump_lambda=max((jump_used.jump_lambda if jump_used else 0.25), 0.75),
                jump_mu=min((jump_used.jump_mu if jump_used else -0.06), -0.08),
                jump_sigma=max((jump_used.jump_sigma if jump_used else 0.20), 0.25),
            )

        snapshot_fp = _snapshot_fingerprint(config.snapshot_file)
        canonical_inputs = _build_canonical_inputs(config, spot, strategy, friction, snapshot_fp)
        canonical_hash = _canonical_inputs_hash(canonical_inputs)

        artifact_base = get_artifact_base_fn(cwd, paths)
        latest_payload, latest_path = _latest_options_mc_artifact(artifact_base)
        forced_refresh = bool(config.force_refresh)
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
                if data_quality_status.startswith("DATA_QUALITY_FAIL") and not config.force_refresh:
                    dq_status_unchanged = isinstance(latest_dq_status, str) and latest_dq_status == data_quality_status
                    cooldown_elapsed = age >= timedelta(minutes=max(0.0, float(config.dq_fail_dedupe_cooldown_minutes)))
                    if dq_status_unchanged and not cooldown_elapsed:
                        payload = {
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "status": "NO_ACTION_DQ_FAIL_DUPLICATE",
                            "data_quality_status": data_quality_status,
                            "dedupe_window_seconds": int(max(0.0, float(config.dq_fail_dedupe_cooldown_minutes)) * 60),
                            "prior_artifact": {
                                "path": str(latest_path),
                                "generated_at": (latest_payload or {}).get("generated_at"),
                                "status": (latest_payload or {}).get("status"),
                                "canonical_inputs_hash": (latest_payload or {}).get("canonical_inputs_hash"),
                            },
                        }
                        return MCEngineResult(payload=payload, metrics={}, multi_seed={}, gates={}, edge_attribution={}, breakevens=None, allow_trade=False, data_quality_status=data_quality_status, summary=payload)
                    if dq_status_unchanged and cooldown_elapsed:
                        dq_fail_republished_after_cooldown = True
                        forced_refresh = True
                cadence_elapsed = age >= timedelta(minutes=max(0.0, float(config.force_refresh_minutes)))
                if cadence_elapsed:
                    forced_refresh = True
                elif not forced_refresh:
                    should_skip = True

        if should_skip and latest_path is not None:
            payload = {
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
            }
            return MCEngineResult(payload=payload, metrics={}, multi_seed={}, gates={}, edge_attribution={}, breakevens=None, allow_trade=False, data_quality_status=data_quality_status, summary=payload)

        base_seed = config.seed
        n_batches = max(1, config.n_batches)
        n_paths_batch = max(100, config.paths_per_batch)
        mid_batch = []
        real_batch = []
        stress_batch = []
        last_pnl_real = None

        for b in range(n_batches):
            seed_b = base_seed + b * 1009
            pnl_mid, pot_mid = simulate_strategy_paths_fn(strategy=strategy, S0=spot, r=config.r, q=config.q, n_paths=n_paths_batch, n_steps=n_steps, dt=dt, iv_params=ivp, exit_rules=exits, friction=FrictionConfig(spread_bps=0.0, slippage_bps=0.0, partial_fill_prob=0.0), model=config.model, seed=seed_b, event_risk_high=config.event_risk_high, jump_params=jump_used, entry_cost_override=config.entry_cost_override)
            pnl_real, pot_real = simulate_strategy_paths_fn(strategy=strategy, S0=spot, r=config.r, q=config.q, n_paths=n_paths_batch, n_steps=n_steps, dt=dt, iv_params=ivp, exit_rules=exits, friction=friction, model=config.model, seed=seed_b, event_risk_high=config.event_risk_high, jump_params=jump_used, entry_cost_override=config.entry_cost_override)
            pnl_stress, pot_stress = simulate_strategy_paths_fn(strategy=strategy, S0=spot, r=config.r, q=config.q, n_paths=n_paths_batch, n_steps=n_steps, dt=dt, iv_params=ivp, exit_rules=exits, friction=FrictionConfig(spread_bps=config.spread_bps * 1.8, slippage_bps=config.slippage_bps * 1.6, partial_fill_prob=min(0.6, config.partial_fill_prob * 1.5)), model=config.model, seed=seed_b, event_risk_high=config.event_risk_high, jump_params=jump_used, entry_cost_override=config.entry_cost_override)
            mid_batch.append(compute_metrics_fn(pnl_mid, pot_mid))
            real_batch.append(compute_metrics_fn(pnl_real, pot_real))
            stress_batch.append(compute_metrics_fn(pnl_stress, pot_stress))
            last_pnl_real = pnl_real

        metrics = real_batch[-1]
        ev_real_vals = np.array([m.ev for m in real_batch])
        pop_real_vals = np.array([m.pop for m in real_batch])
        cvar_real_vals = np.array([m.cvar95 for m in real_batch])
        ev_mid_vals = np.array([m.ev for m in mid_batch])
        ev_stress_vals = np.array([m.ev for m in stress_batch])
        cvar_stress_vals = np.array([m.cvar95 for m in stress_batch])
        n_total_paths = int(n_batches * n_paths_batch)

        z = 1.96
        n_batches_float = float(len(ev_real_vals)) if len(ev_real_vals) else 1.0
        ev_mean = float(np.mean(ev_real_vals))
        ev_std = float(np.std(ev_real_vals))
        ev_se = ev_std / np.sqrt(n_batches_float)
        pop_mean = float(np.mean(pop_real_vals))
        pop_se = float(np.sqrt(max(pop_mean * (1.0 - pop_mean), 0.0) / n_total_paths)) if n_total_paths > 0 else 0.0

        multi_seed_confidence = {
            "n_batches": int(n_batches),
            "paths_per_batch": int(n_paths_batch),
            "n_total_paths": n_total_paths,
            "ev_mean": ev_mean,
            "ev_std": ev_std,
            "ev_5th_percentile": float(np.percentile(ev_real_vals, 5)),
            "pop_mean": pop_mean,
            "cvar_mean": float(np.mean(cvar_real_vals)),
            "cvar_worst": float(np.min(cvar_stress_vals)),
            "ev_mid": float(np.mean(ev_mid_vals)),
            "ev_real": ev_mean,
            "ev_stress": float(np.mean(ev_stress_vals)),
            "confidenceIntervals": {
                "ev": {
                    "value": ev_mean,
                    "ci_low": float(ev_mean - z * ev_se),
                    "ci_high": float(ev_mean + z * ev_se),
                },
                "pop": {
                    "value": pop_mean,
                    "ci_low": float(max(0.0, pop_mean - z * pop_se)),
                    "ci_high": float(min(1.0, pop_mean + z * pop_se)),
                },
                "sampleSize": n_total_paths,
                "convergenceCheck": bool((ev_se / abs(ev_mean)) < 0.05) if ev_mean != 0 else False,
            },
        }

        entry_iv_state = evolve_iv_state(ivp, n_steps=n_steps, dt=dt, returns=np.zeros(n_steps), seed=config.seed)
        tau0 = strategy.expiry_years
        tau_by_leg0 = {idx: max((leg.expiry_years if leg.expiry_years is not None else strategy.expiry_years), 1e-6) for idx, leg in enumerate(strategy.legs)}
        iv_map_entry = {leg.strike: surface_iv(spot, leg.strike, tau_by_leg0[idx], entry_iv_state, 0, ivp) for idx, leg in enumerate(strategy.legs)}
        entry_value = float(strategy_mid_value(strategy, spot, config.r, config.q, tau0, iv_map_entry, tau_by_leg=tau_by_leg0))
        breakevens, breakeven_reason, breakeven_solver = compute_breakevens_fn(strategy, entry_value)
        breakeven_failure_code = None if breakevens is not None else f"BREAKEVEN_SOLVER_FAIL:{breakeven_reason or 'unknown'}"

        regime_probs = infer_regime_distribution_fn(config.model, spot, ivp.iv_atm, n_steps, dt, config.r, config.q, config.seed + 7)
        dominant_regime = regime_probs["dominant"]
        attribution = compute_edge_attribution(ivp, rv10, rv20, regime_probs, breakevens, spot, expiry_years)
        explainable = (attribution["signals_pass"] >= 2) if (rv_contract_pass and rv_freshness_pass and breakevens is not None) else False
        attribution["explainable"] = bool(explainable)
        attribution["explainable_reason"] = (
            "Edge is explainable: at least two independent regime/volatility signals agree with the trade thesis"
            if explainable
            else (rv_staleness_reason or breakeven_failure_code or "Insufficient independent signals to explain edge")
        )
        gates, friction_hurdle = evaluate_survival_gates(metrics, multi_seed_confidence, dominant_regime, attribution, config)
        gates["allow_trade"] = bool(
            rv_contract_pass
            and gates["ev_gate"]
            and gates["ev_ci_gate"]
            and gates["cvar_gate"]
            and gates["cvar_worst_gate"]
            and gates["pop_or_pot"]
            and gates["slippage_sensitivity_ok"]
            and gates["stress_ev_not_catastrophic"]
            and attribution["explainable"]
        )

        provenance = build_provenance(config, strategy, n_batches, n_paths_batch, n_total_paths)
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
                "model": config.model,
                "spot": spot,
                "r": config.r,
                "q": config.q,
                "expiry_years": expiry_years,
                "n_paths": n_total_paths,
                "n_batches": n_batches,
                "paths_per_batch": n_paths_batch,
                "dt": dt,
                "seed": config.seed,
                "strategy": strategy.name,
                "legs": [asdict(leg) for leg in strategy.legs],
                "snapshot_file": config.snapshot_file,
                "event_risk_high": config.event_risk_high,
            },
            "randomness_policy": {"comparison_mode": "paired", "base_seed": base_seed, "sensitivity_seed": base_seed, "crn_scope": "same_model_same_structure_friction_only", "cross_model_or_cross_structure": "unpaired_independent_seeds_required"},
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
            "stress": {"spread_bps": config.spread_bps, "slippage_bps": config.slippage_bps, "partial_fill_prob": config.partial_fill_prob},
            "metrics": metrics.__dict__,
            "multi_seed_confidence": {k: v for k, v in multi_seed_confidence.items() if k in {"n_batches", "paths_per_batch", "n_total_paths", "ev_mean", "ev_std", "ev_5th_percentile", "pop_mean", "cvar_mean", "cvar_worst"}},
            "distribution_percentiles": percentiles_fn(last_pnl_real),
            "sensitivity": {
                "wide_spread_slippage_ev": float(np.mean(ev_stress_vals)),
                "wide_spread_slippage_pop": float(np.mean([m.pop for m in stress_batch])),
                "wide_spread_slippage_cvar95": float(np.mean([m.cvar95 for m in stress_batch])),
                "ev_delta_real_to_stress": float(np.mean(ev_stress_vals) - np.mean(ev_real_vals)),
            },
            "friction_hurdle": friction_hurdle,
            "breakevens": breakevens,
            "breakeven_reason": breakeven_failure_code,
            "breakeven_solver": breakeven_solver,
            "edge_attribution": attribution,
            "gates": gates,
        }
        ok, errors = validate_provenance_payload(payload)
        if not ok:
            raise RuntimeError("options-mc provenance validation failed: " + "; ".join(errors))

        artifact_json = artifact_md = None
        summary = {
            "ev_mean": payload["multi_seed_confidence"]["ev_mean"],
            "ev_5th_percentile": payload["multi_seed_confidence"]["ev_5th_percentile"],
            "pop_mean": payload["multi_seed_confidence"]["pop_mean"],
            "cvar_mean": payload["multi_seed_confidence"]["cvar_mean"],
            "cvar_worst": payload["multi_seed_confidence"]["cvar_worst"],
            "n_total_paths": n_total_paths,
            "allow_trade": gates["allow_trade"],
            "status": payload["status"],
        }
        db_result_id = None
        try:
            db_result_id = asyncio.run(persist_mc_result(payload, asdict(config)))
        except RuntimeError:
            db_result_id = None
        except Exception:
            db_result_id = None

        if db_result_id is not None:
            payload['db_result_id'] = db_result_id
            summary = {'db_result_id': db_result_id, **summary}

        if config.write_artifacts and db_result_id is None:
            j, m = write_report_json_md_fn(artifact_base, payload)
            artifact_json, artifact_md = str(j), str(m)
            summary = {"json": artifact_json, "md": artifact_md, **summary}
        return MCEngineResult(payload=payload, metrics=metrics, multi_seed=payload["multi_seed_confidence"], gates=gates, edge_attribution=attribution, breakevens=breakevens, allow_trade=gates["allow_trade"], data_quality_status=data_quality_status, artifact_json=artifact_json, artifact_md=artifact_md, summary=summary)
