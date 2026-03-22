#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from ak_system.stack.phase1 import run_phase1, write_phase1_artifact


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    payload = run_phase1("SPY")
    path = write_phase1_artifact(root, payload)
    print(json.dumps({"artifact": str(path), "phase": "stack_phase1"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
