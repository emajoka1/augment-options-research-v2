#!/usr/bin/env python3
import json
import math
import os
import uuid
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ak_system.risk.estimator import estimate_structure_risk, risk_cap_dollars as shared_risk_cap_dollars

CHAIN_PATH = os.environ.get("SPY_CHAIN_PATH", os.path.expanduser("~/lab/data/tastytrade/SPY_nested_chain.json"))
DXLINK_PATH = os.environ.get("SPY_DXLINK_PATH", os.path.expanduser("~/lab/data/tastytrade/dxlink_snapshot.json"))
LIVE_PATH = os.environ.get("SPY_LIVE_PATH", os.path.expanduser("~/lab/data/tastytrade/spy_live_snapshot.json"))

MIN_OI = int(os.environ.get("SPY_MIN_OI", "1000"))
MIN_VOL = int(os.environ.get("SPY_MIN_VOL", "100"))
MAX_SPREAD_PCT = float(os.environ.get("SPY_MAX_SPREAD_PCT", "0.10"))
MULTI_LEG_SPREAD_PCT_THRESHOLD = float(os.environ.get("SPY_MULTI_LEG_MAX_SPREAD_PCT", "0.05"))
ACCOUNT_SIZE = float(os.environ.get("SPY_ACCOUNT_SIZE", "10000"))
RISK_PCT = float(os.environ.get("SPY_RISK_PCT", "0.025"))
MAX_RISK_DOLLARS = float(os.environ.get("SPY_MAX_RISK_DOLLARS", "250"))
MIN_DEBIT = float(os.environ.get("SPY_MIN_DEBIT", "0.05"))
MIN_CREDIT = float(os.environ.get("SPY_MIN_CREDIT", "0.05"))
MAX_SPREAD_BPS = float(os.environ.get("SPY_MAX_SPREAD_BPS", "25"))


def risk_cap_dollars() -> float:
    return shared_risk_cap_dollars(ACCOUNT_SIZE, RISK_PCT, MAX_RISK_DOLLARS)


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


def live_is_fresh(live: dict, max_age_minutes: int = 5) -> bool:
    try:
        ts = live.get("finishedAt") or live.get("startedAt")
        if not ts:
            return False
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - t <= timedelta(minutes=max_age_minutes)
    except Exception:
        return False


def get_spot_from_dx(path: str, max_age_minutes: int = 5):
    if not os.path.exists(path):
        return None
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        if datetime.now(timezone.utc) - mtime > timedelta(minutes=max_age_minutes):
            return None
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


def get_spot_from_cboe_quote(symbol: str = "SPY"):
    try:
        d = http_json(f"https://cdn.cboe.com/api/global/delayed_quotes/quotes/{symbol}.json")
        q = d.get("data", {})
        b, a = q.get("bid"), q.get("ask")
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) and b > 0 and a > 0:
            return (float(b) + float(a)) / 2.0, "cboe_bid_ask_mid", q.get("last_trade_time")
        lp = q.get("last_trade_price") or q.get("last")
        if isinstance(lp, (int, float)) and lp > 0:
            return float(lp), "cboe_last", q.get("last_trade_time")
    except Exception:
        pass
    return None, None, None


def get_spot_from_yahoo():
    try:
        d = http_json("https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1m&range=1d")
        m = d["chart"]["result"][0].get("meta", {})
        v = float(m.get("regularMarketPrice") or m.get("previousClose"))
        return v, "yahoo_regular_market", None
    except Exception:
        return None, None, None


def get_yahoo_series(sym: str, rng: str = "3mo", interval: str = "1d"):
    try:
        d = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={rng}")
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        return q
    except Exception:
        return None


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_delta(spot: float, strike: float, t_years: float, rate: float, iv: float, side: str):
    try:
        if not spot or not strike or t_years <= 0 or iv <= 0:
            return None
        d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * t_years) / (iv * math.sqrt(t_years))
        if side == "C":
            return _norm_cdf(d1)
        return _norm_cdf(d1) - 1.0
    except Exception:
        return None


def watchlist_from_cboe_options(spot: float, symbol: str = "SPY"):
    try:
        payload = http_json(f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json")
        options = payload.get("data", {}).get("options", [])
        now = datetime.now(timezone.utc)
        rows = []

        parsed = []
        for o in options:
            osym = o.get("option")
            if not osym or len(osym) < 15:
                continue
            try:
                exp = datetime.strptime(osym[len(symbol):len(symbol)+6], "%y%m%d").date()
                side = osym[len(symbol)+6]
                strike = int(osym[-8:]) / 1000.0
            except Exception:
                continue
            dte = max(0, (exp - now.date()).days)
            parsed.append((dte, abs(strike - (spot or strike)), side, strike, osym, o))

        parsed.sort(key=lambda x: (x[0], x[1]))
        selected = parsed[:80]
        for dte, _, side, strike, osym, o in selected:
            bid = o.get("bid")
            ask = o.get("ask")
            last = o.get("last_trade_price")
            iv = o.get("iv")
            mark = None
            if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
                mark = (float(bid) + float(ask)) / 2.0
            elif isinstance(last, (int, float)):
                mark = float(last)

            t_years = max(dte / 365.0, 1.0 / 365.0)
            row = {
                "expiry": datetime.strptime(osym[len(symbol):len(symbol)+6], "%y%m%d").date().isoformat(),
                "dte": dte,
                "strike": strike,
                "side": side,
                "symbol": osym,
                "bid": float(bid) if isinstance(bid, (int, float)) else None,
                "ask": float(ask) if isinstance(ask, (int, float)) else None,
                "mark": mark,
                "last": float(last) if isinstance(last, (int, float)) else None,
                "delta": float(o.get("delta")) if isinstance(o.get("delta"), (int, float)) else _bs_delta(float(spot), strike, t_years, 0.04, float(iv), side),
                "iv": float(iv) if isinstance(iv, (int, float)) else None,
                "openInterest": int(o.get("open_interest")) if isinstance(o.get("open_interest"), (int, float)) else None,
                "dayVolume": int(o.get("volume")) if isinstance(o.get("volume"), (int, float)) else None,
                "confidence": "cboe-delayed-public",
            }
            sp = spread_pct(row)
            row["spreadPct"] = round(sp, 4) if sp is not None else None
            row["liquid"] = is_liquid(row)
            rows.append(row)

        rows.sort(key=lambda r: (r.get("dte", 999), abs((r.get("strike") or 0) - (spot or 0))))
        return rows
    except Exception:
        return []


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
    max_risk_dollars = risk_cap_dollars()
    return int(max_risk_dollars // max_loss)


def expected_move(spot, iv, dte):
    if not spot or not iv or dte is None:
        return None
    return spot * iv * math.sqrt(max(dte, 1) / 365.0)


def build_candidates(rows):
    liquid = [r for r in rows if r.get("liquid")]

    def two_leg_spread_bps(a, b, denom):
        return (((a.get("ask") - a.get("bid")) + (b.get("ask") - b.get("bid")))/max(0.01, denom))*10000.0

    # debit (risk-cap aware)
    long_c = choose_leg(liquid, "C", 5, 14, 0.35, 0.45) or choose_leg(liquid, "C", 5, 14, 0.30, 0.55)
    short_c = None
    if long_c:
        pool = [r for r in liquid if r["side"] == "C" and r["expiry"] == long_c["expiry"] and r["strike"] > long_c["strike"]]
        viable = []
        for s in pool:
            debit = max(0.01, float(long_c.get("mark") or 0) - float(s.get("mark") or 0))
            max_loss = estimate_structure_risk('debit', risk_cap=risk_cap_dollars(), debit=debit)['max_loss']
            spread_bps = two_leg_spread_bps(long_c, s, debit)
            if max_loss <= risk_cap_dollars() and debit >= MIN_DEBIT and spread_bps <= MAX_SPREAD_BPS:
                viable.append(s)
        viable.sort(key=lambda r: (abs(abs(float(r.get("delta") or 0)) - 0.2), abs((r["strike"] - long_c["strike"]) - 10)))
        short_c = viable[0] if viable else None

    # credit put (risk-cap aware)
    short_p = choose_leg(liquid, "P", 7, 35, 0.20, 0.30) or choose_leg(liquid, "P", 7, 35, 0.15, 0.35)
    long_p = None
    if short_p:
        pool = [r for r in liquid if r["side"] == "P" and r["expiry"] == short_p["expiry"] and r["strike"] < short_p["strike"]]
        viable = []
        for l in pool:
            credit = max(0.01, float(short_p.get("mark") or 0) - float(l.get("mark") or 0))
            width = abs(float(short_p["strike"]) - float(l["strike"]))
            max_loss = estimate_structure_risk('credit', risk_cap=risk_cap_dollars(), width=width, credit=credit)['max_loss']
            spread_bps = two_leg_spread_bps(short_p, l, credit)
            if max_loss <= risk_cap_dollars() and credit >= MIN_CREDIT and spread_bps <= MAX_SPREAD_BPS:
                viable.append(l)
        viable.sort(key=lambda r: (abs(abs(float(r.get("delta") or 0)) - 0.12), abs((short_p["strike"] - r["strike"]) - 10)))
        long_p = viable[0] if viable else None

    # condor paired by expiry (risk-cap aware width/credit)
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
        for lc in sorted(cwing, key=lambda r: abs((r["strike"] - c["strike"]) - 5))[:4]:
            for lp in sorted(pwing, key=lambda r: abs((p["strike"] - r["strike"]) - 5))[:4]:
                credit = max(0.01, float(p.get("mark") or 0) + float(c.get("mark") or 0) - float(lp.get("mark") or 0) - float(lc.get("mark") or 0))
                wing = min(abs(float(p["strike"]) - float(lp["strike"])), abs(float(lc["strike"]) - float(c["strike"])))
                max_loss = estimate_structure_risk('condor', risk_cap=risk_cap_dollars(), wing=wing, credit=credit)['max_loss']
                spread_bps = (sum((l.get("ask") - l.get("bid")) for l in [p, lp, c, lc]) / max(0.01, credit)) * 10000.0
                ok = max_loss <= risk_cap_dollars() and credit >= MIN_CREDIT and spread_bps <= MAX_SPREAD_BPS
                if not ok:
                    continue
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


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def classify_vol_regime(current_iv, rv10, rv20, term_front_back, skew_put_call):
    base_rv = rv20 or rv10
    if current_iv is None or base_rv is None:
        return {
            "regime": "UNCLEAR",
            "ivRvRatio": None,
            "termState": "unknown",
            "skewState": "unknown",
            "explanation": "Missing IV or RV metrics"
        }

    iv_rv_ratio = current_iv / base_rv if base_rv > 0 else None
    if iv_rv_ratio is None:
        regime = "UNCLEAR"
    elif iv_rv_ratio < 0.90:
        regime = "LOW_VOL_UNDERPRICED"
    elif iv_rv_ratio <= 1.10:
        regime = "FAIR_VOL"
    elif iv_rv_ratio <= 1.35:
        regime = "RICH_VOL"
    else:
        regime = "EXTREME_VOL"

    if term_front_back is None:
        term_state = "unknown"
    elif term_front_back > 0.02:
        term_state = "backwardation_risk"
    elif term_front_back < -0.02:
        term_state = "contango_normal"
    else:
        term_state = "flat"

    if skew_put_call is None:
        skew_state = "unknown"
    elif skew_put_call > 0.02:
        skew_state = "put_skew_elevated"
    elif skew_put_call < -0.01:
        skew_state = "call_skew_elevated"
    else:
        skew_state = "balanced"

    return {
        "regime": regime,
        "ivRvRatio": iv_rv_ratio,
        "termState": term_state,
        "skewState": skew_state,
        "explanation": f"iv/base_rv={round(iv_rv_ratio,3)}"
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
    term = (near_iv - back_iv) if (near_iv is not None and back_iv is not None) else None

    classifier = classify_vol_regime(current_iv, rv10, rv20, term, skew)
    vol_label = {
        "LOW_VOL_UNDERPRICED": "cheap",
        "FAIR_VOL": "fair",
        "RICH_VOL": "expensive",
        "EXTREME_VOL": "expensive",
    }.get(classifier["regime"], "unknown")

    return {
        "ivCurrent": current_iv,
        "ivRankProxy": None,
        "ivVsRv10": (current_iv - rv10) if (current_iv and rv10) else None,
        "ivVsRv20": (current_iv - rv20) if (current_iv and rv20) else None,
        "termStructureFrontBack": term,
        "skewPutMinusCall": skew,
        "volLabel": vol_label,
        "expansionRisk": "high" if current_iv and rv20 and current_iv < rv20 else "low_or_moderate",
        "contractionRisk": "high" if current_iv and rv20 and current_iv > rv20 else "low_or_moderate",
        "classifier": classifier,
    }


def score_components(candidate, context, vol, exec_ok, event_ok):
    # Machine-weighted scoring with normalized factors, then mapped to required caps.
    risk_state = context["regime"]["riskState"]
    vol_regime = (vol.get("classifier") or {}).get("regime")
    iv_rv = (vol.get("classifier") or {}).get("ivRvRatio")

    # A) Regime Fit (25)
    regime_match = 0.0
    if candidate["type"] in ("debit", "credit") and risk_state == "Risk-on":
        regime_match = 1.0
    elif candidate["type"] == "condor" and risk_state == "Neutral":
        regime_match = 1.0
    elif risk_state == "Risk-off":
        regime_match = 0.3
    else:
        regime_match = 0.6
    regime_fit = int(round(25 * regime_match))

    # B) Volatility Edge (25)
    vol_edge_norm = 0.3
    if vol_regime == "LOW_VOL_UNDERPRICED" and candidate["type"] == "debit":
        vol_edge_norm = 0.95
    elif vol_regime in ("RICH_VOL", "EXTREME_VOL") and candidate["type"] in ("credit", "condor"):
        vol_edge_norm = 0.95
    elif vol_regime == "FAIR_VOL":
        vol_edge_norm = 0.55
    if iv_rv is not None:
        vol_edge_norm = _clip(vol_edge_norm * (1.0 if 0.75 <= iv_rv <= 1.6 else 0.8))
    vol_edge = int(round(25 * vol_edge_norm))

    # C) Structure Quality (20)
    has_defined = 1.0 if candidate.get("maxLoss") and candidate.get("breakevens") else 0.0
    structure_norm = 0.2 + 0.8 * has_defined
    if candidate["type"] == "condor":
        structure_norm *= 0.9
    structure = int(round(20 * _clip(structure_norm)))

    # D) Event Timing (15)
    event = int(round(15 * (0.85 if event_ok else 0.35)))

    # E) Execution Quality (15)
    execution = int(round(15 * (0.9 if exec_ok else 0.25)))

    total = regime_fit + vol_edge + structure + event + execution
    return {
        "Regime": regime_fit,
        "Vol": vol_edge,
        "Structure": structure,
        "Event": event,
        "Execution": execution,
        "Total": total,
        "machineFactors": {
            "regimeMatch": round(regime_match, 3),
            "volEdgeNorm": round(vol_edge_norm, 3),
            "structureNorm": round(_clip(structure_norm), 3),
            "eventNorm": 0.85 if event_ok else 0.35,
            "executionNorm": 0.9 if exec_ok else 0.25,
            "volRegime": vol_regime,
            "ivRvRatio": round(iv_rv, 3) if iv_rv is not None else None,
        }
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
        max_loss = estimate_structure_risk('debit', risk_cap=risk_cap_dollars(), debit=debit)['max_loss']
        be = float(long_c["strike"]) + debit
        breakevens = [be]
        expected_fit = (hi is not None and be <= hi)
        spread_multi = ((long_c.get("ask") - long_c.get("bid")) + (short_c.get("ask") - short_c.get("bid"))) / max(0.01, debit)
        spread_bps = spread_multi * 10000.0
        exec_ok = spread_multi <= MULTI_LEG_SPREAD_PCT_THRESHOLD and spread_bps <= MAX_SPREAD_BPS
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
        max_loss = estimate_structure_risk('credit', risk_cap=risk_cap_dollars(), width=width, credit=credit)['max_loss']
        be = float(short_p["strike"]) - credit
        breakevens = [be]
        expected_fit = (lo is not None and be <= spot and be >= lo - em * 0.5)
        spread_multi = ((short_p.get("ask") - short_p.get("bid")) + (long_p.get("ask") - long_p.get("bid"))) / max(0.01, credit)
        spread_bps = spread_multi * 10000.0
        exec_ok = spread_multi <= MULTI_LEG_SPREAD_PCT_THRESHOLD and spread_bps <= MAX_SPREAD_BPS
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
        max_loss = estimate_structure_risk('condor', risk_cap=risk_cap_dollars(), wing=wing, credit=credit)['max_loss']
        be_low = float(sp["strike"]) - credit
        be_high = float(sc["strike"]) + credit
        breakevens = [be_low, be_high]
        expected_fit = (lo is not None and hi is not None and be_low <= lo and be_high >= hi)
        spread_multi = sum((l.get("ask") - l.get("bid")) for l in [sp, lp, sc, lc]) / max(0.01, credit)
        spread_bps = spread_multi * 10000.0
        exec_ok = spread_multi <= MULTI_LEG_SPREAD_PCT_THRESHOLD and spread_bps <= MAX_SPREAD_BPS
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
        f"Execution: spread_pct_multi={round(spread_multi*100,2)}% threshold<{MULTI_LEG_SPREAD_PCT_THRESHOLD*100:.2f}% | spread_bps={round(spread_bps,1)} max_bps<={MAX_SPREAD_BPS} => {'Accept' if exec_ok else 'Reject'}",
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

    # Hard constraints for executable candidates.
    if max_loss > risk_cap_dollars():
        gates.append("risk_cap_exceeded")
    if candidate_type == "debit" and debit < MIN_DEBIT:
        gates.append("min_debit_not_met")
    if candidate_type in ("credit", "condor") and credit < MIN_CREDIT:
        gates.append("min_credit_not_met")
    if spread_bps > MAX_SPREAD_BPS:
        gates.append("spread_bps_exceeded")

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

    brief_id = f"brief_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    snapshot_id = ((live or {}).get("snapshotId") or (live or {}).get("snapshot_id")) if isinstance(live, dict) else None

    spot = None
    spot_source = None
    spot_ts = None
    live_fresh = bool(live and live_is_fresh(live))

    cboe_spot, cboe_src, cboe_ts = get_spot_from_cboe_quote("SPY")
    if cboe_spot:
        spot, spot_source, spot_ts = cboe_spot, cboe_src, cboe_ts

    if not spot and live_fresh and live.get("underlying", {}).get("mark"):
        spot = float(live["underlying"]["mark"])
        spot_source = "live_underlying_mark"
        spot_ts = live.get("finishedAt") or live.get("startedAt")

    if not spot:
        dx_spot = get_spot_from_dx(DXLINK_PATH)
        if dx_spot:
            spot = dx_spot
            spot_source = "dx_quote_mid"

    if not spot:
        y_spot, y_src, y_ts = get_spot_from_yahoo()
        if y_spot:
            spot, spot_source, spot_ts = y_spot, y_src, y_ts

    rows = watchlist_from_live(live) if live_fresh else []
    # Fallback to free/public Cboe delayed options when live snapshot is partial or empty.
    if (not rows or not any(r.get("iv") is not None for r in rows)) and spot:
        crows = watchlist_from_cboe_options(spot, "SPY")
        if crows:
            rows = crows

    context = regime_snapshot(spot)
    vol = vol_state(rows, context["realizedVol"].get("rv10"), context["realizedVol"].get("rv20"))

    candidates = build_candidates(rows) if rows else {"debit": (None, None), "credit": (None, None), "condor": (None, None, None, None)}

    analyses = []
    analyses.append(build_trade("debit", list(candidates["debit"]), spot, vol, context))
    analyses.append(build_trade("credit", list(candidates["credit"]), spot, vol, context))
    analyses.append(build_trade("condor", list(candidates["condor"]), spot, vol, context))
    analyses = [a for a in analyses if a is not None]
    analyses.sort(key=lambda x: x["score"]["Total"], reverse=True)

    # Always provide top-3 view (even if PASS) with explicit fail reasons.
    for t in ["debit", "credit", "condor"]:
        if not any(a.get("type") == t for a in analyses):
            analyses.append({
                "type": t,
                "decision": "PASS",
                "score": {"Total": 0},
                "ticket": None,
                "gateFailures": ["NO_CANDIDATES: risk_cap too low for this DTE/structure under current IV/spreads."],
                "whys": [],
                "counterfactuals": {},
                "maxLossPerContract": None,
            })
    analyses.sort(key=lambda x: x.get("score", {}).get("Total", 0), reverse=True)
    analyses = analyses[:3]

    def near_miss(a):
        gf = a.get("gateFailures") or []
        if "risk_cap_exceeded" in gf:
            return "1 strike farther OTM OR reduce width"
        if "spread_bps_exceeded" in gf:
            return "needs tighter spread (~+3% net credit/debit efficiency)"
        if "SIZE_TOO_LARGE" in gf:
            return "DTE+2 or narrower width to reduce max loss"
        if "expected_move_mismatch" in gf:
            return "DTE+2 or shift strikes 1 step"
        return "improve credit/debit by ~3% or shift 1 strike"

    closest_near_miss = {
        "type": analyses[0].get("type") if analyses else None,
        "score": analyses[0].get("score", {}).get("Total") if analyses else None,
        "gateFailures": analyses[0].get("gateFailures") if analyses else [],
        "flipHint": near_miss(analyses[0]) if analyses else None,
    }

    mandatory_missing = []
    if not spot:
        mandatory_missing.append("spot")
    if not rows:
        mandatory_missing.append("option_rows")
    if vol.get("ivCurrent") is None:
        mandatory_missing.append("ivCurrent")
    if context["realizedVol"].get("rv10") is None and context["realizedVol"].get("rv20") is None:
        mandatory_missing.append("realized_vol")

    no_candidates_reason = None
    constraint_gates = {"risk_cap_exceeded", "min_debit_not_met", "min_credit_not_met", "spread_bps_exceeded", "SIZE_TOO_LARGE"}

    if mandatory_missing:
        final_decision = "NO TRADE"
    elif not analyses:
        final_decision = "PASS"
        no_candidates_reason = "NO_CANDIDATES: risk_cap too low for this DTE/structure under current IV/spreads."
    else:
        final_decision = analyses[0]["decision"]
        if all(any("NO_CANDIDATES:" in g for g in (a.get("gateFailures") or [])) for a in analyses):
            no_candidates_reason = "NO_CANDIDATES: risk_cap too low for this DTE/structure under current IV/spreads."
        elif all((a.get("decision") != "TRADE") and any(g in constraint_gates for g in (a.get("gateFailures") or [])) for a in analyses):
            no_candidates_reason = "NO_CANDIDATES: risk_cap too low for this DTE/structure under current IV/spreads."

    output = {
        "brief_meta": {
            "brief_id": brief_id,
            "snapshot_id": snapshot_id,
            "live_path": LIVE_PATH,
            "live_fresh": live_fresh,
            "spot_source": spot_source,
            "spot_timestamp": spot_ts,
        },
        "TRADE BRIEF": {
            "Time": context["timeUserTz"],
            "Ticker": "SPY",
            "Spot": spot,
            "Regime": context["regime"],
            "Volatility State": vol,
            "Candidates": analyses,
            "ClosestNearMiss": closest_near_miss,
            "Final Decision": final_decision,
            "NoCandidatesReason": no_candidates_reason,
            "DefaultBias": "NO TRADE", 
            "missingRequiredData": mandatory_missing,
            "executionPlan": {
                "fillMethod": "Start at mid, improve by $0.01 increments, max chase = $0.05 from mid",
                "multiLegSpreadThreshold": MULTI_LEG_SPREAD_PCT_THRESHOLD,
            },
            "riskFramework": {
                "accountSize": ACCOUNT_SIZE,
                "maxRiskPct": RISK_PCT,
                "maxRiskDollars": round(risk_cap_dollars(), 2),
            },
        }
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
