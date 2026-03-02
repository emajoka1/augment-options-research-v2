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


def latest_options_mc() -> Optional[Dict[str, Any]]:
    files = sorted((ROOT / "kb" / "experiments").glob("options-mc-*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except Exception:
        return None


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


def normalize(live: Optional[Dict[str, Any]], brief: Dict[str, Any]) -> Dict[str, Any]:
    tb = brief.get("TRADE BRIEF", {})
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

    # Additional TRADE_READY gates from latest options MC report.
    mc = latest_options_mc() or {}
    ms = mc.get("multi_seed_confidence") or {}
    edge = mc.get("edge_attribution") or {}
    fh = mc.get("friction_hurdle") or {}

    ev_p5_r = None
    cvar_worst_r = None
    delta_ev_stress_r = None
    mc_rule_failures = []

    r_unit = None
    r_unit_source = "unavailable"
    try:
        ev_5th = ms.get("ev_5th_percentile")
        cvar_worst = ms.get("cvar_worst")
        r_unit, r_unit_source = _derive_structural_r(mc)
        if r_unit is not None:
            r_unit = max(float(r_unit), 1e-6)
        if isinstance(ev_5th, (int, float)) and r_unit:
            ev_p5_r = float(ev_5th) / r_unit
        if isinstance(cvar_worst, (int, float)) and r_unit:
            cvar_worst_r = float(cvar_worst) / r_unit

        if isinstance(fh.get("ev_stress_R"), (int, float)) and isinstance(fh.get("ev_real_R"), (int, float)):
            delta_ev_stress_r = float(fh.get("ev_stress_R")) - float(fh.get("ev_real_R"))
        elif isinstance(fh.get("ev_stress_R"), (int, float)) and isinstance(fh.get("ev_mid_R"), (int, float)):
            delta_ev_stress_r = float(fh.get("ev_stress_R")) - float(fh.get("ev_mid_R"))
    except Exception:
        pass

    mc_ready = True
    if ev_p5_r is None or ev_p5_r <= 0.02:
        mc_ready = False
        mc_rule_failures.append("ev_p5_not_above_0.02R")
    if cvar_worst_r is None or cvar_worst_r <= -1.0:
        mc_ready = False
        mc_rule_failures.append("cvar_worst_not_above_-1R")
    if delta_ev_stress_r is None or delta_ev_stress_r < -0.05:
        mc_ready = False
        mc_rule_failures.append("stress_delta_ev_below_-0.05R")
    if edge.get("explainable") is not True:
        mc_ready = False
        mc_rule_failures.append("edge_not_explainable")

    if missing_required:
        action_state = "NO_TRADE"
    elif final_decision == "TRADE" and mc_ready:
        action_state = "TRADE_READY"
    else:
        action_state = "WATCH"

    return {
        "timestamp": _now_iso(),
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
            "r_unit": r_unit,
            "r_unit_source": r_unit_source,
            "ev_5th_R": ev_p5_r,
            "cvar_worst_R": cvar_worst_r,
            "stress_delta_ev_R": delta_ev_stress_r,
            "explainable_edge": edge.get("explainable"),
            "pass": mc_ready,
            "failures": mc_rule_failures,
        },
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
    return (
        f"MC Snapshot (attempt {attempt}/{max_attempts})\n"
        f"- Status: **{n['data_status']}**\n"
        f"- Action: **{n['action_state']}**\n"
        f"- Spot (SPY): **{n.get('spot')}**\n"
        f"- Data Source: **{n.get('data_source')}**\n"
        f"- Regime: **{n.get('regime')}** | trend **{n.get('trend')}** | VIX **{n.get('vix_direction')}** | US10Y **{n.get('rates_direction')}**\n"
        f"- Final Decision: **{n.get('final_decision')}**\n"
        f"- Top Candidate: `{top.get('type')}` score={top.get('score')} decision={top.get('decision')}\n"
        f"- Missing for trade-ready: {miss_txt}\n"
        f"- TRADE_READY rule: pass={tr.get('pass')} | R={tr.get('r_unit')} ({tr.get('r_unit_source')}) | EV_5th_R={tr.get('ev_5th_R')} | CVaR_worst_R={tr.get('cvar_worst_R')} | StressΔEV_R={tr.get('stress_delta_ev_R')} | Explainable={tr.get('explainable_edge')}\n"
        f"- TRADE_READY rule failures: {tr_fail}\n"
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
