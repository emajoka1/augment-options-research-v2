#!/usr/bin/env python3
"""Summarize MC outcomes."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "snapshots" / "mc_outcomes.jsonl"


def load_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def avg(xs):
    return sum(xs) / len(xs) if xs else None


def main() -> int:
    rows = load_jsonl(OUT)
    if not rows:
        print("No outcomes yet.")
        return 0

    by_action = defaultdict(list)
    for r in rows:
        by_action[r.get("action_state", "UNK")].append(r)

    print(f"Total signals tracked: {len(rows)}")
    for action, rs in sorted(by_action.items()):
        r30 = [x.get("ret_30m") for x in rs if isinstance(x.get("ret_30m"), (int, float))]
        r2h = [x.get("ret_2h") for x in rs if isinstance(x.get("ret_2h"), (int, float))]
        reod = [x.get("ret_eod") for x in rs if isinstance(x.get("ret_eod"), (int, float))]
        print(f"\n[{action}] count={len(rs)}")
        print(f"  avg ret 30m: {avg(r30):.4%}" if r30 else "  avg ret 30m: n/a")
        print(f"  avg ret 2h : {avg(r2h):.4%}" if r2h else "  avg ret 2h : n/a")
        print(f"  avg ret eod: {avg(reod):.4%}" if reod else "  avg ret eod: n/a")

    print("\nLast signal:")
    print(rows[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
