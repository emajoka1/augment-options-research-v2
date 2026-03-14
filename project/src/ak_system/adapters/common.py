from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


REQUIRED_KEYS = ["asof_utc", "source", "symbol", "feature_set", "quality_flags"]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AdapterPayload:
    asof_utc: str
    source: str
    symbol: str
    feature_set: Dict[str, Any]
    quality_flags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_adapter_payload(payload: Dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for k in REQUIRED_KEYS:
        if k not in payload:
            errors.append(f"missing:{k}")
    if payload.get("asof_utc") in (None, ""):
        errors.append("invalid:asof_utc")
    if not isinstance(payload.get("feature_set"), dict):
        errors.append("invalid:feature_set")
    if not isinstance(payload.get("quality_flags"), list):
        errors.append("invalid:quality_flags")
    return len(errors) == 0, errors
