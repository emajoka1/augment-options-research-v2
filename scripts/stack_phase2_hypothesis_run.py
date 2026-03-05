#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from ak_system.research.hypothesis_lane import build_hypothesis, validate_hypothesis_payload, write_hypothesis_artifact


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    payload = build_hypothesis("SPY")
    ok, errors = validate_hypothesis_payload(payload)
    if not ok:
        raise RuntimeError("hypothesis payload invalid: " + ",".join(errors))
    path = write_hypothesis_artifact(root, payload)
    print(json.dumps({"artifact": str(path), "lane": "hypothesis"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
