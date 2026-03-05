#!/usr/bin/env python3
"""MC command handler for consistent SPY brief output.

- Runs live snapshot + brief generator
- Retries when data is PARTIAL_DATA
- Produces normalized action state: NO_TRADE | WATCH | TRADE_READY
- Appends run telemetry to snapshots/mc_runs.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from urllib.request import Request, urlopen
from typing import Tuple
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "snapshots" / "mc_runs.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout


def _http_json(url: str) -> Dict[str, Any]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def get_cboe_spot_mid(symbol: str = "SPY") -> Optional[float]:
    try:
        d = _http_json(f"https://cdn.cboe.com/api/global/delayed_quotes/quotes/{symbol}.json")
        q = d.get("data", {})
        b, a = q.get("bid"), q.get("ask")
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) and b > 0 and a > 0:
            return (float(b) + float(a)) / 2.0
        lp = q.get("last_trade_price") or q.get("last")
        if isinstance(lp, (int, float)):
            return float(lp)
    except Exception:
        return None
    return None


def _extract_json_blob(text: str) -> Dict[str, Any]:
    # Supports tools that may print extra lines before/after JSON.
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found in command output")
    return json.loads(text[start : end + 1])


def run_live_snapshot(skip_live: bool) -> Optional[Dict[str, Any]]:
    if skip_live:
        return None
    out = _run(["node", "scripts/spy_live_snapshot.cjs"])
    return _extract_json_blob(out)


def run_brief() -> Dict[str, Any]:
    out = _run(["python3", "scripts/spy_free_brief.py"])
    return _extract_json_blob(out)


def generate_options_mc_for_run(spot: Optional[float]) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Generate a fresh options-MC artifact for THIS run and return payload + path."""
    py = ROOT / ".venv" / "bin" / "python"
    py_bin = str(py) if py.exists() else "python3"
    s = float(spot) if isinstance(spot, (int, float)) else (get_cboe_spot_mid("SPY") or 685.0)
    cmd = [
        py_bin,
        "scripts/ak_options_mc.py",
        "--model",
        "jump",
        "--example",
        "put_diagonal",
        "--spot",
        str(round(float(s), 3)),
        "--expiry-days",
        "7",
        "--n-batches",
        "10",
        "--paths-per-batch",
        "500",
        "--seed",
        "3019",
    ]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        return None, None
    try:
        out = json.loads(p.stdout)
        src = out.get("json")
        if not src:
            return None, None
        return json.loads(Path(src).read_text()), str(src)
    except Exception:
        return None, None


def latest_options_mc(max_age_minutes: int = 120) -> tuple[Optional[Dict[str, Any]], Optional[str], bool]:
    files = sorted((ROOT / "kb" / "experiments").glob("options-mc-*.json"))
    if not files:
        return None, None, True
    f = files[-1]
    src = str(f)
    stale = False
    try:
        age_sec = (datetime.now(timezone.utc).timestamp() - f.stat().st_mtime)
        stale = age_sec > (max_age_minutes * 60)
    except Exception:
        stale = True
    try:
        return json.loads(f.read_text()), src, stale
    except Exception:
        return None, src, stale


def _derive_structural_r(mc: Dict[str, Any]) -> tuple[Optional[float], str]:
    """Derive a stable, structure-based risk unit (R).

    Priority:
    1) Defined-risk width from strikes (verticals/condors/flies)
    2) Single-leg premium proxy from breakeven distance
    3) Fallback to abs(min_pl) (debug legacy only)
    """
    assumptions = mc.get("assumptions") or {}
    legs = assumptions.get("legs") or []

    # 1) Width-based R for defined-risk multi-leg structures.
    calls = sorted([float(l.get("strike")) for l in legs if (l.get("option_type") == "call" and l.get("strike") is not None)])
    puts = sorted([float(l.get("strike")) for l in legs if (l.get("option_type") == "put" and l.get("strike") is not None)])

    widths = []
    if len(calls) >= 2:
        widths.append(abs(calls[-1] - calls[0]))
    if len(puts) >= 2:
        widths.append(abs(puts[-1] - puts[0]))
    if widths:
        r = max(widths)
        if r > 0:
            return r, "defined_risk_width"

    # 2) Single-leg premium proxy from breakeven distance.
    if len(legs) == 1:
        leg = legs[0]
        strike = leg.get("strike")
        bes = mc.get("breakevens") or []
        if strike is not None and bes:
            try:
                strike_f = float(strike)
                be_dist = min(abs(float(be) - strike_f) for be in bes)
                if be_dist > 0:
                    return be_dist, "single_leg_breakeven_premium_proxy"
            except Exception:
                pass

    # 3) Legacy fallback (stochastic; keep only as a backup).
    metrics = mc.get("metrics") or {}
    try:
        r = abs(float(metrics.get("min_pl", 0.0)))
        if r > 0:
            return r, "fallback_abs_min_pl"
    except Exception:
        pass

    return None, "unavailable"


def load_allocation_state() -> Dict[str, Any]:
    p = ROOT / "snapshots" / "steady_state.json"
    if not p.exists():
        return {"trades_today": 0, "trades_week": 0, "day_pnl_r": 0.0, "correlated_exposure_pct": 0.0}
    try:
        d = json.loads(p.read_text())
        return {
            "trades_today": int(d.get("trades_today", 0)),
            "trades_week": int(d.get("trades_week", 0)),
            "day_pnl_r": float(d.get("day_pnl_r", 0.0)),
            "correlated_exposure_pct": float(d.get("correlated_exposure_pct", 0.0)),
        }
    except Exception:
        return {"trades_today": 0, "trades_week": 0, "day_pnl_r": 0.0, "correlated_exposure_pct": 0.0}


def run_steady_gate(payload: Dict[str, Any]) -> Dict[str, Any]:
    cmd = ["python3", "scripts/steady_compounder_gate.py"]
    p = subprocess.run(cmd, cwd=ROOT, input=json.dumps(payload), capture_output=True, text=True)
    if p.returncode != 0:
        return {"decision": "PASS", "approved": False, "reasons": ["steady_gate_exec_failed"]}
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"decision": "PASS", "approved": False, "reasons": ["steady_gate_parse_failed"]}


def normalize(live: Optional[Dict[str, Any]], brief: Dict[str, Any]) -> Dict[str, Any]:
    tb = brief.get("TRADE BRIEF", {})
    brief_meta = brief.get("brief_meta") or {}
    mc_id = f"mc_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    snapshot_id = ((live or {}).get("snapshotId") or (live or {}).get("snapshot_id")) if isinstance(live, dict) else None
    brief_id = brief_meta.get("brief_id")
    final_decision = tb.get("Final Decision", "NO TRADE")
    missing_required = tb.get("missingRequiredData", []) or []
    candidates = tb.get("Candidates", []) or []
    top = candidates[0] if candidates else {}

    symbols_with_data = None
    dxlink_partial = False
    if live is not None:
        symbols_with_data = live.get("symbolsWithData")
        dxlink_partial = not bool(symbols_with_data)

    iv_current = ((tb.get("Volatility State") or {}).get("ivCurrent"))
    if live is not None and symbols_with_data and symbols_with_data > 0:
        data_source = "dxlink-live"
    elif iv_current is not None:
        data_source = "cboe-delayed-public"
    else:
        data_source = "unknown"

    if data_source == "dxlink-live":
        data_status = "OK"
    elif data_source == "cboe-delayed-public":
        data_status = "OK_FALLBACK"
    elif dxlink_partial:
        data_status = "PARTIAL_DATA"
    else:
        data_status = "UNKNOWN"

    # Additional TRADE_READY gates from run-local options MC artifact (single-source-of-truth).
    mc, mc_source_file = generate_options_mc_for_run(tb.get("Spot"))
    mc_source_stale = False
    if mc is None:
        # Fallback only if generation fails.
        mc, mc_source_file, mc_source_stale = latest_options_mc()
    mc = mc or {}
    ms = mc.get("multi_seed_confidence") or {}
    edge = mc.get("edge_attribution") or {}
    fh = mc.get("friction_hurdle") or {}
    assumptions = mc.get("assumptions") or {}
    randomness = mc.get("randomness_policy") or {}
    n_batches = ms.get("n_batches")
    paths_per_batch = ms.get("paths_per_batch")
    n_total_paths = ms.get("n_total_paths")
    assumptions_n_paths = assumptions.get("n_paths")
    computed_n_total_paths = None
    if isinstance(n_batches, int) and isinstance(paths_per_batch, int):
        computed_n_total_paths = int(n_batches * paths_per_batch)

    counts_consistent = (
        computed_n_total_paths is not None
        and isinstance(n_total_paths, int)
        and isinstance(assumptions_n_paths, int)
        and n_total_paths == computed_n_total_paths == assumptions_n_paths
    )

    mc_provenance = {
        "options_mc_source_mode": "run_local_fresh" if mc_source_stale is False else "fallback_latest",
        "options_mc_source_file": mc_source_file,
        "generated_at": mc.get("generated_at"),
        "model": assumptions.get("model"),
        "n_batches": n_batches,
        "paths_per_batch": paths_per_batch,
        "n_total_paths": n_total_paths,
        "computed_n_total_paths": computed_n_total_paths,
        "assumptions_n_paths": assumptions_n_paths,
        "counts_consistent": counts_consistent,
        "source_stale": mc_source_stale,
        "base_seed": randomness.get("base_seed"),
        "crn_scope": randomness.get("crn_scope"),
    }

    ev_seed_p5_r = None
    ev_seed_p5_min_batches = 5
    ev_mean_r = None
    ev_stress_mean_r = None
    pl_p5_r = None
    pl_p5_threshold_r = -0.50
    cvar_worst_r = None
    delta_ev_stress_mean_r = None
    mc_rule_failures = []

    r_unit = None
    r_unit_source = "unavailable"
    r_minpl_debug = None
    try:
        ev_seed_p5_raw = ms.get("ev_5th_percentile")
        cvar_worst = ms.get("cvar_worst")
        n_batches = ms.get("n_batches")
        r_unit, r_unit_source = _derive_structural_r(mc)
        if r_unit is not None:
            r_unit = max(float(r_unit), 1e-6)

        metrics = mc.get("metrics") or {}
        if isinstance(metrics.get("min_pl"), (int, float)):
            r_minpl_debug = abs(float(metrics.get("min_pl")))

        if isinstance(ev_seed_p5_raw, (int, float)) and isinstance(n_batches, int) and n_batches >= ev_seed_p5_min_batches and r_unit:
            ev_seed_p5_r = float(ev_seed_p5_raw) / r_unit
        if isinstance(cvar_worst, (int, float)) and r_unit:
            cvar_worst_r = float(cvar_worst) / r_unit

        # Pathwise tail metric (distribution of per-path outcomes).
        dp = mc.get("distribution_percentiles") or {}
        if isinstance(dp.get("p5"), (int, float)) and r_unit:
            pl_p5_r = float(dp.get("p5")) / r_unit

        # Stress gate MUST use mean EVs, normalized by structural R.
        ev_real_mean = fh.get("ev_real")
        ev_stress_mean = fh.get("ev_stress")
        if isinstance(ev_real_mean, (int, float)) and r_unit:
            ev_mean_r = float(ev_real_mean) / r_unit
        if isinstance(ev_stress_mean, (int, float)) and r_unit:
            ev_stress_mean_r = float(ev_stress_mean) / r_unit
        if isinstance(ev_real_mean, (int, float)) and isinstance(ev_stress_mean, (int, float)) and r_unit:
            delta_ev_stress_mean_r = (float(ev_stress_mean) - float(ev_real_mean)) / r_unit
    except Exception:
        pass

    mc_ready = True
    if pl_p5_r is None or pl_p5_r <= pl_p5_threshold_r:
        mc_ready = False
        mc_rule_failures.append("pl_p5_not_above_threshold")
    if cvar_worst_r is None or cvar_worst_r <= -1.0:
        mc_ready = False
        mc_rule_failures.append("cvar_worst_not_above_-1R")
    if delta_ev_stress_mean_r is None or delta_ev_stress_mean_r < -0.05:
        mc_ready = False
        mc_rule_failures.append("stress_delta_ev_mean_below_-0.05R")

    # Explainability gate is data-tier aware (avoid penalizing fallback feeds as if they were full live).
    signals_pass = edge.get("signals_pass")
    strong_tail = isinstance(pl_p5_r, (int, float)) and pl_p5_r > -0.35
    if data_status == "OK":
        explainability_ok = (edge.get("explainable") is True) and (isinstance(signals_pass, int) and signals_pass >= 2)
    elif data_status == "OK_FALLBACK":
        explainability_ok = (isinstance(signals_pass, int) and signals_pass >= 1) or strong_tail
    else:
        explainability_ok = False

    if not explainability_ok:
        mc_ready = False
        mc_rule_failures.append("edge_not_explainable_tiered")

    if mc_provenance.get("counts_consistent") is not True:
        mc_ready = False
        mc_rule_failures.append("path_count_mismatch")
    if mc_provenance.get("source_stale") is True:
        mc_ready = False
        mc_rule_failures.append("options_mc_source_stale")

    # Spot integrity guard: compare pipeline spot to fresh CBOE quote mid.
    spot_integrity = {"ref_source": "cboe_quote_mid", "ref_spot": None, "delta": None, "max_delta": 0.5, "ok": None}
    ref_spot = get_cboe_spot_mid("SPY")
    pipe_spot = tb.get("Spot")
    if isinstance(ref_spot, (int, float)) and isinstance(pipe_spot, (int, float)):
        delta = abs(float(pipe_spot) - float(ref_spot))
        spot_integrity.update({"ref_spot": float(ref_spot), "delta": delta, "ok": delta <= 0.5})
        if delta > 0.5:
            mc_ready = False
            mc_rule_failures.append("spot_integrity_mismatch")

    # Enforce steady-compounder hierarchy gate (fail-closed).
    top_score = (top.get("score") or 0.0)
    try:
        structural_quality = max(0.0, min(1.0, float(top_score) / 100.0))
    except Exception:
        structural_quality = 0.0

    steady_payload = {
        "structure": {
            "quality": structural_quality,
            "structural_r_clean": r_unit is not None,
            "invalidation_1r": bool(top.get("type")),
        },
        "mc": {
            "ev_seed_p5_r": ev_seed_p5_r,
            "pl_p5_r": pl_p5_r,
            "cvar95_r": cvar_worst_r,
            "stress_delta_ev_r": delta_ev_stress_mean_r,
            "explainable": explainability_ok,
        },
        "regime": {
            "bucket": "hostile" if str((tb.get("Regime") or {}).get("riskState", "")).lower() == "risk-off" else "neutral",
            "extreme_vol": str(((tb.get("Volatility State") or {}).get("classifier") or {}).get("regime", "")).upper() == "EXTREME_VOL",
            "short_premium": bool(top.get("type") in {"credit", "condor", "iron_condor", "iron_fly"}),
        },
        "allocation": load_allocation_state(),
    }
    steady_gate = run_steady_gate(steady_payload)
    steady_ok = bool(steady_gate.get("approved"))

    # Action state contract (fail-closed on missing/partial data) while preserving
    # MC/steady diagnostics separately in trade_ready_rule.
    if data_status == "PARTIAL_DATA" or missing_required:
        action_state = "NO_TRADE"
    elif final_decision == "TRADE":
        action_state = "TRADE_READY"
    else:
        action_state = "WATCH"

    return {
        "timestamp": _now_iso(),
        "trace_ids": {
            "snapshot_id": snapshot_id,
            "brief_id": brief_id,
            "mc_id": mc_id,
        },
        "data_status": data_status,
        "symbols_with_data": symbols_with_data,
        "data_source": data_source,
        "spot": tb.get("Spot"),
        "regime": (tb.get("Regime") or {}).get("riskState"),
        "trend": (tb.get("Regime") or {}).get("trend"),
        "vix_direction": (tb.get("Regime") or {}).get("vixDirection"),
        "rates_direction": (tb.get("Regime") or {}).get("ratesDirection"),
        "final_decision": final_decision,
        "action_state": action_state,
        "missing_required": missing_required,
        "trade_ready_rule": {
            "r_structural": r_unit,
            "r_structural_source": r_unit_source,
            "r_minpl_debug": r_minpl_debug,
            "ev_mean_R": ev_mean_r,
            "ev_seed_p5_R": ev_seed_p5_r,
            "ev_seed_p5_min_batches": ev_seed_p5_min_batches,
            "ev_stress_mean_R": ev_stress_mean_r,
            "pl_p5_R": pl_p5_r,
            "pl_p5_threshold_R": pl_p5_threshold_r,
            "cvar_worst_R": cvar_worst_r,
            "stress_delta_ev_mean_R": delta_ev_stress_mean_r,
            "explainable_edge_raw": edge.get("explainable"),
            "explainability_signals_pass": signals_pass,
            "explainability_tiered_pass": explainability_ok,
            "pass": bool(mc_ready and steady_ok),
            "failures": list(dict.fromkeys((mc_rule_failures or []) + (steady_gate.get("reasons") or []))),
        },
        "steady_gate": {
            "decision": steady_gate.get("decision"),
            "approved": steady_ok,
            "risk_multiplier": steady_gate.get("risk_multiplier"),
            "reasons": steady_gate.get("reasons") or [],
            "input": steady_payload,
        },
        "spot_integrity": spot_integrity,
        "mc_provenance": mc_provenance,
        "top_candidate": {
            "type": top.get("type"),
            "decision": top.get("decision"),
            "score": (top.get("score") or {}).get("Total"),
            "gate_failures": top.get("gateFailures") or [],
        },
        "raw": brief,
    }


def append_log(entry: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def render_markdown(n: Dict[str, Any], attempt: int, max_attempts: int) -> str:
    missing = n.get("missing_required") or []
    miss_txt = ", ".join(f"`{m}`" for m in missing) if missing else "none"
    top = n.get("top_candidate") or {}
    tr = n.get("trade_ready_rule") or {}
    tr_fail = ", ".join(tr.get("failures") or []) if (tr.get("failures") or []) else "none"
    pv = n.get("mc_provenance") or {}
    ids = n.get("trace_ids") or {}
    si = n.get("spot_integrity") or {}
    pv_txt = (
        f"source_mode={pv.get('options_mc_source_mode')} | source={pv.get('options_mc_source_file')} | generated_at={pv.get('generated_at')} | "
        f"model={pv.get('model')} | n_batches={pv.get('n_batches')} | paths_per_batch={pv.get('paths_per_batch')} | "
        f"n_total_paths={pv.get('n_total_paths')} | computed_n_total_paths={pv.get('computed_n_total_paths')} | "
        f"assumptions_n_paths={pv.get('assumptions_n_paths')} | counts_consistent={pv.get('counts_consistent')} | source_stale={pv.get('source_stale')} | "
        f"base_seed={pv.get('base_seed')} | crn_scope={pv.get('crn_scope')}"
    )
    return (
        f"MC Snapshot (attempt {attempt}/{max_attempts})\n"
        f"- Status: **{n['data_status']}**\n"
        f"- Action: **{n['action_state']}**\n"
        f"- Spot (SPY): **{n.get('spot')}**\n"
        f"- Data Source: **{n.get('data_source')}**\n"
        f"- Regime: **{n.get('regime')}** | trend **{n.get('trend')}** | VIX **{n.get('vix_direction')}** | US10Y **{n.get('rates_direction')}**\n"
        f"- Final Decision: **{n.get('final_decision')}**\n"
        f"- Trace IDs: snapshot_id={ids.get('snapshot_id')} | brief_id={ids.get('brief_id')} | mc_id={ids.get('mc_id')}\n"
        f"- Top Candidate: `{top.get('type')}` score={top.get('score')} decision={top.get('decision')}\n"
        f"- Spot integrity: ok={si.get('ok')} | pipeline_spot={n.get('spot')} | ref_spot={si.get('ref_spot')} | delta={si.get('delta')} (max={si.get('max_delta')})\n"
        f"- Missing for trade-ready: {miss_txt}\n"
        f"- TRADE_READY rule: pass={tr.get('pass')} | R_structural={tr.get('r_structural')} ({tr.get('r_structural_source')}) | R_minpl_debug={tr.get('r_minpl_debug')} | EV_mean_R={tr.get('ev_mean_R')} | EV_seed_p5_R={tr.get('ev_seed_p5_R')} (min_batches={tr.get('ev_seed_p5_min_batches')}) | EV_stress_mean_R={tr.get('ev_stress_mean_R')} | PL_p5_R={tr.get('pl_p5_R')} (thr>{tr.get('pl_p5_threshold_R')}) | CVaR_worst_R={tr.get('cvar_worst_R')} | StressΔEV_mean_R={tr.get('stress_delta_ev_mean_R')} | Explainable(raw/tiered)={tr.get('explainable_edge_raw')}/{tr.get('explainability_tiered_pass')} sig_pass={tr.get('explainability_signals_pass')}\n"
        f"- TRADE_READY rule failures: {tr_fail}\n"
        f"- MC provenance: {pv_txt}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run normalized MC workflow for SPY")
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--retry-delay-sec", type=int, default=180)
    ap.add_argument("--skip-live", action="store_true", help="Skip node live snapshot step")
    ap.add_argument("--json", action="store_true", help="Print normalized JSON instead of markdown")
    args = ap.parse_args()

    last: Optional[Dict[str, Any]] = None

    for i in range(1, max(1, args.max_attempts) + 1):
        live = run_live_snapshot(args.skip_live)
        brief = run_brief()
        normalized = normalize(live, brief)
        normalized["attempt"] = i
        normalized["max_attempts"] = args.max_attempts

        trace_ids = normalized.get("trace_ids") or {}
        if not trace_ids.get("snapshot_id"):
            raise RuntimeError("Untraceable run: missing snapshot_id in trace_ids")
        mc_provenance = normalized.get("mc_provenance") or {}
        if mc_provenance.get("counts_consistent") is not True:
            raise RuntimeError(
                "Inconsistent path counts in options-mc source "
                f"(n_total_paths={mc_provenance.get('n_total_paths')}, "
                f"computed={mc_provenance.get('computed_n_total_paths')}, "
                f"assumptions_n_paths={mc_provenance.get('assumptions_n_paths')})"
            )
        if mc_provenance.get("source_stale") is True:
            raise RuntimeError("Stale options-mc source file: refresh required before decisioning")
        spot_integrity = normalized.get("spot_integrity") or {}
        if spot_integrity.get("ok") is False:
            raise RuntimeError(
                "Spot integrity mismatch "
                f"(pipeline={normalized.get('spot')}, ref={spot_integrity.get('ref_spot')}, delta={spot_integrity.get('delta')})"
            )

        append_log(
            {
                "timestamp": normalized["timestamp"],
                "attempt": i,
                "data_status": normalized["data_status"],
                "data_source": normalized.get("data_source"),
                "action_state": normalized["action_state"],
                "spot": normalized["spot"],
                "final_decision": normalized["final_decision"],
                "missing_required": normalized["missing_required"],
                "trade_ready_rule_pass": (normalized.get("trade_ready_rule") or {}).get("pass"),
                "trade_ready_rule_failures": (normalized.get("trade_ready_rule") or {}).get("failures"),
            }
        )

        last = normalized
        if normalized["data_status"] in {"OK", "OK_FALLBACK"}:
            break
        if i < args.max_attempts:
            time.sleep(max(0, args.retry_delay_sec))

    if last is None:
        raise RuntimeError("No MC output generated")

    if args.json:
        print(json.dumps(last, indent=2))
    else:
        print(render_markdown(last, last["attempt"], last["max_attempts"]))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
