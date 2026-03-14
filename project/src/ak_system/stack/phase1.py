from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ak_system.adapters import fetch_akshare_features, fetch_qlib_features, validate_adapter_payload


def run_phase1(symbol: str = "SPY") -> Dict[str, Any]:
    ak = fetch_akshare_features(symbol)
    ql = fetch_qlib_features(symbol)

    for name, payload in (("akshare", ak), ("qlib", ql)):
        ok, errors = validate_adapter_payload(payload)
        if not ok:
            raise RuntimeError(f"{name} payload invalid: {errors}")

    return {
        "phase": "stack_phase1",
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "adapters": {
            "akshare": ak,
            "qlib": ql,
        },
        "research_only": True,
        "execution_impact": "none",
    }


def write_phase1_artifact(root: Path, payload: Dict[str, Any]) -> Path:
    out = root / "kb" / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out / f"stack-phase1-{ts}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
