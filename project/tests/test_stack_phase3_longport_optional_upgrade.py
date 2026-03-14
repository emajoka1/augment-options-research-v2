import os

from ak_system.adapters.longport_adapter import fetch_longport_quote
from ak_system.stack.source_arbitration import arbitrate_sources


def test_tier_arbitration_prefers_premium_then_live_then_fallback():
    premium = {"source_tier": "OK_LIVE_PREMIUM", "spot": 501.0, "quality_flags": ["premium_ok"]}
    live = {"source_tier": "OK_LIVE", "spot": 500.0, "quality_flags": ["live_ok"]}
    fallback = {"source_tier": "OK_FALLBACK", "spot": 499.0, "quality_flags": ["fallback_ok"]}

    out = arbitrate_sources(premium, live, fallback)
    assert out["source_tier"] == "OK_LIVE_PREMIUM"
    assert out["spot"] == 501.0



def test_tier_arbitration_falls_back_when_premium_unavailable():
    premium_unavail = {"source_tier": "UNAVAILABLE", "spot": None, "quality_flags": ["premium_unavailable"]}
    live = {"source_tier": "OK_LIVE", "spot": 500.0, "quality_flags": ["live_ok"]}
    fallback = {"source_tier": "OK_FALLBACK", "spot": 499.0, "quality_flags": ["fallback_ok"]}

    out = arbitrate_sources(premium_unavail, live, fallback)
    assert out["source_tier"] == "OK_LIVE"
    assert out["spot"] == 500.0



def test_longport_disabled_explicit_label(monkeypatch):
    monkeypatch.delenv("LONGPORT_APP_KEY", raising=False)
    monkeypatch.delenv("LONGPORT_APP_SECRET", raising=False)
    monkeypatch.delenv("LONGPORT_ACCESS_TOKEN", raising=False)

    out = fetch_longport_quote("SPY")
    assert out["source"] == "longport_unavailable"
    assert out["source_tier"] == "UNAVAILABLE"
    assert "premium_unavailable" in out["quality_flags"]
