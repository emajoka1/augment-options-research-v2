#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen

CHAIN_PATH = os.environ.get("SPY_CHAIN_PATH", os.path.expanduser("~/lab/data/tastytrade/SPY_nested_chain.json"))
DXLINK_PATH = os.environ.get("SPY_DXLINK_PATH", os.path.expanduser("~/lab/data/tastytrade/dxlink_snapshot.json"))
LIVE_PATH = os.environ.get("SPY_LIVE_PATH", os.path.expanduser("~/lab/data/tastytrade/spy_live_snapshot.json"))

MIN_OI = int(os.environ.get("SPY_MIN_OI", "1000"))
MIN_VOL = int(os.environ.get("SPY_MIN_VOL", "100"))
MAX_SPREAD_PCT = float(os.environ.get("SPY_MAX_SPREAD_PCT", "0.10"))


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
    symbols = {"SPY": "SPY", "VIX": "%5EVIX", "US10Y": "%5ETNX", "DXY": "DX-Y.NYB"}
    for k, sym in symbols.items():
        try:
            d = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d")
            closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if isinstance(c, (int, float))]
            if len(closes) >= 2:
                last, prev = closes[-1], closes[-2]
                out[k] = {"last": round(last, 3), "pct": round((last - prev) / prev * 100.0, 3)}
        except Exception:
            continue
    return out


def round_to_step(x: float, step: int = 5):
    return int(round(x / step) * step)


def load_live(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def spread_pct(row):
    b, a, m = row.get("bid"), row.get("ask"), row.get("mark")
    if b is None or a is None or m in (None, 0):
        return None
    return max(0.0, (a - b) / m)


def is_liquid(row):
    sp = spread_pct(row)
    return (
        row.get("mark") not in (None, 0)
        and row.get("openInterest") is not None
        and row.get("dayVolume") is not None
        and row.get("openInterest") >= MIN_OI
        and row.get("dayVolume") >= MIN_VOL
        and sp is not None
        and sp <= MAX_SPREAD_PCT
    )


def watchlist_from_live(live):
    rows = []
    data = live.get("data", {})
    for c in live.get("contracts", []):
        d = data.get(c["symbol"], {})
        row = {
            "expiry": c["expiry"],
            "dte": c["dte"],
            "strike": c["strike"],
            "side": c["side"],
            "symbol": c["symbol"],
            "bid": d.get("bid"),
            "ask": d.get("ask"),
            "mark": d.get("mark"),
            "last": d.get("last"),
            "delta": d.get("delta"),
            "iv": d.get("iv"),
            "openInterest": d.get("openInterest"),
            "dayVolume": d.get("dayVolume"),
            "confidence": "delayed-live",
        }
        sp = spread_pct(row)
        row["spreadPct"] = round(sp, 4) if sp is not None else None
        row["liquid"] = is_liquid(row)
        rows.append(row)
    rows.sort(key=lambda r: (r["dte"], -(r.get("dayVolume") or 0), -(r.get("openInterest") or 0)))
    return rows


def build_watchlist_structure(chain, spot):
    expirations = sorted(chain.get("expirations", []), key=lambda e: e.get("days-to-expiration", 99999))[:2]
    center = round_to_step(spot or 600, 5)
    picks = [center - 10, center - 5, center, center + 5, center + 10]
    out = []
    for exp in expirations:
        dte = exp.get("days-to-expiration")
        ed = exp.get("expiration-date")
        strikes = {int(float(s["strike-price"])): s for s in exp.get("strikes", [])}
        for st in picks:
            if st in strikes:
                row = strikes[st]
                out.append({"expiry": ed, "dte": dte, "strike": st, "call": row.get("call"), "put": row.get("put"), "confidence": "structure-only"})
    return out[:10]


def choose_leg(rows, side, dte_lo, dte_hi, d_lo, d_hi):
    cands = [
        r for r in rows
        if r.get("side") == side
        and r.get("delta") is not None
        and dte_lo <= (r.get("dte") or 999) <= dte_hi
        and d_lo <= abs(float(r["delta"])) <= d_hi
        and r.get("liquid")
    ]
    if not cands:
        return None
    target = (d_lo + d_hi) / 2.0
    cands.sort(key=lambda r: (r["dte"], abs(abs(float(r["delta"])) - target), -(r.get("dayVolume") or 0)))
    return cands[0]


def build_setups_from_live(rows):
    liquid_rows = [r for r in rows if r.get("liquid")]

    # Debit spread: 5-14 DTE, long 0.35-0.45, short 0.15-0.25 same expiry, short strike above long strike.
    long_call = choose_leg(liquid_rows, "C", 5, 14, 0.35, 0.45)
    short_call = None
    if long_call:
        call_pool = [r for r in liquid_rows if r["side"] == "C" and r["expiry"] == long_call["expiry"] and r["strike"] > long_call["strike"] and 0.15 <= abs(float(r["delta"])) <= 0.25]
        call_pool.sort(key=lambda r: (abs(abs(float(r["delta"])) - 0.2), abs((r["strike"] - long_call["strike"]) - 10)))
        short_call = call_pool[0] if call_pool else None

    # Put credit: 7-30 DTE, short 0.20-0.30, long 0.10-0.15 same expiry, long strike lower.
    short_put = choose_leg(liquid_rows, "P", 7, 30, 0.20, 0.30)
    long_put = None
    if short_put:
        put_pool = [r for r in liquid_rows if r["side"] == "P" and r["expiry"] == short_put["expiry"] and r["strike"] < short_put["strike"] and 0.10 <= abs(float(r["delta"])) <= 0.15]
        put_pool.sort(key=lambda r: (abs(abs(float(r["delta"])) - 0.125), abs((short_put["strike"] - r["strike"]) - 10)))
        long_put = put_pool[0] if put_pool else None

    # Iron condor: both shorts 0.15-0.20, wings nearest lower/higher strike same expiry.
    short_call_ic = choose_leg(liquid_rows, "C", 7, 21, 0.15, 0.20)
    short_put_ic = choose_leg(liquid_rows, "P", 7, 21, 0.15, 0.20)
    long_call_ic = long_put_ic = None
    if short_call_ic and short_put_ic:
        common_exp = short_call_ic["expiry"] if short_call_ic["expiry"] == short_put_ic["expiry"] else None
        if common_exp:
            cands_c = [r for r in liquid_rows if r["expiry"] == common_exp and r["side"] == "C" and r["strike"] > short_call_ic["strike"]]
            cands_p = [r for r in liquid_rows if r["expiry"] == common_exp and r["side"] == "P" and r["strike"] < short_put_ic["strike"]]
            if cands_c:
                long_call_ic = sorted(cands_c, key=lambda r: abs((r["strike"] - short_call_ic["strike"]) - 10))[0]
            if cands_p:
                long_put_ic = sorted(cands_p, key=lambda r: abs((short_put_ic["strike"] - r["strike"]) - 10))[0]

    def fmt(r):
        if not r:
            return "N/A"
        return f"{r['expiry']} {int(r['strike'])}{r['side']}"

    return [
        {
            "setup": "Bull call debit spread (tight selector)",
            "example": f"Buy {fmt(long_call)} / Sell {fmt(short_call)}",
            "criteria": "5-14 DTE, long 0.35-0.45 delta, short 0.15-0.25 delta, liquid only",
            "risk": "Max loss = net debit x 100",
        },
        {
            "setup": "Bull put credit spread (tight selector)",
            "example": f"Sell {fmt(short_put)} / Buy {fmt(long_put)}",
            "criteria": "7-30 DTE, short 0.20-0.30 delta, long 0.10-0.15 delta, liquid only",
            "risk": "Max loss = (width - credit) x 100",
        },
        {
            "setup": "Iron condor (tight selector)",
            "example": f"Sell {fmt(short_put_ic)} / Buy {fmt(long_put_ic)} + Sell {fmt(short_call_ic)} / Buy {fmt(long_call_ic)}",
            "criteria": "7-21 DTE, both shorts 0.15-0.20 delta, liquid only",
            "risk": "Max loss per side = (wing - credit) x 100",
        },
    ]


def build_setups_structure(spot):
    s = round_to_step(spot or 600, 5)
    return [
        {"setup": "Bull call debit spread (defined risk)", "example": f"Buy {s+5}C / Sell {s+15}C (7-14 DTE)", "risk": "Max loss = net debit x 100"},
        {"setup": "Bull put credit spread (defined risk)", "example": f"Sell {s-15}P / Buy {s-25}P (14-30 DTE)", "risk": "Max loss = (width - credit) x 100"},
        {"setup": "Iron condor (range/vol crush)", "example": f"Sell {s-15}P/{s-25}P + Sell {s+15}C/{s+25}C (7-21 DTE)", "risk": "Max loss per side = (wing - credit) x 100"},
    ]


def catalysts():
    return [
        {"title": "US economic calendar (time + consensus)", "link": "https://www.investing.com/economic-calendar/"},
        {"title": "ForexFactory macro calendar", "link": "https://www.forexfactory.com/calendar"},
        {"title": "Fed events/speeches calendar", "link": "https://www.federalreserve.gov/newsevents/calendar.htm"},
        {"title": "US Treasury auction calendar", "link": "https://home.treasury.gov/resource-center/data-chart-center/quarterly-refunding/documents-auction-calendar"},
        {"title": "Earnings calendar", "link": "https://www.marketwatch.com/tools/earnings-calendar"},
    ]


def main():
    now = datetime.now(timezone.utc).isoformat()
    chain = load_chain(CHAIN_PATH)
    live = load_live(LIVE_PATH)

    spot_dx = get_spot_from_dx(DXLINK_PATH)
    spot_yf = get_spot_from_yahoo()
    spot_live = None
    if live and live.get("underlying", {}).get("mark"):
        spot_live = float(live["underlying"]["mark"])
    spot = spot_live or spot_dx or spot_yf

    regime = get_regime_read()

    trade_ready = False
    watch = []
    setups = []
    missing = []

    if live:
        watch = watchlist_from_live(live)
        liquid_count = len([r for r in watch if r.get("liquid")])
        has_fields = len([r for r in watch if all(r.get(k) is not None for k in ["bid", "ask", "mark", "delta", "iv", "openInterest", "dayVolume"])])
        trade_ready = liquid_count >= 6 and has_fields >= 10
        setups = build_setups_from_live(watch)
        if not trade_ready:
            missing = [
                f"need >=6 liquid contracts (now {liquid_count})",
                f"need >=10 contracts with complete fields (now {has_fields})",
            ]
    else:
        watch = build_watchlist_structure(chain, spot)
        setups = build_setups_structure(spot)
        missing = ["option bid/ask", "option mark/last", "greeks + IV", "open interest", "day volume"]

    brief = {
        "status": "TRADE_READY_DELAYED" if trade_ready else "PARTIAL_DATA",
        "generated_at_utc": now,
        "symbol": "SPY",
        "spot": {"value": spot, "source": "live_snapshot" if spot_live else ("dxlink_snapshot" if spot_dx else ("yahoo" if spot_yf else None))},
        "selector": {
            "minOI": MIN_OI,
            "minDayVolume": MIN_VOL,
            "maxSpreadPct": MAX_SPREAD_PCT,
            "deltaBands": {
                "debit_long_call": [0.35, 0.45],
                "debit_short_call": [0.15, 0.25],
                "credit_short_put": [0.20, 0.30],
                "credit_long_put": [0.10, 0.15],
                "ic_shorts": [0.15, 0.20],
            },
        },
        "catalysts": catalysts(),
        "regime": regime,
        "watchlist": watch[:20],
        "setups": setups,
        "missing_for_trade_ready": missing,
        "guardrails": [
            "Prefer tight markets; skip contracts with wide spread (>8-10% of premium).",
            "Require OI and day volume before execution.",
            "Cap risk per trade to <=0.5-1.0% of account.",
            "This feed is delayed; confirm fills and live state in broker before sending orders.",
        ],
    }
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
