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

    if missing_required:
        action_state = "NO_TRADE"
    elif final_decision == "TRADE":
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
