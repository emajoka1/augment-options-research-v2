#!/usr/bin/env python3
"""Show current MC scheduler + state health in one place."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "snapshots" / "mc_last_state.json"
CRON_LOG = ROOT / "snapshots" / "mc_cron.log"


def launchd_status() -> tuple[bool, str]:
    cmd = ["launchctl", "print", "gui/501/com.mc.notify"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        return False, "launchd job not loaded"

    txt = p.stdout
    last_exit = "unknown"
    runs = "unknown"
    state = "unknown"
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("state ="):
            state = s.split("=", 1)[1].strip()
        elif s.startswith("runs ="):
            runs = s.split("=", 1)[1].strip()
        elif s.startswith("last exit code ="):
            last_exit = s.split("=", 1)[1].strip()

    ok = (last_exit == "0") or (state == "running")
    return ok, f"state={state}, runs={runs}, last_exit={last_exit}"


def read_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def tail_log(n: int = 3) -> list[str]:
    if not CRON_LOG.exists():
        return []
    lines = CRON_LOG.read_text(errors="ignore").splitlines()
    return lines[-n:]


def main() -> int:
    ok, lstat = launchd_status()
    state = read_state()
    print(f"Scheduler: {'OK' if ok else 'ISSUE'} ({lstat})")

    if state:
        print(
            "Last MC state: "
            f"action={state.get('action_state')} "
            f"status={state.get('data_status')} "
            f"decision={state.get('final_decision')} "
            f"spot={state.get('spot')} "
            f"at={state.get('timestamp')}"
        )
    else:
        print("Last MC state: none yet")

    tail = tail_log(3)
    if tail:
        print("Recent log tail:")
        for ln in tail:
            print(f"- {ln}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
