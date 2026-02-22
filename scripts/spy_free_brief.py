#!/usr/bin/env python3
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.request import Request, urlopen

CHAIN_PATH = os.environ.get("SPY_CHAIN_PATH", os.path.expanduser("~/lab/data/tastytrade/SPY_nested_chain.json"))
DXLINK_PATH = os.environ.get("SPY_DXLINK_PATH", os.path.expanduser("~/lab/data/tastytrade/dxlink_snapshot.json"))


def http_json(url: str, timeout: int = 8):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_chain(path: str):
    with open(path) as f:
        raw = json.load(f)
    items = raw.get("data", {}).get("items", [])
    if not items:
        raise RuntimeError("No chain items found")
    return items[0]


def get_spot_from_dx(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            d = json.load(f)
        for ev in d.get("events", []):
            if ev.get("eventType") == "Quote" and ev.get("eventSymbol") == "SPY":
                bid = ev.get("bidPrice")
                ask = ev.get("askPrice")
                if bid and ask:
                    return (float(bid) + float(ask)) / 2.0
    except Exception:
        return None
    return None


def get_spot_from_yahoo():
    try:
        d = http_json("https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1m&range=1d")
        result = d["chart"]["result"][0]
        m = result.get("meta", {})
        for key in ("regularMarketPrice", "previousClose"):
            if m.get(key):
                return float(m[key])
    except Exception:
        return None
    return None


def get_regime_read():
    out = {}
    symbols = {
        "SPY": "SPY",
        "VIX": "%5EVIX",
        "US10Y": "%5ETNX",
        "DXY": "DX-Y.NYB",
    }
    for k, sym in symbols.items():
        try:
            d = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d")
            closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if isinstance(c, (int, float))]
            if len(closes) >= 2:
                last, prev = closes[-1], closes[-2]
                out[k] = {
                    "last": round(last, 3),
                    "pct": round((last - prev) / prev * 100.0, 3),
                }
        except Exception:
            continue
    return out


def round_to_step(x: float, step: int = 5):
    return int(round(x / step) * step)


def build_watchlist(chain, spot):
    expirations = chain.get("expirations", [])
    expirations = sorted(expirations, key=lambda e: e.get("days-to-expiration", 99999))
    chosen = expirations[:2]
    if not chosen:
        return []

    center = round_to_step(spot or 600, 5)
    picks = [center - 10, center - 5, center, center + 5, center + 10]
    out = []
    for exp in chosen:
        dte = exp.get("days-to-expiration")
        ed = exp.get("expiration-date")
        strikes = {int(float(s["strike-price"])): s for s in exp.get("strikes", [])}
        for st in picks:
            if st in strikes:
                row = strikes[st]
                out.append(
                    {
                        "expiry": ed,
                        "dte": dte,
                        "strike": st,
                        "call": row.get("call"),
                        "put": row.get("put"),
                        "confidence": "structure-only",
                    }
                )
    return out[:10]


def catalysts():
    # Public links that are dependable and free. (No paid feed claims.)
    return [
        {"title": "US economic calendar (time + consensus)", "link": "https://www.investing.com/economic-calendar/"},
        {"title": "ForexFactory macro calendar", "link": "https://www.forexfactory.com/calendar"},
        {"title": "Fed events/speeches calendar", "link": "https://www.federalreserve.gov/newsevents/calendar.htm"},
        {"title": "US Treasury auction calendar", "link": "https://home.treasury.gov/resource-center/data-chart-center/quarterly-refunding/documents-auction-calendar"},
        {"title": "Earnings calendar", "link": "https://www.marketwatch.com/tools/earnings-calendar"},
    ]


def build_setups(spot):
    s = round_to_step(spot or 600, 5)
    return [
        {
            "setup": "Bull call debit spread (defined risk)",
            "example": f"Buy {s+5}C / Sell {s+15}C (7-14 DTE)",
            "risk": "Max loss = net debit x 100",
        },
        {
            "setup": "Bull put credit spread (defined risk)",
            "example": f"Sell {s-15}P / Buy {s-25}P (14-30 DTE)",
            "risk": "Max loss = (width - credit) x 100",
        },
        {
            "setup": "Iron condor (range/vol crush)",
            "example": f"Sell {s-15}P/{s-25}P + Sell {s+15}C/{s+25}C (7-21 DTE)",
            "risk": "Max loss per side = (wing - credit) x 100",
        },
    ]


def main():
    now = datetime.now(timezone.utc).isoformat()
    chain = load_chain(CHAIN_PATH)

    spot_dx = get_spot_from_dx(DXLINK_PATH)
    spot_yf = get_spot_from_yahoo()
    spot = spot_dx or spot_yf

    watch = build_watchlist(chain, spot)
    regime = get_regime_read()

    missing = [
        "option bid/ask",
        "option mark/last",
        "greeks + IV",
        "open interest",
        "day volume",
    ]

    brief = {
        "status": "PARTIAL_DATA",
        "generated_at_utc": now,
        "symbol": "SPY",
        "spot": {"value": spot, "source": "dxlink_snapshot" if spot_dx else ("yahoo" if spot_yf else None)},
        "catalysts": catalysts(),
        "regime": regime,
        "watchlist": watch,
        "setups": build_setups(spot),
        "missing_for_trade_ready": missing,
        "guardrails": [
            "Do not place trade without checking live bid/ask and fill quality.",
            "Skip legs with wide spread (>8-10% of premium).",
            "Prefer strikes with strong OI and day volume.",
            "Cap risk per trade to <=0.5-1.0% of account.",
        ],
    }

    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
