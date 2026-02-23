#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ak_system.config import RiskConfig, Schedules, build_paths, ensure_dirs
from ak_system.pipeline import collect, distill, propose, validate


def run_once(root: Path) -> dict:
    paths = build_paths(root)
    ensure_dirs(paths)
    risk = RiskConfig()

    c = collect(paths)
    d = distill(paths)
    v = validate(paths, risk)
    p = propose(paths, v)

    result = {
        "collect": str(c),
        "distill": str(d),
        "validate_status": v.get("status"),
        "proposal": str(p),
    }
    print(json.dumps(result, indent=2))
    return result


def run_daemon(root: Path) -> None:
    paths = build_paths(root)
    ensure_dirs(paths)
    risk = RiskConfig()
    schedule = Schedules()

    timers = {
        "collect": 0.0,
        "distill": 0.0,
        "validate": 0.0,
        "propose": 0.0,
    }

    while True:
        now = time.time()
        if now - timers["collect"] >= schedule.collect_minutes * 60:
            collect(paths)
            timers["collect"] = now
        if now - timers["distill"] >= schedule.distill_minutes * 60:
            distill(paths)
            timers["distill"] = now
        if now - timers["validate"] >= schedule.validate_minutes * 60:
            report = validate(paths, risk)
            timers["validate"] = now
        if now - timers["propose"] >= schedule.propose_minutes * 60:
            report = validate(paths, risk)
            propose(paths, report)
            timers["propose"] = now

        time.sleep(15)


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Research+Knowledge scheduler")
    parser.add_argument("--root", default=".", help="workspace root")
    parser.add_argument("--mode", choices=["once", "daemon"], default="once")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    if args.mode == "once":
        run_once(root)
    else:
        run_daemon(root)


if __name__ == "__main__":
    main()
