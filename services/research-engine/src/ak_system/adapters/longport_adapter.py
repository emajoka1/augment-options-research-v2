from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_longport_quote(symbol: str = "SPY") -> Dict[str, Any]:
    """Optional Longport premium adapter.

    No hard dependency: if credentials/library missing, return explicit unavailable payload.
    """
    app_key = os.environ.get("LONGPORT_APP_KEY")
    app_secret = os.environ.get("LONGPORT_APP_SECRET")
    access_token = os.environ.get("LONGPORT_ACCESS_TOKEN")

    if not (app_key and app_secret and access_token):
        return {
            "asof_utc": now_utc_iso(),
            "source": "longport_unavailable",
            "symbol": symbol,
            "spot": None,
            "quality_flags": ["credentials_missing", "premium_unavailable"],
            "source_tier": "UNAVAILABLE",
        }

    try:
        # Keep optional import and fail-closed if unavailable.
        import longport  # type: ignore  # pragma: no cover

        # Placeholder: explicit optional mode keeps baseline non-dependent.
        return {
            "asof_utc": now_utc_iso(),
            "source": "longport",
            "symbol": symbol,
            "spot": None,
            "quality_flags": ["library_loaded", "quote_fetch_not_configured"],
            "source_tier": "OK_LIVE_PREMIUM",
        }
    except Exception:
        return {
            "asof_utc": now_utc_iso(),
            "source": "longport_unavailable",
            "symbol": symbol,
            "spot": None,
            "quality_flags": ["library_missing", "premium_unavailable"],
            "source_tier": "UNAVAILABLE",
        }
