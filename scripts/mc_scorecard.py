#!/usr/bin/env python3
"""Quick scorecard for MC run history."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "snapshots" / "mc_runs.jsonl"


def main() -> int:
    if not LOG.exists():
        print("No run history yet.")
        return 0

    rows = []
    with LOG.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    if not rows:
        print("No parsable run history.")
        return 0

    act = Counter(r.get("action_state") for r in rows)
    sts = Counter(r.get("data_status") for r in rows)
    dec = Counter(r.get("final_decision") for r in rows)

    print(f"Total runs: {len(rows)}")
    print("Action states:", dict(act))
    print("Data status:", dict(sts))
    print("Final decision:", dict(dec))
    print("Last run:", rows[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
