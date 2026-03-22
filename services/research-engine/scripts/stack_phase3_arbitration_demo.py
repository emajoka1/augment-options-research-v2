#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from ak_system.adapters.longport_adapter import fetch_longport_quote
from ak_system.stack.source_arbitration import arbitrate_sources


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    lp = fetch_longport_quote("SPY")
    live = {"source_tier": "OK_LIVE", "spot": 500.0, "quality_flags": ["live_ok"]}
    fallback = {"source_tier": "OK_FALLBACK", "spot": 499.8, "quality_flags": ["fallback_ok"]}

    selected = arbitrate_sources(lp, live, fallback)
    out = {
        "phase": "stack_phase3",
        "longport": lp,
        "arbitration": selected,
    }

    exp = root / "kb" / "experiments"
    exp.mkdir(parents=True, exist_ok=True)
    path = exp / "stack-phase3-arbitration-demo.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(path), "selected": selected}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
