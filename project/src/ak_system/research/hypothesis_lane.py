from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


REQUIRED_HYP_KEYS = [
    "assumptions",
    "expected_edge_mechanism",
    "invalidation",
    "confidence_source",
    "provenance",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_hash(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_hypothesis(symbol: str = "SPY", model_id: str = "rd-agent:placeholder", prompt_version: str = "v1") -> Dict[str, Any]:
    h = {
        "assumptions": [
            "volatility mean-reverts after event shock",
            "liquidity remains sufficient for defined-risk structures",
        ],
        "expected_edge_mechanism": "Short-term volatility dislocation decays faster than priced in front expiration.",
        "invalidation": "Regime flips to trend|vol_expanding with rising rates and widening spreads.",
        "confidence_source": "rule_based_placeholder",
        "provenance": {
            "prompt_version": prompt_version,
            "model_id": model_id,
            "run_timestamp_utc": _now(),
        },
    }
    cfg = {
        "symbol": symbol,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "assumptions": h["assumptions"],
        "edge": h["expected_edge_mechanism"],
        "invalidation": h["invalidation"],
    }
    h["provenance"]["config_hash"] = _config_hash(cfg)

    return {
        "lane": "hypothesis",
        "symbol": symbol,
        "hypothesis": h,
        "guardrails": {
            "can_set_trade_ready": False,
            "allowed_outputs": ["research_task", "ticket_proposal"],
        },
    }


def validate_hypothesis_payload(payload: Dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    hyp = payload.get("hypothesis") or {}
    for k in REQUIRED_HYP_KEYS:
        if k not in hyp:
            errors.append(f"missing:{k}")
    guard = payload.get("guardrails") or {}
    if guard.get("can_set_trade_ready") is not False:
        errors.append("invalid:can_set_trade_ready_must_be_false")
    prov = hyp.get("provenance") or {}
    for k in ["prompt_version", "model_id", "run_timestamp_utc", "config_hash"]:
        if not prov.get(k):
            errors.append(f"missing:provenance.{k}")
    return len(errors) == 0, errors


def write_hypothesis_artifact(root: Path, payload: Dict[str, Any]) -> Path:
    out = root / "kb" / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out / f"hypothesis-{ts}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
