#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

CHAIN_PATH = os.environ.get("SPY_CHAIN_PATH", os.path.expanduser("~/lab/data/tastytrade/SPY_nested_chain.json"))
DXLINK_PATH = os.environ.get("SPY_DXLINK_PATH", os.path.expanduser("~/lab/data/tastytrade/dxlink_snapshot.json"))
LIVE_PATH = os.environ.get("SPY_LIVE_PATH", os.path.expanduser("~/lab/data/tastytrade/spy_live_snapshot.json"))

MIN_OI = int(os.environ.get("SPY_MIN_OI", "1000"))
MIN_VOL = int(os.environ.get("SPY_MIN_VOL", "100"))
MAX_SPREAD_PCT = float(os.environ.get("SPY_MAX_SPREAD_PCT", "0.10"))
ACCOUNT_SIZE = float(os.environ.get("SPY_ACCOUNT_SIZE", "10000"))
RISK_PCT = float(os.environ.get("SPY_RISK_PCT", "0.0075"))


def http_json(url: str, timeout: int = 8):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_chain(path: str):
    with open(path) as f:
        raw = json.load(f)
    return raw.get("data", {}).get("items", [])[0]


def get_spot_from_dx(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            d = json.load(f)
        for ev in d.get("events", []):
            if ev.get("eventType") == "Quote" and ev.get("eventSymbol") == "SPY":
                b, a = ev.get("bidPrice"), ev.get("askPrice")
                if b and a:
                    return (float(b) + float(a)) / 2.0
    except Exception:
        return None
    return None


def get_spot_from_yahoo():
    try:
        d = http_json("https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1m&range=1d")
        m = d["chart"]["result"][0].get("meta", {})
        return float(m.get("regularMarketPrice") or m.get("previousClose"))
    except Exception:
        return None


def get_regime_read():
    out = {}
    symbols = {"SPY": "SPY", "VIX": "%5EVIX", "US10Y": "%5ETNX", "DXY": "DX-Y.NYB"}
    for k, sym in symbols.items():
        try:
            d = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d")
            closes = [c for c in d["chart"]["result"][0]["indicators"]["quote"][0]["close"] if isinstance(c, (int, float))]
            if len(closes) >= 2:
                last, prev = closes[-1], closes[-2]
                out[k] = {"last": round(last, 3), "pct": round((last - prev) / prev * 100.0, 3)}
        except Exception:
            pass
    return out


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
        and row.get("openInterest") is not None and row.get("openInterest") >= MIN_OI
        and row.get("dayVolume") is not None and row.get("dayVolume") >= MIN_VOL
        and sp is not None and sp <= MAX_SPREAD_PCT
    )


def watchlist_from_live(live):
    rows = []
    data = live.get("data", {})
    for c in live.get("contracts", []):
        d = data.get(c["symbol"], {})
        r = {
            "expiry": c["expiry"], "dte": c["dte"], "strike": c["strike"], "side": c["side"], "symbol": c["symbol"],
            "bid": d.get("bid"), "ask": d.get("ask"), "mark": d.get("mark"), "last": d.get("last"),
            "delta": d.get("delta"), "iv": d.get("iv"), "openInterest": d.get("openInterest"), "dayVolume": d.get("dayVolume"),
            "confidence": "delayed-live",
        }
        sp = spread_pct(r)
        r["spreadPct"] = round(sp, 4) if sp is not None else None
        r["liquid"] = is_liquid(r)
        rows.append(r)
    rows.sort(key=lambda r: (r["dte"], -(r.get("dayVolume") or 0), -(r.get("openInterest") or 0)))
    return rows


def choose_leg(rows, side, dte_lo, dte_hi, d_lo, d_hi):
    cands = [r for r in rows if r.get("liquid") and r.get("side") == side and r.get("delta") is not None and dte_lo <= (r.get("dte") or 999) <= dte_hi and d_lo <= abs(float(r["delta"])) <= d_hi]
    if not cands:
        return None
    target = (d_lo + d_hi) / 2
    cands.sort(key=lambda r: (r["dte"], abs(abs(float(r["delta"])) - target), -(r.get("dayVolume") or 0)))
    return cands[0]


def contracts_for_risk(max_loss_per_contract):
    if not max_loss_per_contract or max_loss_per_contract <= 0:
        return 0
    dollars = ACCOUNT_SIZE * RISK_PCT
    return int(max(0, dollars // max_loss_per_contract))


def build_setups_from_live(rows):
    liquid = [r for r in rows if r.get("liquid")]

    # strict bands first, then graceful fallback bands
    long_c = choose_leg(liquid, "C", 5, 14, 0.35, 0.45) or choose_leg(liquid, "C", 5, 14, 0.30, 0.55)
    short_c = None
    if long_c:
        pool = [r for r in liquid if r["side"] == "C" and r["expiry"] == long_c["expiry"] and r["strike"] > long_c["strike"] and 0.15 <= abs(float(r["delta"])) <= 0.25]
        if not pool:
            pool = [r for r in liquid if r["side"] == "C" and r["expiry"] == long_c["expiry"] and r["strike"] > long_c["strike"] and 0.10 <= abs(float(r["delta"])) <= 0.35]
        pool.sort(key=lambda r: (abs(abs(float(r["delta"])) - 0.2), abs((r["strike"] - long_c["strike"]) - 10)))
        short_c = pool[0] if pool else None

    short_p = choose_leg(liquid, "P", 7, 30, 0.20, 0.30) or choose_leg(liquid, "P", 7, 30, 0.15, 0.35)
    long_p = None
    if short_p:
        pool = [r for r in liquid if r["side"] == "P" and r["expiry"] == short_p["expiry"] and r["strike"] < short_p["strike"] and 0.10 <= abs(float(r["delta"])) <= 0.15]
        if not pool:
            pool = [r for r in liquid if r["side"] == "P" and r["expiry"] == short_p["expiry"] and r["strike"] < short_p["strike"] and 0.05 <= abs(float(r["delta"])) <= 0.20]
        pool.sort(key=lambda r: (abs(abs(float(r["delta"])) - 0.125), abs((short_p["strike"] - r["strike"]) - 10)))
        long_p = pool[0] if pool else None

    short_c_ic = choose_leg(liquid, "C", 5, 30, 0.15, 0.20) or choose_leg(liquid, "C", 5, 30, 0.10, 0.30)
    short_p_ic = choose_leg(liquid, "P", 5, 30, 0.15, 0.20) or choose_leg(liquid, "P", 5, 30, 0.10, 0.30)
    long_c_ic = long_p_ic = None

    # Condor fallback: force same-expiry pair if the independent pickers disagree.
    if not (short_c_ic and short_p_ic and short_c_ic["expiry"] == short_p_ic["expiry"]):
        expiries = sorted({r["expiry"] for r in liquid if 7 <= (r.get("dte") or 999) <= 30})
        best = None
        for exp in expiries:
            calls = [r for r in liquid if r["expiry"] == exp and r["side"] == "C" and 0.12 <= abs(float(r.get("delta") or 99)) <= 0.30]
            puts = [r for r in liquid if r["expiry"] == exp and r["side"] == "P" and 0.12 <= abs(float(r.get("delta") or 99)) <= 0.30]
            if not calls or not puts:
                continue
            for c in sorted(calls, key=lambda r: abs(abs(float(r["delta"])) - 0.18)):
                for p in sorted(puts, key=lambda r: abs(abs(float(r["delta"])) - 0.18)):
                    has_call_wing = any(x for x in rows if x["expiry"] == exp and x["side"] == "C" and x["strike"] > c["strike"] and x.get("mark") not in (None,0))
                    has_put_wing = any(x for x in rows if x["expiry"] == exp and x["side"] == "P" and x["strike"] < p["strike"] and x.get("mark") not in (None,0))
                    if not (has_call_wing and has_put_wing):
                        continue
                    score = abs(abs(float(c["delta"])) - 0.18) + abs(abs(float(p["delta"])) - 0.18)
                    if best is None or score < best[0]:
                        best = (score, c, p)
                    break
                if best is not None:
                    break
        if best:
            short_c_ic, short_p_ic = best[1], best[2]

    if short_c_ic and short_p_ic and short_c_ic["expiry"] == short_p_ic["expiry"]:
        exp = short_c_ic["expiry"]
        cands_c = [r for r in rows if r["expiry"] == exp and r["side"] == "C" and r["strike"] > short_c_ic["strike"] and r.get("mark") not in (None,0)]
        cands_p = [r for r in rows if r["expiry"] == exp and r["side"] == "P" and r["strike"] < short_p_ic["strike"] and r.get("mark") not in (None,0)]
        if cands_c:
            long_c_ic = sorted(cands_c, key=lambda r: abs((r["strike"] - short_c_ic["strike"]) - 5))[0]
        if cands_p:
            long_p_ic = sorted(cands_p, key=lambda r: abs((short_p_ic["strike"] - r["strike"]) - 5))[0]

    def fmt(r): return f"{r['expiry']} {int(r['strike'])}{r['side']}" if r else "N/A"

    def avg_spread(*legs):
        vals = [x.get("spreadPct") for x in legs if x and x.get("spreadPct") is not None]
        return (sum(vals) / len(vals)) if vals else None

    def make_ticket(kind, legs, max_loss):
        marks = [float(x.get("mark") or 0) for x in legs if x]
        if not marks:
            return None
        if kind == "debit":
            entry = max(0.01, marks[0] - marks[1])
            return {
                "entry": [round(entry * 0.98, 2), round(entry * 1.03, 2)],
                "takeProfit": round(entry * 1.6, 2),
                "stopLoss": round(entry * 0.6, 2),
                "invalidation": "break below opening range low",
                "maxLoss": round(max_loss, 2),
                "contracts": contracts_for_risk(max_loss),
            }
        if kind == "credit":
            entry = max(0.01, marks[0] - marks[1])
            return {
                "entry": [round(entry * 0.97, 2), round(entry * 1.03, 2)],
                "takeProfit": round(entry * 0.5, 2),
                "stopLoss": round(entry * 1.8, 2),
                "invalidation": "underlying breaches short strike momentum zone",
                "maxLoss": round(max_loss, 2),
                "contracts": contracts_for_risk(max_loss),
            }
        if kind == "condor":
            entry = max(0.01, marks[0] + marks[1] - marks[2] - marks[3])
            return {
                "entry": [round(entry * 0.95, 2), round(entry * 1.05, 2)],
                "takeProfit": round(entry * 0.5, 2),
                "stopLoss": round(entry * 1.8, 2),
                "invalidation": "price acceptance outside short strikes",
                "maxLoss": round(max_loss, 2),
                "contracts": contracts_for_risk(max_loss),
            }
        return None

    def score_setup(legs, target_deltas, regime_bias=0):
        if not all(legs):
            return 0
        liq = sum(1 for l in legs if l.get("liquid")) / len(legs)
        sp = avg_spread(*legs)
        spread_score = 1.0 if sp is not None and sp <= MAX_SPREAD_PCT else 0.4
        delta_err = 0.0
        n = 0
        for l, t in zip(legs, target_deltas):
            if l.get("delta") is None:
                continue
            delta_err += abs(abs(float(l["delta"])) - t)
            n += 1
        delta_score = max(0.0, 1.0 - (delta_err / max(1, n)) / 0.25)
        raw = 100 * (0.40 * liq + 0.25 * spread_score + 0.25 * delta_score + 0.10 * regime_bias)
        return int(round(max(0, min(100, raw))))

    vix = 0
    # regime bias: prefer debit/credit when VIX moderate-low, condor when VIX elevated
    # (coarse; final check still manual)
    try:
        vix = float(next((r.get("iv") for r in rows if r.get("side") == "P" and r.get("dte") == 5 and r.get("strike") == 685), 0) or 0)
    except Exception:
        vix = 0

    setups = []
    if long_c and short_c and long_c.get("mark") and short_c.get("mark"):
        debit = max(0.01, float(long_c["mark"]) - float(short_c["mark"]))
        ml = debit * 100
        setups.append({
            "setup": "Bull call debit spread",
            "example": f"Buy {fmt(long_c)} / Sell {fmt(short_c)}",
            "maxLossPerContract": round(ml,2),
            "contractsByRisk": contracts_for_risk(ml),
            "qualityScore": score_setup([long_c, short_c], [0.40, 0.20], regime_bias=1.0),
            "ticket": make_ticket("debit", [long_c, short_c], ml),
        })
    else:
        setups.append({"setup": "Bull call debit spread", "example": "N/A", "maxLossPerContract": None, "contractsByRisk": 0, "qualityScore": 0, "ticket": None})

    if short_p and long_p:
        width = abs(float(short_p["strike"]) - float(long_p["strike"]))
        credit = max(0.01, float(short_p.get("mark") or 0) - float(long_p.get("mark") or 0))
        ml = max(0.01, (width - credit) * 100)
        setups.append({
            "setup": "Bull put credit spread",
            "example": f"Sell {fmt(short_p)} / Buy {fmt(long_p)}",
            "maxLossPerContract": round(ml,2),
            "contractsByRisk": contracts_for_risk(ml),
            "qualityScore": score_setup([short_p, long_p], [0.25, 0.12], regime_bias=0.8),
            "ticket": make_ticket("credit", [short_p, long_p], ml),
        })
    else:
        setups.append({"setup": "Bull put credit spread", "example": "N/A", "maxLossPerContract": None, "contractsByRisk": 0, "qualityScore": 0, "ticket": None})

    if short_c_ic and short_p_ic and long_c_ic and long_p_ic:
        wing = min(abs(float(long_c_ic["strike"]) - float(short_c_ic["strike"])), abs(float(short_p_ic["strike"]) - float(long_p_ic["strike"])))
        credit = max(0.01, (float(short_c_ic.get("mark") or 0)+float(short_p_ic.get("mark") or 0)-float(long_c_ic.get("mark") or 0)-float(long_p_ic.get("mark") or 0)))
        ml = max(0.01, (wing - credit) * 100)
        setups.append({
            "setup": "Iron condor",
            "example": f"Sell {fmt(short_p_ic)}/{fmt(short_c_ic)} + Buy {fmt(long_p_ic)}/{fmt(long_c_ic)}",
            "maxLossPerContract": round(ml,2),
            "contractsByRisk": contracts_for_risk(ml),
            "qualityScore": score_setup([short_p_ic, short_c_ic, long_p_ic, long_c_ic], [0.18, 0.18, 0.10, 0.10], regime_bias=0.6),
            "ticket": make_ticket("condor", [short_p_ic, short_c_ic, long_p_ic, long_c_ic], ml),
        })
    else:
        setups.append({"setup": "Iron condor", "example": "N/A", "maxLossPerContract": None, "contractsByRisk": 0, "qualityScore": 0, "ticket": None})

    setups.sort(key=lambda s: s.get("qualityScore", 0), reverse=True)
    for i, s in enumerate(setups, 1):
        s["rank"] = i

    return setups


def catalysts():
    return [
        {"title": "US economic calendar", "link": "https://www.investing.com/economic-calendar/"},
        {"title": "ForexFactory calendar", "link": "https://www.forexfactory.com/calendar"},
        {"title": "Fed calendar", "link": "https://www.federalreserve.gov/newsevents/calendar.htm"},
        {"title": "Treasury auction calendar", "link": "https://home.treasury.gov/resource-center/data-chart-center/quarterly-refunding/documents-auction-calendar"},
        {"title": "Earnings calendar", "link": "https://www.marketwatch.com/tools/earnings-calendar"},
    ]


def execution_window():
    lon = datetime.now(ZoneInfo("Europe/London"))
    h, m = lon.hour, lon.minute
    in_window = (h > 14 or (h == 14 and m >= 35)) and (h < 15 or (h == 15 and m <= 15))
    return {
        "nowLondon": lon.isoformat(timespec="minutes"),
        "recommended": "14:35-15:15 London",
        "inWindow": in_window,
    }


def no_trade_reason(regime, liquid_count, avg_spread):
    reasons = []
    vix = (regime.get("VIX") or {}).get("last")
    if liquid_count < 6:
        reasons.append("insufficient liquid contracts")
    if avg_spread is not None and avg_spread > MAX_SPREAD_PCT:
        reasons.append("average spread too wide")
    if vix is not None and vix > 35:
        reasons.append("volatility shock regime (VIX > 35)")
    return reasons


def main():
    now = datetime.now(timezone.utc).isoformat()
    live = load_live(LIVE_PATH)
    chain = load_chain(CHAIN_PATH)

    spot = None
    if live and live.get("underlying", {}).get("mark"):
        spot = float(live["underlying"]["mark"])
    spot = spot or get_spot_from_dx(DXLINK_PATH) or get_spot_from_yahoo()

    regime = get_regime_read()
    watch = watchlist_from_live(live) if live else []
    liquid_rows = [r for r in watch if r.get("liquid")]
    liquid_count = len(liquid_rows)
    avg_spread = round(sum(r.get("spreadPct", 0) for r in liquid_rows) / liquid_count, 4) if liquid_count else None

    setups = build_setups_from_live(watch) if live else []
    ready = live is not None and liquid_count >= 6
    reasons = no_trade_reason(regime, liquid_count, avg_spread)
    if reasons:
        ready = False

    brief = {
        "status": "TRADE_READY_DELAYED" if ready else "PARTIAL_DATA",
        "generated_at_utc": now,
        "symbol": "SPY",
        "spot": {"value": spot, "source": "live_snapshot" if live else None},
        "executionWindow": execution_window(),
        "riskModel": {"accountSize": ACCOUNT_SIZE, "riskPct": RISK_PCT, "riskDollars": round(ACCOUNT_SIZE * RISK_PCT, 2)},
        "selector": {"minOI": MIN_OI, "minDayVolume": MIN_VOL, "maxSpreadPct": MAX_SPREAD_PCT},
        "regime": regime,
        "watchlist": (watch[:20] if watch else []),
        "setups": setups,
        "catalysts": catalysts(),
        "noTradeReasons": reasons,
        "missing_for_trade_ready": ([] if ready else ["need stable liquid contracts + acceptable spreads + non-shock regime"]),
        "guardrails": [
            "Confirm live broker quotes before order entry (this feed is delayed).",
            "Skip if spread > 8-10% of option premium.",
            "Risk <= 0.5-1.0% account per trade.",
        ],
    }
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
