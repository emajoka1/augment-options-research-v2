from __future__ import annotations

from typing import Any, Dict

from .common import AdapterPayload, now_utc_iso, validate_adapter_payload


def fetch_qlib_features(symbol: str = "SPY") -> Dict[str, Any]:
    """Research-only Qlib adapter for model-ready factors.

    Optional dependency; emits explicit quality flags on fallback path.
    """
    feature_set: Dict[str, Any] = {}
    source = "qlib"
    quality_flags = []

    try:
        # Optional import; avoid hard dependency for baseline operation.
        import qlib  # type: ignore  # pragma: no cover

        # Keep this adapter deterministic + research-only: expose a minimal placeholder
        # factor map; real factor generation is delegated to future phase work.
        feature_set = {
            "momentum_20d": None,
            "volatility_20d": None,
            "value_proxy": None,
            "liquidity_proxy": None,
        }
        quality_flags = ["qlib_loaded", "factor_placeholders"]
    except Exception:
        source = "qlib_unavailable"
        feature_set = {
            "momentum_20d": None,
            "volatility_20d": None,
            "value_proxy": None,
            "liquidity_proxy": None,
        }
        quality_flags = ["adapter_unavailable", "research_only_no_trade"]

    payload = AdapterPayload(
        asof_utc=now_utc_iso(),
        source=source,
        symbol=symbol,
        feature_set=feature_set,
        quality_flags=quality_flags,
    ).to_dict()

    ok, errors = validate_adapter_payload(payload)
    if not ok:
        raise RuntimeError("qlib_adapter schema invalid: " + ",".join(errors))
    return payload
