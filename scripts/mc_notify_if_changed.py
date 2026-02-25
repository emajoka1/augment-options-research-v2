#!/usr/bin/env python3
"""Run MC and emit notification text only when state changes.

Designed for cron/periodic execution.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "snapshots" / "mc_last_state.json"


def run_mc_json(max_attempts: int, retry_delay_sec: int, skip_live: bool) -> Dict[str, Any]:
    cmd = [
        "python3",
        "scripts/mc_command.py",
        "--json",
        "--max-attempts",
        str(max_attempts),
        "--retry-delay-sec",
        str(retry_delay_sec),
    ]
    if skip_live:
        cmd.append("--skip-live")

    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "mc_command failed")
    return json.loads(p.stdout)


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def changed(prev: Dict[str, Any], cur: Dict[str, Any]) -> bool:
    keys = ["action_state", "data_status", "final_decision"]
    return any(prev.get(k) != cur.get(k) for k in keys)


def summary(cur: Dict[str, Any]) -> str:
    miss = cur.get("missing_required") or []
    miss_txt = ", ".join(miss) if miss else "none"
    return (
        f"MC update: {cur.get('action_state')} | status={cur.get('data_status')} | "
        f"SPY={cur.get('spot')} | regime={cur.get('regime')} ({cur.get('trend')}) | "
        f"decision={cur.get('final_decision')} | missing={miss_txt}"
    )


def maybe_notify(text: str, enabled: bool) -> None:
    if not enabled:
        return
    # Best-effort: OpenClaw wake event if available.
    subprocess.run(
        ["openclaw", "system", "event", "--text", text, "--mode", "now"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run MC and notify only on state changes")
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--retry-delay-sec", type=int, default=180)
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--notify", action="store_true", help="Emit openclaw system event on change")
    ap.add_argument("--force", action="store_true", help="Emit summary even if state unchanged")
    args = ap.parse_args()

    cur = run_mc_json(args.max_attempts, args.retry_delay_sec, args.skip_live)
    prev = load_state()

    is_changed = changed(prev, cur)
    should_emit = args.force or is_changed or not prev

    if should_emit:
        txt = summary(cur)
        print(txt)
        maybe_notify(txt, args.notify)
    else:
        print("NO_CHANGE")

    save_state(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_state": cur.get("action_state"),
            "data_status": cur.get("data_status"),
            "final_decision": cur.get("final_decision"),
            "spot": cur.get("spot"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
