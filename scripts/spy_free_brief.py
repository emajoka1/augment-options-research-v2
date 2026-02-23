#!/usr/bin/env python3
import json
import math
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
MULTI_LEG_SPREAD_PCT_THRESHOLD = float(os.environ.get("SPY_MULTI_LEG_MAX_SPREAD_PCT", "0.05"))
ACCOUNT_SIZE = float(os.environ.get("SPY_ACCOUNT_SIZE", "10000"))
RISK_PCT = float(os.environ.get("SPY_RISK_PCT", "0.0075"))


def http_json(url: str, timeout: int = 8):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_chain(path: str):
    with open(path) as f:
        raw = json.load(f)
    items = raw.get("data", {}).get("items", [])
    return items[0] if items else {}


def load_live(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


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


def get_yahoo_series(sym: str, rng: str = "3mo", interval: str = "1d"):
    try:
        d = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={rng}")
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        return q
    except Exception:
        return None


def ann_realized_vol(closes, window=10):
    c = [x for x in closes if isinstance(x, (int, float))]
    if len(c) < window + 1:
        return None
    rets = [math.log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i - 1] > 0 and c[i] > 0]
    if len(rets) < window:
        return None
    w = rets[-window:]
    mean = sum(w) / len(w)
    var = sum((x - mean) ** 2 for x in w) / max(1, len(w) - 1)
    return math.sqrt(var) * math.sqrt(252)


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
        row = {
            "expiry": c["expiry"], "dte": c["dte"], "strike": c["strike"], "side": c["side"], "symbol": c["symbol"],
            "bid": d.get("bid"), "ask": d.get("ask"), "mark": d.get("mark"), "last": d.get("last"),
            "delta": d.get("delta"), "iv": d.get("iv"), "openInterest": d.get("openInterest"), "dayVolume": d.get("dayVolume"),
            "confidence": "delayed-live",
        }
        sp = spread_pct(row)
        row["spreadPct"] = round(sp, 4) if sp is not None else None
        row["liquid"] = is_liquid(row)
        rows.append(row)
    rows.sort(key=lambda r: (r.get("dte", 999), -(r.get("dayVolume") or 0), -(r.get("openInterest") or 0)))
    return rows


def choose_leg(rows, side, dte_lo, dte_hi, d_lo, d_hi):
    cands = [
        r for r in rows
        if r.get("liquid") and r.get("side") == side and r.get("delta") is not None
        and dte_lo <= (r.get("dte") or 999) <= dte_hi and d_lo <= abs(float(r["delta"])) <= d_hi
    ]
    if not cands:
        return None
    target = (d_lo + d_hi) / 2
    cands.sort(key=lambda r: (r["dte"], abs(abs(float(r["delta"])) - target), -(r.get("dayVolume") or 0)))
    return cands[0]


def contracts_for_risk(max_loss):
    if not max_loss or max_loss <= 0:
        return 0
    return int((ACCOUNT_SIZE * RISK_PCT) // max_loss)


def expected_move(spot, iv, dte):
    if not spot or not iv or dte is None:
        return None
    return spot * iv * math.sqrt(max(dte, 1) / 365.0)


def build_candidates(rows):
    liquid = [r for r in rows if r.get("liquid")]
    # debit
    long_c = choose_leg(liquid, "C", 5, 14, 0.35, 0.45) or choose_leg(liquid, "C", 5, 14, 0.30, 0.55)
    short_c = None
    if long_c:
        pool = [r for r in liquid if r["side"] == "C" and r["expiry"] == long_c["expiry"] and r["strike"] > long_c["strike"]]
        pool.sort(key=lambda r: (abs(abs(float(r.get("delta") or 0)) - 0.2), abs((r["strike"] - long_c["strike"]) - 10)))
        short_c = pool[0] if pool else None

    # credit put
    short_p = choose_leg(liquid, "P", 7, 35, 0.20, 0.30) or choose_leg(liquid, "P", 7, 35, 0.15, 0.35)
    long_p = None
    if short_p:
        pool = [r for r in liquid if r["side"] == "P" and r["expiry"] == short_p["expiry"] and r["strike"] < short_p["strike"]]
        pool.sort(key=lambda r: (abs(abs(float(r.get("delta") or 0)) - 0.12), abs((short_p["strike"] - r["strike"]) - 10)))
        long_p = pool[0] if pool else None

    # condor paired by expiry
    short_c_ic = short_p_ic = long_c_ic = long_p_ic = None
    expiries = sorted({r["expiry"] for r in liquid if 5 <= (r.get("dte") or 999) <= 30})
    best = None
    for exp in expiries:
        calls = [r for r in liquid if r["expiry"] == exp and r["side"] == "C" and 0.10 <= abs(float(r.get("delta") or 99)) <= 0.30]
        puts = [r for r in liquid if r["expiry"] == exp and r["side"] == "P" and 0.10 <= abs(float(r.get("delta") or 99)) <= 0.30]
        if not calls or not puts:
            continue
        c = sorted(calls, key=lambda r: abs(abs(float(r["delta"])) - 0.18))[0]
        p = sorted(puts, key=lambda r: abs(abs(float(r["delta"])) - 0.18))[0]
        cwing = [r for r in rows if r["expiry"] == exp and r["side"] == "C" and r["strike"] > c["strike"] and r.get("mark") not in (None, 0)]
        pwing = [r for r in rows if r["expiry"] == exp and r["side"] == "P" and r["strike"] < p["strike"] and r.get("mark") not in (None, 0)]
        if not cwing or not pwing:
            continue
        lc = sorted(cwing, key=lambda r: abs((r["strike"] - c["strike"]) - 5))[0]
        lp = sorted(pwing, key=lambda r: abs((p["strike"] - r["strike"]) - 5))[0]
        score = abs(abs(float(c["delta"])) - 0.18) + abs(abs(float(p["delta"])) - 0.18)
        if best is None or score < best[0]:
            best = (score, c, p, lc, lp)
    if best:
        _, short_c_ic, short_p_ic, long_c_ic, long_p_ic = best

    return {
        "debit": (long_c, short_c),
        "credit": (short_p, long_p),
        "condor": (short_p_ic, long_p_ic, short_c_ic, long_c_ic),
    }


def regime_snapshot(spot):
    q_spy = get_yahoo_series("SPY", "3mo", "1d") or {}
    q_vix = get_yahoo_series("%5EVIX", "1mo", "1d") or {}
    q_tnx = get_yahoo_series("%5ETNX", "1mo", "1d") or {}

    closes = [x for x in (q_spy.get("close") or []) if isinstance(x, (int, float))]
    highs = [x for x in (q_spy.get("high") or []) if isinstance(x, (int, float))]
    lows = [x for x in (q_spy.get("low") or []) if isinstance(x, (int, float))]
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else None
    trend_up = bool(ma5 and ma20 and ma5 > ma20 and closes[-1] > ma20) if closes else False

    vixc = [x for x in (q_vix.get("close") or []) if isinstance(x, (int, float))]
    tny = [x for x in (q_tnx.get("close") or []) if isinstance(x, (int, float))]
    vix_dir = ("down" if len(vixc) >= 2 and vixc[-1] < vixc[-2] else "up") if vixc else "unknown"
    rates_dir = ("up" if len(tny) >= 2 and tny[-1] > tny[-2] else "down") if tny else "unknown"

    risk_regime = "Risk-on" if trend_up and vix_dir == "down" else ("Risk-off" if (not trend_up and vix_dir == "up") else "Neutral")

    metrics = [
        {"metric": "MA5-MA20", "value": round((ma5 - ma20), 3) if ma5 and ma20 else None, "threshold": ">0", "interpretation": "uptrend" if trend_up else "not-uptrend"},
        {"metric": "VIX day change", "value": round(vixc[-1] - vixc[-2], 3) if len(vixc) >= 2 else None, "threshold": "<0 risk-on", "interpretation": vix_dir},
        {"metric": "US10Y day change", "value": round(tny[-1] - tny[-2], 3) if len(tny) >= 2 else None, "threshold": "context", "interpretation": rates_dir},
    ]

    rv10 = ann_realized_vol(closes, 10)
    rv20 = ann_realized_vol(closes, 20)

    return {
        "ticker": "SPY",
        "spot": spot,
        "timeUserTz": datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="minutes"),
        "eventRiskNext48h": [
            "https://www.investing.com/economic-calendar/",
            "https://www.forexfactory.com/calendar",
            "https://www.federalreserve.gov/newsevents/calendar.htm",
            "https://www.marketwatch.com/tools/earnings-calendar",
        ],
        "regime": {
            "riskState": risk_regime,
            "trend": "up" if trend_up else "down_or_flat",
            "vixDirection": vix_dir,
            "ratesDirection": rates_dir,
            "metrics": metrics,
        },
        "realizedVol": {"rv10": rv10, "rv20": rv20},
    }


def vol_state(rows, rv10, rv20):
    ivs = [float(r["iv"]) for r in rows if r.get("iv") is not None]
    current_iv = sum(ivs[:6]) / len(ivs[:6]) if len(ivs) >= 6 else (sum(ivs) / len(ivs) if ivs else None)

    near = [r for r in rows if 4 <= (r.get("dte") or 999) <= 9 and r.get("iv") is not None]
    back = [r for r in rows if 20 <= (r.get("dte") or 999) <= 40 and r.get("iv") is not None]
    near_iv = sum(float(r["iv"]) for r in near) / len(near) if near else None
    back_iv = sum(float(r["iv"]) for r in back) / len(back) if back else None

    near_put = [r for r in near if r.get("side") == "P"]
    near_call = [r for r in near if r.get("side") == "C"]
    put_iv = sum(float(r["iv"]) for r in near_put) / len(near_put) if near_put else None
    call_iv = sum(float(r["iv"]) for r in near_call) / len(near_call) if near_call else None
    skew = (put_iv - call_iv) if put_iv is not None and call_iv is not None else None

    if current_iv is None:
        vol_label = "unknown"
    else:
        base_rv = rv20 or rv10
        if base_rv is None:
            vol_label = "unknown"
        elif current_iv < base_rv * 0.95:
            vol_label = "cheap"
        elif current_iv > base_rv * 1.05:
            vol_label = "expensive"
        else:
            vol_label = "fair"

    return {
        "ivCurrent": current_iv,
        "ivRankProxy": None,
        "ivVsRv10": (current_iv - rv10) if (current_iv and rv10) else None,
        "ivVsRv20": (current_iv - rv20) if (current_iv and rv20) else None,
        "termStructureFrontBack": (near_iv - back_iv) if (near_iv and back_iv) else None,
        "skewPutMinusCall": skew,
        "volLabel": vol_label,
        "expansionRisk": "high" if current_iv and rv20 and current_iv < rv20 else "low_or_moderate",
        "contractionRisk": "high" if current_iv and rv20 and current_iv > rv20 else "low_or_moderate",
    }


def score_components(candidate, context, vol, exec_ok, event_ok):
    # A) Regime Fit 25
    regime_fit = 0
    risk_state = context["regime"]["riskState"]
    if candidate["type"] in ("debit", "credit") and risk_state == "Risk-on":
        regime_fit = 22
    elif candidate["type"] == "condor" and risk_state == "Neutral":
        regime_fit = 22
    else:
        regime_fit = 12

    # B) Volatility Edge 25
    vol_edge = 0
    label = vol["volLabel"]
    if label == "cheap" and candidate["type"] == "debit":
        vol_edge = 23
    elif label == "expensive" and candidate["type"] in ("credit", "condor"):
        vol_edge = 23
    elif label == "fair":
        vol_edge = 14
    else:
        vol_edge = 8

    # C) Structure Quality 20
    structure = 0
    if candidate.get("maxLoss") and candidate.get("breakevens"):
        structure = 16
        if candidate["type"] == "condor":
            structure = 14
    else:
        structure = 0

    # D) Event Timing 15
    event = 12 if event_ok else 5

    # E) Execution Quality 15
    execution = 13 if exec_ok else 4

    total = regime_fit + vol_edge + structure + event + execution
    return {
        "Regime": regime_fit,
        "Vol": vol_edge,
        "Structure": structure,
        "Event": event,
        "Execution": execution,
        "Total": total,
    }


def build_trade(candidate_type, legs, spot, vol, context):
    if any(x is None for x in legs):
        return None
    if any((l.get("mark") in (None, 0)) for l in legs):
        return None

    dte = min(l.get("dte") or 999 for l in legs)
    iv = vol.get("ivCurrent")
    em = expected_move(spot, iv, dte) if iv else None
    lo, hi = (spot - em, spot + em) if (spot and em) else (None, None)

    if candidate_type == "debit":
        long_c, short_c = legs
        debit = max(0.01, float(long_c["mark"]) - float(short_c["mark"]))
        width = abs(float(short_c["strike"]) - float(long_c["strike"]))
        max_loss = debit * 100
        be = float(long_c["strike"]) + debit
        breakevens = [be]
        expected_fit = (hi is not None and be <= hi)
        spread_multi = ((long_c.get("ask") - long_c.get("bid")) + (short_c.get("ask") - short_c.get("bid"))) / max(0.01, debit)
        exec_ok = spread_multi <= MULTI_LEG_SPREAD_PCT_THRESHOLD
        ticket = {
            "legs": [f"Buy {long_c['symbol']}", f"Sell {short_c['symbol']}"],
            "expiry": long_c["expiry"],
            "entryRange": [round(debit * 0.98, 2), round(debit * 1.03, 2)],
            "maxLoss": round(max_loss, 2),
            "target": round(min(width * 0.7, debit * 1.6), 2),
            "stop": round(debit * 0.6, 2),
            "invalidation": f"SPY < {round(min(long_c['strike'], short_c['strike']) - em * 0.2, 2) if em else 'ORL'}",
            "positionSizeContracts": contracts_for_risk(max_loss),
        }
    elif candidate_type == "credit":
        short_p, long_p = legs
        credit = max(0.01, float(short_p["mark"]) - float(long_p["mark"]))
        width = abs(float(short_p["strike"]) - float(long_p["strike"]))
        max_loss = (width - credit) * 100
        be = float(short_p["strike"]) - credit
        breakevens = [be]
        expected_fit = (lo is not None and be <= spot and be >= lo - em * 0.5)
        spread_multi = ((short_p.get("ask") - short_p.get("bid")) + (long_p.get("ask") - long_p.get("bid"))) / max(0.01, credit)
        exec_ok = spread_multi <= MULTI_LEG_SPREAD_PCT_THRESHOLD
        ticket = {
            "legs": [f"Sell {short_p['symbol']}", f"Buy {long_p['symbol']}"],
            "expiry": short_p["expiry"],
            "entryRange": [round(credit * 0.97, 2), round(credit * 1.03, 2)],
            "maxLoss": round(max_loss, 2),
            "target": round(credit * 0.5, 2),
            "stop": round(credit * 1.8, 2),
            "invalidation": f"SPY < {round(short_p['strike'],2)}",
            "positionSizeContracts": contracts_for_risk(max_loss),
        }
    else:
        sp, lp, sc, lc = legs
        credit = max(0.01, float(sp["mark"]) + float(sc["mark"]) - float(lp["mark"]) - float(lc["mark"]))
        wing = min(abs(float(sp["strike"]) - float(lp["strike"])), abs(float(lc["strike"]) - float(sc["strike"])))
        max_loss = (wing - credit) * 100
        be_low = float(sp["strike"]) - credit
        be_high = float(sc["strike"]) + credit
        breakevens = [be_low, be_high]
        expected_fit = (lo is not None and hi is not None and be_low <= lo and be_high >= hi)
        spread_multi = sum((l.get("ask") - l.get("bid")) for l in [sp, lp, sc, lc]) / max(0.01, credit)
        exec_ok = spread_multi <= MULTI_LEG_SPREAD_PCT_THRESHOLD
        ticket = {
            "legs": [f"Sell {sp['symbol']}", f"Buy {lp['symbol']}", f"Sell {sc['symbol']}", f"Buy {lc['symbol']}"],
            "expiry": sp["expiry"],
            "entryRange": [round(credit * 0.95, 2), round(credit * 1.05, 2)],
            "maxLoss": round(max_loss, 2),
            "target": round(credit * 0.5, 2),
            "stop": round(credit * 1.8, 2),
            "invalidation": f"SPY outside [{round(sp['strike'],2)}, {round(sc['strike'],2)}] with momentum",
            "positionSizeContracts": contracts_for_risk(max_loss),
        }

    # hard checks
    missing = []
    for req in ["openInterest", "dayVolume", "bid", "ask", "mark", "delta", "iv"]:
        if any(l.get(req) is None for l in legs):
            missing.append(req)
    event_ok = True  # calendar links present; hard binary on link availability
    score = score_components({"type": candidate_type, "maxLoss": max_loss, "breakevens": breakevens}, context, vol, exec_ok, event_ok)

    why = [
        f"Execution: spread_pct_multi={round(spread_multi*100,2)}% threshold<{MULTI_LEG_SPREAD_PCT_THRESHOLD*100:.2f}% => {'Accept' if exec_ok else 'Reject'}",
        f"Vol Edge: ivCurrent={round(vol.get('ivCurrent') or 0,4)} rv10={round(context['realizedVol'].get('rv10') or 0,4)} rv20={round(context['realizedVol'].get('rv20') or 0,4)} => {vol.get('volLabel')}",
        f"ExpectedMove: em={round(em,2) if em else None} bounds=[{round(lo,2) if lo else None},{round(hi,2) if hi else None}] breakevens={','.join(str(round(x,2)) for x in breakevens)} => {'fit' if expected_fit else 'no_fit'}",
    ]

    decision = "TRADE"
    gates = []
    if missing:
        gates.append("missing_fields")
    if not expected_fit:
        gates.append("expected_move_mismatch")
    if not exec_ok:
        gates.append("execution_poor")
    if score["Total"] < 70:
        gates.append("score_below_70")
    if ticket["positionSizeContracts"] <= 0:
        gates.append("SIZE_TOO_LARGE")

    if gates:
        decision = "PASS"

    counterfactuals = {
        "loseQuicklyIf": "Underlying moves through invalidation before theta/vega thesis materializes",
        "volBreak": "If IV shifts opposite by >2 volatility points vs entry assumption",
        "priceInvalidation": ticket["invalidation"],
        "altIfIvPlus10": "If IV +10 pts, shift to defined-risk short premium (credit spread/condor) with wider wings",
    }

    return {
        "type": candidate_type,
        "expectedMove": {
            "value": round(em, 2) if em else None,
            "upper1SD": round(hi, 2) if hi else None,
            "lower1SD": round(lo, 2) if lo else None,
            "breakevens": [round(x, 2) for x in breakevens],
            "comparison": "inside" if expected_fit else "outside_or_mismatch",
        },
        "ticket": ticket,
        "score": score,
        "whys": why,
        "counterfactuals": counterfactuals,
        "decision": decision,
        "gateFailures": gates,
        "maxLossPerContract": round(max_loss, 2),
    }


def main():
    live = load_live(LIVE_PATH)
    _ = load_chain(CHAIN_PATH)  # keep compatibility for environment

    spot = None
    if live and live.get("underlying", {}).get("mark"):
        spot = float(live["underlying"]["mark"])
    spot = spot or get_spot_from_dx(DXLINK_PATH) or get_spot_from_yahoo()

    rows = watchlist_from_live(live) if live else []
    context = regime_snapshot(spot)
    vol = vol_state(rows, context["realizedVol"].get("rv10"), context["realizedVol"].get("rv20"))

    candidates = build_candidates(rows) if rows else {"debit": (None, None), "credit": (None, None), "condor": (None, None, None, None)}

    analyses = []
    analyses.append(build_trade("debit", list(candidates["debit"]), spot, vol, context))
    analyses.append(build_trade("credit", list(candidates["credit"]), spot, vol, context))
    analyses.append(build_trade("condor", list(candidates["condor"]), spot, vol, context))
    analyses = [a for a in analyses if a is not None]
    analyses.sort(key=lambda x: x["score"]["Total"], reverse=True)

    mandatory_missing = []
    if not spot:
        mandatory_missing.append("spot")
    if not rows:
        mandatory_missing.append("live_option_rows")
    if vol.get("ivCurrent") is None:
        mandatory_missing.append("ivCurrent")
    if context["realizedVol"].get("rv10") is None and context["realizedVol"].get("rv20") is None:
        mandatory_missing.append("realized_vol")

    if mandatory_missing:
        final_decision = "NO TRADE"
    elif not analyses:
        final_decision = "PASS"
    else:
        final_decision = analyses[0]["decision"]

    output = {
        "TRADE BRIEF": {
            "Time": context["timeUserTz"],
            "Ticker": "SPY",
            "Spot": spot,
            "Regime": context["regime"],
            "Volatility State": vol,
            "Candidates": analyses,
            "Final Decision": final_decision,
            "DefaultBias": "NO TRADE",
            "missingRequiredData": mandatory_missing,
            "executionPlan": {
                "fillMethod": "Start at mid, improve by $0.01 increments, max chase = $0.05 from mid",
                "multiLegSpreadThreshold": MULTI_LEG_SPREAD_PCT_THRESHOLD,
            },
            "riskFramework": {
                "accountSize": ACCOUNT_SIZE,
                "maxRiskPct": RISK_PCT,
                "maxRiskDollars": round(ACCOUNT_SIZE * RISK_PCT, 2),
            },
        }
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
