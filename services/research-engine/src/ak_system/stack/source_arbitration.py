from __future__ import annotations

from typing import Any, Dict


TIER_ORDER = ["OK_LIVE_PREMIUM", "OK_LIVE", "OK_FALLBACK"]


def _resolve_tier(data: Dict[str, Any]) -> str:
    tier = data.get("source_tier")
    if isinstance(tier, str) and tier in TIER_ORDER:
        return tier
    return "UNAVAILABLE"


def arbitrate_sources(longport_data: Dict[str, Any] | None, live_data: Dict[str, Any] | None, fallback_data: Dict[str, Any] | None) -> Dict[str, Any]:
    candidates = [
        ("longport", longport_data or {}),
        ("live", live_data or {}),
        ("fallback", fallback_data or {}),
    ]

    best_name = None
    best_payload: Dict[str, Any] = {}
    best_rank = 999
    for name, payload in candidates:
        tier = _resolve_tier(payload)
        if tier in TIER_ORDER:
            rank = TIER_ORDER.index(tier)
            if rank < best_rank:
                best_rank = rank
                best_name = name
                best_payload = payload

    if best_name is None:
        raise RuntimeError("source_arbitration_unresolved")

    spot = best_payload.get("spot")
    if spot is None:
        # unresolved spot integrity must fail closed
        raise RuntimeError("source_arbitration_spot_missing")

    return {
        "selected_source": best_name,
        "source_tier": _resolve_tier(best_payload),
        "spot": spot,
        "quality_flags": best_payload.get("quality_flags") or [],
    }
