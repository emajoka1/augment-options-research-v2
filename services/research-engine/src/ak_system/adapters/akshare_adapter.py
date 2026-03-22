from __future__ import annotations

from typing import Any, Dict

from .common import AdapterPayload, now_utc_iso, validate_adapter_payload


def fetch_akshare_features(symbol: str = "SPY") -> Dict[str, Any]:
    """Research-only AKShare adapter.

    Keeps dependency optional; if AKShare is unavailable, returns fail-closed quality flags.
    """
    feature_set: Dict[str, Any] = {}
    quality_flags = []
    source = "akshare"

    try:
        import akshare as ak  # type: ignore

        # Lightweight proxy features (best-effort).
        # Using index/ETF proxy keeps this adapter research-only and non-blocking.
        hist = ak.stock_us_hist(symbol=symbol)  # pragma: no cover (depends on external lib/network)
        if hist is None or len(hist) == 0:
            quality_flags.append("empty_dataset")
        else:
            last = hist.iloc[-1]
            feature_set = {
                "close": float(last.get("收盘", 0.0)),
                "open": float(last.get("开盘", 0.0)),
                "high": float(last.get("最高", 0.0)),
                "low": float(last.get("最低", 0.0)),
                "volume": float(last.get("成交量", 0.0)),
            }
            quality_flags.append("ok")
    except Exception:
        # Fail closed: explicit degraded marker, no silent success.
        source = "akshare_unavailable"
        feature_set = {
            "close": None,
            "open": None,
            "high": None,
            "low": None,
            "volume": None,
            "macro_proxy": None,
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
        raise RuntimeError("akshare_adapter schema invalid: " + ",".join(errors))
    return payload
