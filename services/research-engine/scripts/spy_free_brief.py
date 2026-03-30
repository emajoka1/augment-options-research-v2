#!/usr/bin/env python3
import json
import math
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone, timedelta, time as dt_time
from zoneinfo import ZoneInfo
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ak_system.live_paths import DXLINK_LIVE_PATHS, load_json_file
from ak_system.risk.estimator import estimate_structure_risk, risk_cap_dollars as shared_risk_cap_dollars
from ak_system.mc_options.engine import MCEngine, MCEngineConfig
from ak_system.mc_options.pricer import bs_greeks

CHAIN_PATH = os.environ.get("SPY_CHAIN_PATH", os.path.expanduser("~/lab/data/tastytrade/SPY_nested_chain.json"))
DXLINK_PATH = os.environ.get("SPY_DXLINK_PATH", str(DXLINK_LIVE_PATHS.snapshot))
LIVE_PATH = os.environ.get("SPY_LIVE_PATH", str(DXLINK_LIVE_PATHS.snapshot))
LIVE_STATUS_PATH = str(DXLINK_LIVE_PATHS.status)
LIVE_MAX_AGE_MINUTES = int(os.environ.get("SPY_LIVE_MAX_AGE_MINUTES", "5"))
TRIGGER_LIVE_REFRESH = os.environ.get("SPY_TRIGGER_LIVE_REFRESH", "0").lower() in {"1", "true", "yes"}
LIVE_SNAPSHOT_SCRIPT = os.environ.get("SPY_LIVE_SCRIPT", str(ROOT / "scripts" / "spy_live_snapshot.cjs"))
DXLINK_CANDLES_SCRIPT = os.environ.get("DXLINK_CANDLES_SCRIPT", str(ROOT / "scripts" / "dxlink_candles.cjs"))
DXLINK_CANDLE_OUT = os.environ.get("DXLINK_CANDLE_OUT", str(DXLINK_LIVE_PATHS.candles))
DXLINK_DAILY_CLOSES_OUT = os.environ.get("DXLINK_DAILY_CLOSES_OUT", str(DXLINK_LIVE_PATHS.daily_closes))
DXLINK_DAILY_BACKFILL_SCRIPT = os.environ.get("DXLINK_DAILY_BACKFILL_SCRIPT", str(ROOT / "scripts" / "backfill_daily_closes.py"))
DXLINK_CANDLE_SYMBOL = os.environ.get("DXLINK_CANDLE_SYMBOL", "SPY{=5m}")
PORTFOLIO_CONTEXT_PATH = os.environ.get("SPY_PORTFOLIO_CONTEXT_PATH", str(ROOT / "data" / "portfolio_context.json"))
MARKET_TZ = ZoneInfo("America/New_York")
MARKET_CLOSE_ET = dt_time(16, 0)

MIN_OI = int(os.environ.get("SPY_MIN_OI", "1000"))
MIN_VOL = int(os.environ.get("SPY_MIN_VOL", "100"))
MAX_SPREAD_PCT = float(os.environ.get("SPY_MAX_SPREAD_PCT", "0.10"))
MULTI_LEG_SPREAD_PCT_THRESHOLD = float(os.environ.get("SPY_MULTI_LEG_MAX_SPREAD_PCT", "0.05"))
MULTI_LEG_SPREAD_PCT_REJECT = float(os.environ.get("SPY_MULTI_LEG_REJECT_SPREAD_PCT", "0.20"))
ACCOUNT_SIZE = float(os.environ.get("SPY_ACCOUNT_SIZE", "10000"))
RISK_PCT = float(os.environ.get("SPY_RISK_PCT", "0.025"))
MAX_RISK_DOLLARS = float(os.environ.get("SPY_MAX_RISK_DOLLARS", "250"))
MIN_DEBIT = float(os.environ.get("SPY_MIN_DEBIT", "0.05"))
MIN_CREDIT = float(os.environ.get("SPY_MIN_CREDIT", "0.05"))
MAX_SPREAD_BPS = float(os.environ.get("SPY_MAX_SPREAD_BPS", "1500"))
MC_N_BATCHES = int(os.environ.get("SPY_BRIEF_MC_N_BATCHES", "2"))
MC_PATHS_PER_BATCH = int(os.environ.get("SPY_BRIEF_MC_PATHS_PER_BATCH", "250"))
MC_DT_DAYS = float(os.environ.get("SPY_BRIEF_MC_DT_DAYS", "0.5"))
MC_N_BATCHES = int(os.environ.get("SPY_BRIEF_MC_N_BATCHES", "2"))
MC_PATHS_PER_BATCH = int(os.environ.get("SPY_BRIEF_MC_PATHS_PER_BATCH", "250"))
MC_DT_DAYS = float(os.environ.get("SPY_BRIEF_MC_DT_DAYS", "0.5"))

REGIME_STRATEGY_FIT = {
    ("Neutral", "down_or_flat"): {
        "condor": 0.7,
        "credit_put": 0.4,
        "credit_call": 0.8,
        "debit_put": 0.7,
        "debit_call": 0.3,
    },
    ("Risk-on", "up"): {
        "condor": 0.5,
        "credit_put": 0.9,
        "credit_call": 0.2,
        "debit_call": 0.9,
        "debit_put": 0.1,
    },
    ("Risk-off", "down_or_flat"): {
        "condor": 0.3,
        "credit_put": 0.2,
        "credit_call": 0.8,
        "debit_put": 0.9,
        "debit_call": 0.1,
    },
}

STRATEGY_DIRECTIONAL_BIAS = {
    'condor': 'neutral',
    'credit_put': 'bullish',
    'credit_call': 'bearish',
    'debit_call': 'bullish',
    'debit_put': 'bearish',
    'straddle': 'neutral',
    'strangle': 'neutral',
}

TREND_ALIGNMENT = {
    ('bullish', 'up'): 1.0,
    ('bullish', 'neutral'): 0.7,
    ('bullish', 'down_or_flat'): 0.2,
    ('bearish', 'down_or_flat'): 1.0,
    ('bearish', 'neutral'): 0.7,
    ('bearish', 'up'): 0.2,
    ('neutral', 'neutral'): 1.0,
    ('neutral', 'up'): 0.6,
    ('neutral', 'down_or_flat'): 0.6,
}

CRITICAL_GATES = {
    'expected_move_mismatch', 'mc:ev_gate', 'mc:cvar_worst_gate',
    'mc:pop_or_pot', 'execution_poor', 'spread_bps_exceeded'
}
WARNING_GATES = {
    'mc:ev_ci_gate', 'score_below_70'
}


def risk_cap_dollars() -> float:
    return shared_risk_cap_dollars(ACCOUNT_SIZE, RISK_PCT, MAX_RISK_DOLLARS)




def load_chain(path: str):
    with open(path) as f:
        raw = json.load(f)
    items = raw.get("data", {}).get("items", [])
    return items[0] if items else {}


def load_live(path):
    live_path = Path(path)
    if not live_path.exists():
        return None
    return load_json_file(live_path)


def live_is_fresh(live: dict, max_age_minutes: int = 5) -> bool:
    try:
        ts = live.get("generatedAt") or live.get("finishedAt") or live.get("startedAt")
        if not ts:
            return False
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - t <= timedelta(minutes=max_age_minutes)
    except Exception:
        return False


def _live_is_fresh_compat(live: dict, max_age_minutes: int = LIVE_MAX_AGE_MINUTES) -> bool:
    try:
        return bool(live_is_fresh(live, max_age_minutes))
    except TypeError:
        return bool(live_is_fresh(live))



def refresh_live_snapshot_if_needed(path: str = LIVE_PATH, max_age_minutes: int = LIVE_MAX_AGE_MINUTES):
    live = load_live(path)
    if live and _live_is_fresh_compat(live, max_age_minutes):
        return live
    if not TRIGGER_LIVE_REFRESH:
        return live
    try:
        subprocess.run(
            ["node", LIVE_SNAPSHOT_SCRIPT],
            check=True,
            cwd=str(ROOT),
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:
        return load_live(path)
    return load_live(path)



def load_live_status(path: str = LIVE_STATUS_PATH):
    return load_json_file(Path(path))




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
    rv = math.sqrt(var) * math.sqrt(252)
    assert 0.01 <= rv <= 2.00, f"rv{window} {rv} outside valid range"
    return rv


def spread_pct(row):
    b, a, m = row.get("bid"), row.get("ask"), row.get("mark")
    if b is None or a is None or m in (None, 0):
        return None
    return max(0.0, (a - b) / m)


def compute_execution_quality(legs, leg_actions):
    leg_metrics = []
    signed_mid_total = 0.0
    total_spread_cost = 0.0
    for leg, action in zip(legs, leg_actions):
        bid = _to_float(leg.get("bid"))
        ask = _to_float(leg.get("ask"))
        oi = _to_int(leg.get("openInterest")) or 0
        volume = _to_int(leg.get("dayVolume")) or 0
        if bid is None or ask is None:
            mid = None
            spread = None
            spread_pct_value = float("inf")
            spread_bps_value = float("inf")
        else:
            mid = (bid + ask) / 2.0
            spread = max(0.0, ask - bid)
            spread_pct_value = ((spread / mid) * 100.0) if mid and mid > 0 else float("inf")
            spread_bps_value = spread_pct_value * 100.0
            total_spread_cost += spread
            signed_mid_total += mid * (1.0 if action == "sell" else -1.0)

        liquid = oi > 1000 and volume > 500
        leg_metrics.append({
            "symbol": leg.get("symbol"),
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": spread,
            "spread_pct": None if not math.isfinite(spread_pct_value) else spread_pct_value,
            "spread_bps": None if not math.isfinite(spread_bps_value) else spread_bps_value,
            "oi": oi,
            "volume": volume,
            "liquid": liquid,
        })

    valid_leg_spreads = [m["spread_pct"] for m in leg_metrics if m.get("spread_pct") is not None]
    worst_leg_spread_pct = max(valid_leg_spreads) if valid_leg_spreads else None
    avg_leg_spread_pct = (sum(valid_leg_spreads) / len(valid_leg_spreads)) if valid_leg_spreads else None
    net_mid = abs(signed_mid_total)
    multi_spread_pct = ((total_spread_cost / net_mid) * 100.0) if net_mid > 0 else float("inf")

    return {
        "per_leg": leg_metrics,
        "worst_leg_spread_pct": worst_leg_spread_pct,
        "avg_leg_spread_pct": avg_leg_spread_pct,
        "multi_spread_pct": multi_spread_pct,
        "multi_spread_bps": multi_spread_pct * 100.0 if math.isfinite(multi_spread_pct) else None,
        "all_legs_liquid": all(m["liquid"] for m in leg_metrics),
    }


def _to_float(v):
    try:
        if v in (None, ""):
            return None
        return float(v)
    except Exception:
        return None


def _to_int(v):
    try:
        if v in (None, ""):
            return None
        return int(float(v))
    except Exception:
        return None


def current_market_now() -> datetime:
    override = os.environ.get("SPY_BRIEF_NOW_ET")
    if override:
        dt = datetime.fromisoformat(override)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=MARKET_TZ)
        return dt.astimezone(MARKET_TZ)
    return datetime.now(MARKET_TZ)


def compute_dte(expiry_value, now_dt: datetime | None = None) -> int | None:
    if not expiry_value:
        return None
    try:
        expiry_date = datetime.fromisoformat(str(expiry_value)).date()
    except Exception:
        return None
    now_et = (now_dt or current_market_now()).astimezone(MARKET_TZ)
    expiry_dt = datetime.combine(expiry_date, MARKET_CLOSE_ET, tzinfo=MARKET_TZ)
    delta_seconds = (expiry_dt - now_et).total_seconds()
    if delta_seconds <= 0:
        return 0
    return max(0, int(delta_seconds // 86400))


def dte_sanity_warning(expiry_value, dte: int | None) -> str | None:
    if dte is None:
        return None
    try:
        expiry_date = datetime.fromisoformat(str(expiry_value)).date()
        is_weekly = expiry_date.weekday() == 4
    except Exception:
        is_weekly = False
    if is_weekly and dte > 60:
        return f"Suspicious DTE for weekly expiry {expiry_value}: {dte}"
    if dte > 400:
        return f"Suspicious DTE for expiry {expiry_value}: {dte}"
    return None


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
    contracts = live.get("contracts", []) or live.get("optionRing", [])
    now_et = current_market_now()
    for c in contracts:
        d = data.get(c["symbol"], {})
        recomputed_dte = compute_dte(c.get("expiry"), now_et)
        row = {
            "expiry": c["expiry"], "dte": recomputed_dte, "strike": _to_float(c.get("strike")), "side": c["side"], "symbol": c["symbol"],
            "bid": _to_float(d.get("bid")), "ask": _to_float(d.get("ask")), "mark": _to_float(d.get("mark")), "last": _to_float(d.get("last")),
            "delta": _to_float(d.get("delta")), "iv": _to_float(d.get("iv")), "openInterest": _to_int(d.get("openInterest")), "dayVolume": _to_int(d.get("dayVolume")),
            "confidence": "dxlink-live",
        }
        warning = dte_sanity_warning(c.get("expiry"), recomputed_dte)
        if warning:
            row["dteWarning"] = warning
        sp = spread_pct(row)
        row["spreadPct"] = round(sp, 4) if sp is not None else None
        row["liquid"] = is_liquid(row)
        rows.append(row)
    rows.sort(key=lambda r: (r.get("dte", 999), -(r.get("dayVolume") or 0), -(r.get("openInterest") or 0)))
    return rows


def canonical_dte_summary(rows):
    valid = [r for r in rows if r.get("expiry") and r.get("dte") is not None]
    if not valid:
        return None
    grouped: dict[str, int] = {}
    for row in valid:
        expiry = str(row["expiry"])
        dte = int(row["dte"])
        grouped[expiry] = min(grouped.get(expiry, dte), dte)
    return {
        "generatedAtEt": current_market_now().isoformat(timespec="seconds"),
        "byExpiry": grouped,
        "nearestExpiry": min(grouped, key=lambda k: grouped[k]) if grouped else None,
        "nearestDte": min(grouped.values()) if grouped else None,
    }


def choose_leg(rows, side, dte_lo, dte_hi, d_lo, d_hi, require_liquid=True):
    cands = [
        r for r in rows
        if (r.get("liquid") or not require_liquid) and r.get("side") == side and r.get("delta") is not None
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


def set_trade_target(strategy_type, entry_credit, entry_debit, max_profit, dte):
    if strategy_type in ('condor', 'credit'):
        if dte <= 3:
            target_pct = 0.80
        elif dte <= 14:
            target_pct = 0.50
        elif dte <= 30:
            target_pct = 0.40
        else:
            target_pct = 0.30
        target_price = round(float(entry_credit) * (1 - target_pct), 2)
        return target_price, target_pct

    if strategy_type == 'debit':
        if dte <= 3:
            target_pct = 1.30
        elif dte <= 14:
            target_pct = 1.50
        elif dte <= 30:
            target_pct = 2.00
        else:
            target_pct = 2.50
        target_price = round(float(entry_debit) * target_pct, 2)
        return target_price, target_pct

    return None, None


def validate_pot(pop, pot, strategy_type):
    if strategy_type in ('condor', 'credit') and pop is not None and pot is not None:
        if pop > 0.60 and pot < 0.10:
            return {
                'warning': 'Target appears unrealistic — PoP is high but PoT is near zero',
                'suggestion': 'Consider relaxing target (take profits earlier)',
                'flag': 'target_unrealistic'
            }
    return None


def validate_mc_inputs(spot, iv, rv, dte, legs, strategy_type):
    errors = []
    warnings = []

    if dte < 0:
        errors.append(f"DTE is negative ({dte})")
    if dte == 0:
        warnings.append("DTE is 0 — expiry today, consider assignment risk")
    if dte > 365:
        warnings.append(f"DTE is {dte} — unusually long for this strategy")

    if iv is None or iv <= 0:
        errors.append(f"IV is non-positive ({iv})")
    elif iv > 2.0:
        errors.append(f"IV is {iv} — likely a unit error (should be decimal, e.g., 0.30)")
    elif iv < 0.05:
        warnings.append(f"IV is {iv} — unusually low, verify data source")

    if rv is None:
        warnings.append("RV is missing — proceed with caution")
    elif rv <= 0:
        errors.append(f"RV is non-positive ({rv})")
    elif rv > 2.0:
        errors.append(f"RV is {rv} — likely a unit error")

    ratio = (iv / rv) if (iv is not None and rv not in (None, 0)) else None
    if ratio is not None and ratio > 10.0:
        errors.append(f"IV/RV ratio is {ratio:.1f} — likely a unit mismatch")

    for leg in legs:
        leg_iv = _to_float(leg.get('iv'))
        leg_delta = _to_float(leg.get('delta'))
        bid = _to_float(leg.get('bid'))
        ask = _to_float(leg.get('ask'))
        if leg_iv is not None and leg_iv > 2.0:
            errors.append(f"Leg {leg.get('symbol')} IV is {leg_iv} — unit error")
        if leg_delta is not None and abs(leg_delta) > 1.0:
            errors.append(f"Leg {leg.get('symbol')} delta is {leg_delta} — impossible")
        if bid is not None and ask is not None and bid > ask:
            errors.append(f"Leg {leg.get('symbol')} bid ({bid}) > ask ({ask})")
        if bid is not None and bid < 0:
            errors.append(f"Leg {leg.get('symbol')} has negative bid")

    em = None
    if spot and iv and dte is not None:
        try:
            em = expected_move(spot, iv, dte)
        except AssertionError as exc:
            errors.append(str(exc))
    if em is not None and em > spot * 0.5:
        errors.append(f"Expected move ({em:.2f}) > 50% of spot — check IV and DTE")
    if em is not None and em <= 0:
        errors.append(f"Expected move is non-positive ({em:.2f})")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'proceed': len(errors) == 0,
    }


def compute_invalidation(strategy_type, legs, spot, dte):
    if strategy_type == 'condor':
        short_put_strike = min(l['strike'] for l in legs if l.get('side') == 'P' and l.get('action') == 'sell')
        short_call_strike = max(l['strike'] for l in legs if l.get('side') == 'C' and l.get('action') == 'sell')
        return f"SPY outside [{short_put_strike}, {short_call_strike}] with momentum", None

    if strategy_type in ('credit_put', 'credit'):
        short_strike = max(l['strike'] for l in legs if l.get('side') == 'P' and l.get('action') == 'sell')
        return f"SPY < {short_strike}", short_strike

    if strategy_type == 'credit_call':
        short_strike = min(l['strike'] for l in legs if l.get('side') == 'C' and l.get('action') == 'sell')
        return f"SPY > {short_strike}", short_strike

    if strategy_type in ('debit_call', 'debit'):
        long_strike = min(l['strike'] for l in legs if l.get('side') == 'C' and l.get('action') == 'buy')
        support_level = round(float(spot) * 0.98, 2)
        return f"SPY fails to trade above {long_strike} or drops below {support_level}", support_level

    if strategy_type == 'debit_put':
        long_strike = max(l['strike'] for l in legs if l.get('side') == 'P' and l.get('action') == 'buy')
        resistance_level = round(float(spot) * 1.02, 2)
        return f"SPY fails to trade below {long_strike} or rises above {resistance_level}", resistance_level

    return "SPY moves against position thesis", None


def validate_invalidation_level(invalidation_price, spot):
    if invalidation_price is not None:
        distance_pct = abs(float(invalidation_price) - float(spot)) / float(spot)
        if distance_pct > 0.20:
            return {
                'valid': False,
                'warning': f"Invalidation at {invalidation_price} is {distance_pct*100:.1f}% from spot — unrealistic"
            }
    return {'valid': True}


def build_counterfactuals(candidate_type, legs, ticket, expected_move_payload, spot, context):
    if not legs or not ticket:
        return {}

    dte = min((l.get('dte') or 999) for l in legs if l is not None)
    em = (expected_move_payload or {}).get('value') or 0
    em_pct = round((em / spot) * 100, 1) if spot and em else None
    rv10 = (context.get('realizedVol') or {}).get('rv10')
    rv20 = (context.get('realizedVol') or {}).get('rv20')
    rv_current = max(v for v in [rv10, rv20] if v is not None) if any(v is not None for v in [rv10, rv20]) else None
    iv_current = _to_float((expected_move_payload or {}).get('ivUsed'))
    theta_per_day = round((ticket.get('target') or 0) / max(dte, 1), 2) if ticket.get('target') is not None else None
    breakeven_days = max(1, round(dte / 2)) if dte not in (None, 999) else None

    if candidate_type == 'condor' and len(legs) >= 4:
        puts = sorted([l for l in legs if l.get('side') == 'P'], key=lambda x: x.get('strike', 0), reverse=True)
        calls = sorted([l for l in legs if l.get('side') == 'C'], key=lambda x: x.get('strike', 0))
        short_put = puts[0].get('strike') if puts else None
        long_put = puts[-1].get('strike') if puts else None
        short_call = calls[0].get('strike') if calls else None
        long_call = calls[-1].get('strike') if calls else None
        return {
            'loseQuicklyIf': f"A sharp directional move (>{em_pct}% in either direction) breaks through the short strike at {short_put}/{short_call} before theta decay offsets the loss. Gamma risk is highest in the last {min(dte, 3)} days of the trade.",
            'volBreak': f"If realized vol expands above {round((rv_current or 0)*100,1)}% (currently {round((rv_current or 0)*100,1)}%), the wings widen in value faster than theta decays the shorts. A VIX spike above 25 would likely trigger this.",
            'priceInvalidation': f"SPY closes outside [{short_put}, {short_call}]. Partial loss begins between the short and long strikes. Full max loss at [{long_put}, {long_call}].",
            'timeDecay': f"If SPY stays range-bound, this trade profits ~${theta_per_day}/day from theta. Break-even time horizon: {breakeven_days} days (all else equal).",
        }

    if candidate_type == 'credit' and len(legs) >= 2:
        short_strike = max(l.get('strike') for l in legs if l.get('side') == 'P')
        long_strike = min(l.get('strike') for l in legs if l.get('side') == 'P')
        max_loss = ticket.get('maxLoss')
        iv_break = round(((iv_current or 0) + 0.10) * 100, 1) if iv_current is not None else None
        vol_cost = round((ticket.get('entryRange', [0])[0] or 0) * 0.25, 2)
        return {
            'loseQuicklyIf': f"SPY drops below {short_strike} with momentum. A gap down through {long_strike} produces max loss of ${max_loss}. Most dangerous scenario: overnight gap on negative news with no chance to manage.",
            'volBreak': f"IV expansion of +10.0pts increases the short put value faster than theta decay. At current IV ({round((iv_current or 0)*100,1)}%), a move to {iv_break}% would add ~${vol_cost} to the spread's mark-to-market loss.",
            'priceInvalidation': f"SPY below {short_strike}. Partial loss between {short_strike} and {long_strike}. Full max loss of ${max_loss} below {long_strike}.",
        }

    if candidate_type == 'debit' and len(legs) >= 2:
        long_strike = min(l.get('strike') for l in legs if l.get('side') == 'C')
        breakeven = ((expected_move_payload or {}).get('breakevens') or [None])[0]
        max_loss = ticket.get('maxLoss')
        required_move = round(max(0, ((breakeven or long_strike) - spot) / spot * 100), 1) if spot and (breakeven or long_strike) else None
        theta_per_day = round((ticket.get('entryRange', [0,0])[1] - ticket.get('entryRange', [0,0])[0]) / max(dte,1), 2) if ticket.get('entryRange') else None
        vol_drop = 10.0
        vega_loss = round((ticket.get('entryRange', [0])[0] or 0) * 0.15, 2)
        return {
            'loseQuicklyIf': f"SPY fails to move above {long_strike} by expiry. With {dte} DTE, theta decay costs ~${theta_per_day}/day. The trade needs a {required_move}% move in {dte} days to profit.",
            'volBreak': f"IV contraction (vol crush) reduces the value of both legs, but hurts the long leg more. A {vol_drop}pt IV drop costs ~${vega_loss} in value. Avoid holding through known vol-crush events (earnings, FOMC).",
            'priceInvalidation': f"SPY below {breakeven} at expiry. Max loss of ${max_loss} occurs if SPY is at or below {long_strike} at expiry.",
        }

    return {}


def identify_dominant_risk(dte, net_gamma, net_theta, net_vega):
    if dte <= 3:
        return 'GAMMA'
    if dte <= 14:
        return 'THETA'
    return 'VEGA'


def classify_gamma_risk(net_gamma, dte, spot):
    gamma_dollar = abs(net_gamma) * spot * spot * 0.01
    if dte <= 1 and gamma_dollar > 50:
        return 'EXTREME'
    if dte <= 3 and gamma_dollar > 30:
        return 'HIGH'
    if gamma_dollar > 15:
        return 'MODERATE'
    return 'LOW'


def compute_position_greeks(legs, spot, dte, entry_cost=0.0):
    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0
    for leg in legs:
        action = leg.get('action', 'buy')
        sign = 1.0 if action == 'buy' else -1.0
        delta = _to_float(leg.get('delta')) or 0.0
        gamma = _to_float(leg.get('gamma')) or 0.0
        theta = _to_float(leg.get('theta')) or 0.0
        vega = _to_float(leg.get('vega')) or 0.0
        net_delta += delta * sign * 100.0
        net_gamma += gamma * sign * 100.0
        net_theta += theta * sign * 100.0
        net_vega += vega * sign * 100.0

    theta_per_day = round(net_theta, 2)
    days_to_breakeven = round(abs(entry_cost / net_theta), 1) if net_theta not in (0, None) else None
    dominant = identify_dominant_risk(dte, net_gamma, net_theta, net_vega)
    return {
        'netDelta': round(net_delta, 2),
        'netDeltaDollars': round(net_delta * spot, 2),
        'netGamma': round(net_gamma, 6),
        'gammaRisk': classify_gamma_risk(net_gamma, dte, spot),
        'netTheta': round(net_theta, 2),
        'thetaPerDay': theta_per_day,
        'daysToBreakeven': days_to_breakeven,
        'netVega': round(net_vega, 2),
        'vegaDollarImpact': round(net_vega * 0.01, 2),
        'dominantRiskFactor': dominant,
    }


def enrich_leg_greeks(leg, spot, dte, r=0.03, q=0.013):
    enriched = dict(leg)
    gamma = _to_float(enriched.get('gamma'))
    theta = _to_float(enriched.get('theta'))
    vega = _to_float(enriched.get('vega'))
    delta = _to_float(enriched.get('delta'))
    iv = _to_float(enriched.get('iv'))
    strike = _to_float(enriched.get('strike'))
    side = 'call' if str(enriched.get('side')).upper() == 'C' else 'put'
    expiry_years = max(float(dte or 1) / 365.0, 1e-6)

    if iv is not None and strike is not None and any(v is None for v in [delta, gamma, theta, vega]):
        try:
            g = bs_greeks(float(spot), float(strike), r, q, float(iv), expiry_years, side)
            if delta is None:
                enriched['delta'] = g.delta
            if gamma is None:
                enriched['gamma'] = g.gamma
            if theta is None:
                enriched['theta'] = g.theta_daily
            if vega is None:
                enriched['vega'] = g.vega
        except Exception:
            pass
    return enriched


def is_highly_correlated(underlying_a, underlying_b):
    a = str(underlying_a or '').upper()
    b = str(underlying_b or '').upper()
    if a == b:
        return True
    corr_clusters = [
        {'SPY', 'SPX', 'ES', 'QQQ', 'IWM'},
    ]
    return any(a in cluster and b in cluster for cluster in corr_clusters)


def load_portfolio_context(path=PORTFOLIO_CONTEXT_PATH):
    p = Path(path)
    if not p.exists():
        return None
    return load_json_file(p)


def evaluate_portfolio_context(new_trade, existing_positions, portfolio_value):
    current_delta = sum(float(p.get('net_delta', 0.0)) for p in existing_positions)
    new_delta = current_delta + float(new_trade.get('net_delta', 0.0))
    spy_exposure = sum(abs(float(p.get('notional', 0.0))) for p in existing_positions if str(p.get('underlying', '')).upper() == 'SPY')
    new_spy_exposure = spy_exposure + abs(float(new_trade.get('notional', 0.0)))
    concentration_pct = (new_spy_exposure / portfolio_value) if portfolio_value else None
    correlated_risk = sum(
        float(p.get('max_loss', 0.0)) for p in existing_positions
        if p.get('underlying') == new_trade.get('underlying') or is_highly_correlated(p.get('underlying'), new_trade.get('underlying'))
    )
    total_risk = sum(float(p.get('max_loss', 0.0)) for p in existing_positions) + float(new_trade.get('max_loss', 0.0))
    portfolio_risk_pct = (total_risk / portfolio_value) if portfolio_value else None

    warnings = []
    if concentration_pct is not None and concentration_pct > 0.30:
        warnings.append(f'SPY concentration would rise to {round(concentration_pct*100,1)}% of portfolio value')
    if portfolio_risk_pct is not None and portfolio_risk_pct > 0.05:
        warnings.append(f'Total defined risk would reach {round(portfolio_risk_pct*100,1)}% of portfolio value')
    if abs(new_delta - current_delta) > 50:
        warnings.append(f'Portfolio delta would shift by {round(new_delta - current_delta,2)}')

    return {
        'currentDelta': round(current_delta, 2),
        'newDelta': round(new_delta, 2),
        'deltaShift': round(new_delta - current_delta, 2),
        'concentrationPct': round(concentration_pct, 4) if concentration_pct is not None else None,
        'correlatedRisk': round(correlated_risk, 2),
        'totalPortfolioRisk': round(portfolio_risk_pct, 4) if portfolio_risk_pct is not None else None,
        'warnings': warnings,
    }


def expected_move(spot, iv, dte):
    if not spot or not iv or dte is None:
        return None
    em = spot * iv * math.sqrt(max(dte, 1) / 365.0)
    assert em > 0, "EM must be positive"
    assert em < spot * 0.5, f"EM {em} > 50% of spot {spot} — likely a bug"
    assert (spot - em) > 0, f"Lower 1SD {spot - em} is negative — impossible for equity"
    assert (spot + em) > spot, "Upper 1SD must be above spot"
    assert (spot - em) < spot, "Lower 1SD must be below spot"
    return em


def atm_iv_for_expected_move(rows, spot, dte):
    if not rows or spot in (None, 0) or dte is None:
        return None

    same_dte = [r for r in rows if r.get("iv") is not None and r.get("strike") is not None and r.get("dte") == dte]
    pool = same_dte or [r for r in rows if r.get("iv") is not None and r.get("strike") is not None]
    if not pool:
        return None

    valid = []
    for row in pool:
        iv = _to_float(row.get("iv"))
        strike = _to_float(row.get("strike"))
        if iv is None or strike is None:
            continue
        if iv <= 0:
            continue
        if iv > 1.5:
            iv = iv / 100.0 if iv > 3.0 else iv
        valid.append({**row, "iv": iv, "strike": strike})

    if not valid:
        return None

    below = [r for r in valid if r["strike"] <= spot]
    above = [r for r in valid if r["strike"] >= spot]
    nearest_below = min(below, key=lambda r: (abs(r["strike"] - spot), r.get("dte", 999))) if below else None
    nearest_above = min(above, key=lambda r: (abs(r["strike"] - spot), r.get("dte", 999))) if above else None

    if nearest_below and nearest_above:
        if nearest_below["strike"] == nearest_above["strike"]:
            return (nearest_below["iv"] + nearest_above["iv"]) / 2.0
        dist_total = abs(spot - nearest_below["strike"]) + abs(nearest_above["strike"] - spot)
        if dist_total == 0:
            return (nearest_below["iv"] + nearest_above["iv"]) / 2.0
        weight_below = abs(nearest_above["strike"] - spot) / dist_total
        weight_above = abs(spot - nearest_below["strike"]) / dist_total
        return nearest_below["iv"] * weight_below + nearest_above["iv"] * weight_above

    single = nearest_below or nearest_above
    return single["iv"] if single else None


def normalize_iv_decimal(iv_value):
    iv = _to_float(iv_value)
    if iv is None:
        return None
    if iv > 2.0:
        iv = iv / 100.0
    assert 0.01 <= iv <= 2.00, f"ivCurrent {iv} is outside valid range — unit error"
    return iv


def aggregate_iv_current(rows, spot):
    if not rows or spot in (None, 0):
        return None

    valid = []
    for row in rows:
        strike = _to_float(row.get("strike"))
        iv = normalize_iv_decimal(row.get("iv")) if row.get("iv") is not None else None
        dte = _to_int(row.get("dte"))
        side = row.get("side")
        if strike is None or iv is None or dte is None or side not in {"P", "C"}:
            continue
        if dte <= 0:
            continue
        valid.append({**row, "strike": strike, "iv": iv, "dte": dte})

    if not valid:
        return None

    expiries = sorted({(r.get("expiry"), r.get("dte")) for r in valid if r.get("expiry")})
    best_pair = None
    for expiry, dte in expiries:
        same_expiry = [r for r in valid if r.get("expiry") == expiry and r.get("dte") == dte]
        puts = [r for r in same_expiry if r.get("side") == "P"]
        calls = [r for r in same_expiry if r.get("side") == "C"]
        if not puts or not calls:
            continue
        atm_put = min(puts, key=lambda r: abs(r["strike"] - spot))
        atm_call = min(calls, key=lambda r: abs(r["strike"] - spot))
        score = abs(atm_put["strike"] - spot) + abs(atm_call["strike"] - spot)
        if best_pair is None or (dte, score) < (best_pair[0], best_pair[1]):
            best_pair = (dte, score, atm_put, atm_call)

    if best_pair:
        _, _, atm_put, atm_call = best_pair
        return (atm_put["iv"] + atm_call["iv"]) / 2.0

    weighted_numer = sum(r["iv"] * max(1, _to_int(r.get("dayVolume")) or 0) for r in valid)
    weighted_denom = sum(max(1, _to_int(r.get("dayVolume")) or 0) for r in valid)
    return (weighted_numer / weighted_denom) if weighted_denom else None


def build_candidates(rows):
    liquid = [r for r in rows if r.get("liquid")]

    def choose_best_across_windows(side, windows, delta_targets):
        for dte_lo, dte_hi in windows:
            for d_lo, d_hi in delta_targets:
                leg = choose_leg(liquid, side, dte_lo, dte_hi, d_lo, d_hi)
                if leg:
                    return leg
        return None

    # trader-realistic DTE bands
    debit_windows = [(7, 21), (22, 35), (36, 45)]
    credit_windows = [(14, 35), (7, 21), (36, 45)]
    condor_windows = [(14, 45), (7, 21)]

    # debit
    long_c = choose_best_across_windows("C", debit_windows, [(0.35, 0.45), (0.30, 0.55), (0.20, 0.60)])
    short_c = None
    if long_c:
        pool = [r for r in liquid if r["side"] == "C" and r["expiry"] == long_c["expiry"] and r["strike"] > long_c["strike"]]
        pool.sort(key=lambda r: (abs(abs(float(r.get("delta") or 0)) - 0.2), abs((r["strike"] - long_c["strike"]) - 10), -(r.get("dayVolume") or 0)))
        short_c = pool[0] if pool else None

    # credit put
    short_p = choose_best_across_windows("P", credit_windows, [(0.20, 0.30), (0.15, 0.35), (0.10, 0.40)])
    long_p = None
    if short_p:
        pool = [r for r in liquid if r["side"] == "P" and r["expiry"] == short_p["expiry"] and r["strike"] < short_p["strike"]]
        pool.sort(key=lambda r: (abs(abs(float(r.get("delta") or 0)) - 0.12), abs((short_p["strike"] - r["strike"]) - 10), -(r.get("dayVolume") or 0)))
        long_p = pool[0] if pool else None

    # condor paired by expiry
    short_c_ic = short_p_ic = long_c_ic = long_p_ic = None
    expiries = sorted({r["expiry"] for r in liquid if any(lo <= (r.get("dte") or 999) <= hi for lo, hi in condor_windows)})
    best = None
    for exp in expiries:
        calls = [r for r in liquid if r["expiry"] == exp and r["side"] == "C" and 0.08 <= abs(float(r.get("delta") or 99)) <= 0.35]
        puts = [r for r in liquid if r["expiry"] == exp and r["side"] == "P" and 0.08 <= abs(float(r.get("delta") or 99)) <= 0.35]
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


def _load_dxlink_candles() -> list[float]:
    """Load SPY daily close prices from canonical daily-close file, with fallback collapse from intraday candles."""
    daily_data = load_json_file(Path(DXLINK_DAILY_CLOSES_OUT)) or {}
    closes_from_daily = []
    for row in daily_data.get("closes") or []:
        value = _to_float((row or {}).get("close"))
        if value is not None and math.isfinite(value):
            closes_from_daily.append(value)
    if closes_from_daily:
        return closes_from_daily

    try:
        subprocess.run(
            [sys.executable, DXLINK_DAILY_BACKFILL_SCRIPT],
            check=True,
            cwd=str(ROOT),
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        daily_data = load_json_file(Path(DXLINK_DAILY_CLOSES_OUT)) or {}
        closes_from_daily = []
        for row in daily_data.get("closes") or []:
            value = _to_float((row or {}).get("close"))
            if value is not None and math.isfinite(value):
                closes_from_daily.append(value)
        if closes_from_daily:
            return closes_from_daily
    except Exception:
        pass

    data = load_json_file(Path(DXLINK_CANDLE_OUT)) or {}
    candles = data.get("candles") or []
    daily_closes: dict[str, tuple[int, float]] = {}
    now_utc = datetime.now(timezone.utc)
    for candle in candles:
        raw = candle.get("close")
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except Exception:
            continue
        if not math.isfinite(value):
            continue
        ts = candle.get("time")
        if not isinstance(ts, (int, float)):
            continue
        dt_utc = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        if dt_utc > now_utc + timedelta(minutes=5):
            continue
        dt_et = dt_utc.astimezone(MARKET_TZ)
        day_key = dt_et.date().isoformat()
        existing = daily_closes.get(day_key)
        if existing is None or ts > existing[0]:
            daily_closes[day_key] = (int(ts), value)
    ordered_days = sorted(daily_closes)
    return [daily_closes[day][1] for day in ordered_days]


def regime_snapshot(spot):
    closes = _load_dxlink_candles()

    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else None
    trend_up = bool(ma5 and ma20 and ma5 > ma20 and closes[-1] > ma20) if closes else False

    # VIX and rates context unavailable without fallback sources — report unknown
    vix_dir = "unknown"
    rates_dir = "unknown"

    risk_regime = "Risk-on" if trend_up else "Neutral"

    metrics = [
        {"metric": "MA5-MA20", "value": round((ma5 - ma20), 3) if ma5 and ma20 else None, "threshold": ">0", "interpretation": "uptrend" if trend_up else "not-uptrend", "observedAt": datetime.now(timezone.utc).isoformat()},
        {"metric": "VIX day change", "value": None, "threshold": "<0 risk-on", "interpretation": vix_dir, "observedAt": None},
        {"metric": "US10Y day change", "value": None, "threshold": "context", "interpretation": rates_dir, "observedAt": None},
    ]

    rv10 = ann_realized_vol(closes, 10)
    rv20 = ann_realized_vol(closes, 20)

    if rv10 is not None and rv20 is not None:
        ratio = rv10 / rv20 if rv20 else None
        assert ratio is None or 0.5 <= ratio <= 2.0, f"rv10/rv20 ratio {ratio} is extreme"

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
        "dataQuality": {
            "regime": compute_data_quality_factor({"metrics": metrics}),
        },
    }


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def is_data_fresh(metric: dict, max_age_minutes: int = 15) -> bool:
    observed_at = metric.get("observedAt")
    if not observed_at:
        return False
    try:
        ts = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
    except Exception:
        return False
    return (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)) <= timedelta(minutes=max_age_minutes)


def compute_data_quality_factor(regime_data: dict) -> dict:
    metrics = ((regime_data or {}).get("metrics") or [])
    total_inputs = len(metrics)
    if total_inputs == 0:
        return {
            "availableInputs": 0,
            "freshInputs": 0,
            "totalInputs": 0,
            "completeness": 0.0,
            "freshness": 0.0,
            "qualityFactor": 0.0,
            "perMetric": [],
        }

    per_metric = []
    available_inputs = 0
    fresh_inputs = 0
    for metric in metrics:
        available = metric.get("value") is not None and metric.get("interpretation") != "unknown"
        fresh = available and is_data_fresh(metric, max_age_minutes=15)
        if available:
            available_inputs += 1
        if fresh:
            fresh_inputs += 1
        per_metric.append({
            "metric": metric.get("metric"),
            "available": available,
            "fresh": fresh,
            "value": metric.get("value"),
            "interpretation": metric.get("interpretation"),
            "observedAt": metric.get("observedAt"),
        })

    completeness = available_inputs / total_inputs
    freshness = fresh_inputs / total_inputs
    quality_factor = min(completeness, freshness)
    if quality_factor < 0.50:
        quality_factor = min(quality_factor, 0.33)

    return {
        "availableInputs": available_inputs,
        "freshInputs": fresh_inputs,
        "totalInputs": total_inputs,
        "completeness": completeness,
        "freshness": freshness,
        "qualityFactor": quality_factor,
        "perMetric": per_metric,
    }


def compute_final_score(component_scores, gate_results):
    raw_total = sum(v for k, v in component_scores.items() if k in {"Regime", "Vol", "Structure", "Event", "Execution"})
    normalized = [str(g) for g in gate_results]
    critical_gates = [g for g in normalized if g in CRITICAL_GATES]
    warning_gates = [g for g in normalized if g in WARNING_GATES]

    if len(critical_gates) >= 3:
        score_cap = 30
    elif len(critical_gates) >= 2:
        score_cap = 45
    elif len(critical_gates) >= 1:
        score_cap = 60
    elif len(warning_gates) >= 1:
        score_cap = 75
    else:
        score_cap = 100

    adjusted_total = min(raw_total, score_cap)
    return {
        "rawTotal": raw_total,
        "adjustedTotal": adjusted_total,
        "gatesPassed": len(gate_results) == 0,
        "gatePenalty": raw_total - adjusted_total,
        "criticalGateCount": len(critical_gates),
        "warningGateCount": len(warning_gates),
        "components": component_scores,
    }


def check_directional_alignment(strategy_type, trend):
    bias = STRATEGY_DIRECTIONAL_BIAS.get(strategy_type, 'neutral')
    alignment = TREND_ALIGNMENT.get((bias, trend), 0.5)
    if alignment <= 0.3:
        return {
            'aligned': False,
            'score_multiplier': alignment,
            'warning': f'{strategy_type} is {bias} but trend is {trend} — directional mismatch',
            'gate': 'directional_mismatch',
            'bias': bias,
        }
    return {
        'aligned': True,
        'score_multiplier': alignment,
        'warning': None,
        'gate': None,
        'bias': bias,
    }


def compute_vol_edge_score(iv_current, rv10, rv20, strategy_type, max_score=20):
    rv_best = max(v for v in [rv10, rv20] if v is not None) if any(v is not None for v in [rv10, rv20]) else None
    if iv_current is None or rv_best is None or rv_best <= 0:
        return 10
    iv_rv_ratio = iv_current / rv_best

    if strategy_type in ("condor", "credit"):
        if iv_rv_ratio >= 2.0:
            raw = 1.0
        elif iv_rv_ratio >= 1.5:
            raw = 0.8
        elif iv_rv_ratio >= 1.2:
            raw = 0.6
        elif iv_rv_ratio >= 1.0:
            raw = 0.4
        else:
            raw = 0.15
    elif strategy_type == "debit":
        if iv_rv_ratio <= 0.8:
            raw = 1.0
        elif iv_rv_ratio <= 1.0:
            raw = 0.7
        elif iv_rv_ratio <= 1.3:
            raw = 0.4
        else:
            raw = 0.1
    else:
        raw = 0.5

    return round(raw * max_score)


def classify_vol_regime(current_iv, rv10, rv20, term_front_back, skew_put_call, iv_rank_proxy=None):
    base_rv = rv10 if rv10 is not None else rv20
    if current_iv is None or base_rv is None or base_rv <= 0:
        return {
            "regime": "UNCLEAR",
            "ivRvRatio": None,
            "termState": "unknown",
            "skewState": "unknown",
            "explanation": "Missing IV or RV metrics"
        }

    iv_rv_ratio = current_iv / base_rv
    if iv_rv_ratio > 3.0 or (iv_rank_proxy is not None and iv_rank_proxy > 80):
        regime = "HIGH_VOL"
    elif iv_rv_ratio > 1.8 or (iv_rank_proxy is not None and iv_rank_proxy > 50):
        regime = "ELEVATED_VOL"
    elif iv_rv_ratio > 1.0:
        regime = "NORMAL_VOL"
    else:
        regime = "LOW_VOL"

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


def vol_state(rows, rv10, rv20, spot=None):
    current_iv = aggregate_iv_current(rows, spot)

    near = [r for r in rows if 4 <= (r.get("dte") or 999) <= 9 and r.get("iv") is not None and (r.get("dte") or 0) > 0]
    back = [r for r in rows if 20 <= (r.get("dte") or 999) <= 40 and r.get("iv") is not None and (r.get("dte") or 0) > 0]
    near_iv = sum(normalize_iv_decimal(r["iv"]) for r in near) / len(near) if near else None
    back_iv = sum(normalize_iv_decimal(r["iv"]) for r in back) / len(back) if back else None

    near_put = [r for r in near if r.get("side") == "P"]
    near_call = [r for r in near if r.get("side") == "C"]
    put_iv = sum(normalize_iv_decimal(r["iv"]) for r in near_put) / len(near_put) if near_put else None
    call_iv = sum(normalize_iv_decimal(r["iv"]) for r in near_call) / len(near_call) if near_call else None
    skew = (put_iv - call_iv) if put_iv is not None and call_iv is not None else None
    term = (near_iv - back_iv) if (near_iv is not None and back_iv is not None) else None

    classifier = classify_vol_regime(current_iv, rv10, rv20, term, skew)
    vol_label = {
        "LOW_VOL": "cheap",
        "NORMAL_VOL": "fair",
        "ELEVATED_VOL": "expensive",
        "HIGH_VOL": "expensive",
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
    regime = context["regime"]
    risk_state = regime["riskState"]
    trend = regime.get("trend")
    regime_quality = compute_data_quality_factor(regime)
    vol_regime = (vol.get("classifier") or {}).get("regime")
    iv_rv = (vol.get("classifier") or {}).get("ivRvRatio")

    # A) Regime Fit (25)
    strategy_key = {
        "condor": "condor",
        "debit": "debit_call",
        "credit": "credit_put",
    }.get(candidate["type"], "condor")
    directional_alignment = check_directional_alignment(strategy_key, trend)
    regime_match = REGIME_STRATEGY_FIT.get((risk_state, trend), {}).get(strategy_key, 0.5)
    regime_match *= directional_alignment["score_multiplier"]
    raw_regime_fit = int(round(25 * regime_match))
    regime_fit = int(round(raw_regime_fit * regime_quality["qualityFactor"]))

    # B) Volatility Edge (20)
    realized_vol = context.get("realizedVol") or {}
    vol_edge = compute_vol_edge_score(vol.get("ivCurrent"), realized_vol.get("rv10"), realized_vol.get("rv20"), candidate["type"], max_score=20)
    vol_edge_norm = vol_edge / 20.0

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
            "regimeDataQualityFactor": round(regime_quality["qualityFactor"], 3),
            "directionalAlignment": directional_alignment,
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
    iv = atm_iv_for_expected_move(legs, spot, dte) or vol.get("ivCurrent")
    em = expected_move(spot, iv, dte) if iv else None
    lo, hi = (spot - em, spot + em) if (spot and em) else (None, None)

    if candidate_type == "debit":
        long_c, short_c = legs
        leg_defs = [
            {**long_c, 'action': 'buy'},
            {**short_c, 'action': 'sell'},
        ]
        debit = max(0.01, float(long_c["mark"]) - float(short_c["mark"]))
        width = abs(float(short_c["strike"]) - float(long_c["strike"]))
        max_loss = estimate_structure_risk('debit', risk_cap=risk_cap_dollars(), debit=debit)['max_loss']
        be = float(long_c["strike"]) + debit
        breakevens = [be]
        expected_fit = (hi is not None and be <= hi)
        execution = compute_execution_quality([long_c, short_c], ["buy", "sell"])
        spread_multi = (execution["multi_spread_pct"] or float("inf")) / 100.0 if execution.get("multi_spread_pct") is not None else float("inf")
        spread_bps = execution.get("multi_spread_bps")
        worst_leg_spread_pct = execution.get("worst_leg_spread_pct")
        exec_ok = bool(execution.get("all_legs_liquid")) and (worst_leg_spread_pct is not None and worst_leg_spread_pct < 15.0) and (execution.get("multi_spread_pct") is not None and execution.get("multi_spread_pct") < (MULTI_LEG_SPREAD_PCT_REJECT * 100.0))
        target_price, target_pct = set_trade_target('debit', None, debit, width - debit, dte)
        invalidation_text, invalidation_price = compute_invalidation('debit_call', leg_defs, spot, dte)
        ticket = {
            "legs": [f"Buy {long_c['symbol']}", f"Sell {short_c['symbol']}"],
            "expiry": long_c["expiry"],
            "entryRange": [round(debit * 0.98, 2), round(debit * 1.03, 2)],
            "maxLoss": round(max_loss, 2),
            "target": target_price,
            "stop": round(debit * 0.6, 2),
            "invalidation": invalidation_text,
            "positionSizeContracts": contracts_for_risk(max_loss),
        }
        invalidation_validation = validate_invalidation_level(invalidation_price, spot)
    elif candidate_type == "credit":
        short_p, long_p = legs
        leg_defs = [
            {**short_p, 'action': 'sell'},
            {**long_p, 'action': 'buy'},
        ]
        credit = max(0.01, float(short_p["mark"]) - float(long_p["mark"]))
        width = abs(float(short_p["strike"]) - float(long_p["strike"]))
        max_loss = estimate_structure_risk('credit', risk_cap=risk_cap_dollars(), width=width, credit=credit)['max_loss']
        be = float(short_p["strike"]) - credit
        breakevens = [be]
        expected_fit = (lo is not None and be <= spot and be >= lo - em * 0.5)
        execution = compute_execution_quality([short_p, long_p], ["sell", "buy"])
        spread_multi = (execution["multi_spread_pct"] or float("inf")) / 100.0 if execution.get("multi_spread_pct") is not None else float("inf")
        spread_bps = execution.get("multi_spread_bps")
        worst_leg_spread_pct = execution.get("worst_leg_spread_pct")
        exec_ok = bool(execution.get("all_legs_liquid")) and (worst_leg_spread_pct is not None and worst_leg_spread_pct < 15.0) and (execution.get("multi_spread_pct") is not None and execution.get("multi_spread_pct") < (MULTI_LEG_SPREAD_PCT_REJECT * 100.0))
        target_price, target_pct = set_trade_target('credit', credit, None, credit, dte)
        invalidation_text, invalidation_price = compute_invalidation('credit_put', leg_defs, spot, dte)
        ticket = {
            "legs": [f"Sell {short_p['symbol']}", f"Buy {long_p['symbol']}"],
            "expiry": short_p["expiry"],
            "entryRange": [round(credit * 0.97, 2), round(credit * 1.03, 2)],
            "maxLoss": round(max_loss, 2),
            "target": target_price,
            "stop": round(credit * 1.8, 2),
            "invalidation": invalidation_text,
            "positionSizeContracts": contracts_for_risk(max_loss),
        }
        invalidation_validation = validate_invalidation_level(invalidation_price, spot)
    else:
        sp, lp, sc, lc = legs
        leg_defs = [
            {**sp, 'action': 'sell'},
            {**lp, 'action': 'buy'},
            {**sc, 'action': 'sell'},
            {**lc, 'action': 'buy'},
        ]
        credit = max(0.01, float(sp["mark"]) + float(sc["mark"]) - float(lp["mark"]) - float(lc["mark"]))
        wing = min(abs(float(sp["strike"]) - float(lp["strike"])), abs(float(lc["strike"]) - float(sc["strike"])))
        max_loss = estimate_structure_risk('condor', risk_cap=risk_cap_dollars(), wing=wing, credit=credit)['max_loss']
        be_low = float(sp["strike"]) - credit
        be_high = float(sc["strike"]) + credit
        breakevens = [be_low, be_high]
        expected_fit = (lo is not None and hi is not None and be_low <= lo and be_high >= hi)
        execution = compute_execution_quality([sp, lp, sc, lc], ["sell", "buy", "sell", "buy"])
        spread_multi = (execution["multi_spread_pct"] or float("inf")) / 100.0 if execution.get("multi_spread_pct") is not None else float("inf")
        spread_bps = execution.get("multi_spread_bps")
        worst_leg_spread_pct = execution.get("worst_leg_spread_pct")
        exec_ok = bool(execution.get("all_legs_liquid")) and (worst_leg_spread_pct is not None and worst_leg_spread_pct < 15.0) and (execution.get("multi_spread_pct") is not None and execution.get("multi_spread_pct") < (MULTI_LEG_SPREAD_PCT_REJECT * 100.0))
        target_price, target_pct = set_trade_target('condor', credit, None, credit, dte)
        invalidation_text, invalidation_price = compute_invalidation('condor', leg_defs, spot, dte)
        ticket = {
            "legs": [f"Sell {sp['symbol']}", f"Buy {lp['symbol']}", f"Sell {sc['symbol']}", f"Buy {lc['symbol']}"],
            "expiry": sp["expiry"],
            "entryRange": [round(credit * 0.95, 2), round(credit * 1.05, 2)],
            "maxLoss": round(max_loss, 2),
            "target": target_price,
            "stop": round(credit * 1.8, 2),
            "invalidation": invalidation_text,
            "positionSizeContracts": contracts_for_risk(max_loss),
        }
        invalidation_validation = validate_invalidation_level(invalidation_price, spot)

    # hard checks
    missing = []
    for req in ["openInterest", "dayVolume", "bid", "ask", "mark", "delta", "iv"]:
        if any(l.get(req) is None for l in legs):
            missing.append(req)
    event_ok = True  # calendar links present; hard binary on link availability
    score = score_components({"type": candidate_type, "maxLoss": max_loss, "breakevens": breakevens}, context, vol, exec_ok, event_ok)
    directional_alignment = ((score.get("machineFactors") or {}).get("directionalAlignment") or {})

    why = [
        f"Execution: worst_leg_spread_pct={round(worst_leg_spread_pct,2) if worst_leg_spread_pct is not None else None}% | avg_leg_spread_pct={round(execution.get('avg_leg_spread_pct'),2) if execution.get('avg_leg_spread_pct') is not None else None}% | multi_spread_pct={round(execution.get('multi_spread_pct'),2) if execution.get('multi_spread_pct') is not None else None}% => {'Accept' if exec_ok else 'Reject'}",
        f"Vol Edge: ivCurrent={round(vol.get('ivCurrent') or 0,4)} rv10={round(context['realizedVol'].get('rv10') or 0,4)} rv20={round(context['realizedVol'].get('rv20') or 0,4)} => {vol.get('volLabel')}",
        f"ExpectedMove: em={round(em,2) if em else None} bounds=[{round(lo,2) if lo else None},{round(hi,2) if hi else None}] breakevens={','.join(str(round(x,2)) for x in breakevens)} => {'fit' if expected_fit else 'no_fit'}",
    ]
    if not invalidation_validation.get('valid'):
        why.append(invalidation_validation['warning'])

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

    # Hard constraints for executable candidates.
    if candidate_type == "debit" and debit < MIN_DEBIT:
        gates.append("min_debit_not_met")
    if candidate_type in ("credit", "condor") and credit < MIN_CREDIT:
        gates.append("min_credit_not_met")
    if spread_bps is not None and spread_bps > MAX_SPREAD_BPS:
        gates.append("spread_bps_exceeded")
    if directional_alignment.get("gate"):
        gates.append(directional_alignment["gate"])

    if gates:
        decision = "PASS"

    enriched_leg_defs = [enrich_leg_greeks(leg, spot, dte) for leg in leg_defs]
    final_score = compute_final_score(score, gates)
    greek_entry_cost = debit if candidate_type == 'debit' else credit
    greeks = compute_position_greeks(enriched_leg_defs, spot, dte, entry_cost=greek_entry_cost)
    portfolio_context_raw = load_portfolio_context()
    if portfolio_context_raw and isinstance(portfolio_context_raw, dict):
        portfolio_context = evaluate_portfolio_context(
            {
                'underlying': 'SPY',
                'net_delta': greeks.get('netDelta', 0.0),
                'notional': greeks.get('netDeltaDollars', 0.0),
                'max_loss': round(max_loss, 2),
            },
            portfolio_context_raw.get('positions', []) or [],
            float(portfolio_context_raw.get('portfolioValue', 0.0) or 0.0),
        )
    else:
        portfolio_context = {
            'currentDelta': None,
            'newDelta': None,
            'deltaShift': None,
            'concentrationPct': None,
            'correlatedRisk': None,
            'totalPortfolioRisk': None,
            'warnings': ['Portfolio context unavailable — this trade is evaluated in isolation. Risk of over-concentration is not assessed.'],
        }

    counterfactuals = build_counterfactuals(candidate_type, legs, ticket, {
        "value": round(em, 2) if em else None,
        "breakevens": [round(x, 2) for x in breakevens],
        "ivUsed": round(iv, 4) if iv is not None else None,
    }, spot, context)

    structure_legs = []
    for leg, leg_def in zip(legs, enriched_leg_defs):
        structure_legs.append({
            "symbol": leg.get("symbol"),
            "side": leg.get("side"),
            "action": leg_def.get("action"),
            "expiry": leg.get("expiry"),
            "dte": leg.get("dte"),
            "strike": leg.get("strike"),
            "mark": leg.get("mark"),
            "bid": leg.get("bid"),
            "ask": leg.get("ask"),
            "delta": leg_def.get("delta", leg.get("delta")),
            "gamma": leg_def.get("gamma", leg.get("gamma")),
            "theta": leg_def.get("theta", leg.get("theta")),
            "vega": leg_def.get("vega", leg.get("vega")),
            "iv": leg_def.get("iv", leg.get("iv")),
            "openInterest": leg.get("openInterest"),
            "dayVolume": leg.get("dayVolume"),
        })

    return {
        "type": candidate_type,
        "expectedMove": {
            "ivUsed": round(iv, 4) if iv is not None else None,
            "dteUsed": dte,
            "value": round(em, 2) if em else None,
            "upper1SD": round(hi, 2) if hi else None,
            "lower1SD": round(lo, 2) if lo else None,
            "breakevens": [round(x, 2) for x in breakevens],
            "comparison": "inside" if expected_fit else "outside_or_mismatch",
        },
        "ticket": ticket,
        "score": {
            **score,
            "RawTotal": final_score["rawTotal"],
            "Total": final_score["adjustedTotal"],
            "AdjustedTotal": final_score["adjustedTotal"],
            "GatePenalty": final_score["gatePenalty"],
            "GatesPassed": final_score["gatesPassed"],
            "CriticalGateCount": final_score["criticalGateCount"],
            "WarningGateCount": final_score["warningGateCount"],
            "DisplayText": f"{final_score['adjustedTotal']} (raw: {final_score['rawTotal']}, penalized for {len(gates)} gate failures)" if final_score["gatePenalty"] > 0 else str(final_score["adjustedTotal"]),
            "Color": "green" if final_score["adjustedTotal"] >= 70 else ("amber" if final_score["adjustedTotal"] >= 50 else "red"),
        },
        "whys": why,
        "counterfactuals": counterfactuals,
        "decision": decision,
        "gateFailures": gates,
        "directionalAlignment": directional_alignment,
        "greeks": greeks,
        "portfolioContext": portfolio_context,
        "maxLossPerContract": round(max_loss, 2),
        "structure": {
            "name": candidate_type,
            "expiry": legs[0].get("expiry") if legs else None,
            "dte": dte,
            "legs": structure_legs,
            "pricing": {
                "spreadPctMulti": round(spread_multi * 100, 2),
                "spreadBps": round(spread_bps, 1) if spread_bps is not None else None,
                "execution": execution,
                "entryDebit": round(debit, 2) if candidate_type == "debit" else None,
                "entryCredit": round(credit, 2) if candidate_type in ("credit", "condor") else None,
                "width": round(width, 2) if candidate_type in ("debit", "credit") else round(wing, 2),
            },
        },
    }


def _candidate_structure_payload(candidate_type, legs):
    present = [leg for leg in legs if leg is not None]
    dte = min((l.get("dte") or 999) for l in present) if present else None
    expiry = present[0].get("expiry") if present else None
    leg_rows = []
    for leg in present:
        leg_rows.append({
            "symbol": leg.get("symbol"),
            "side": leg.get("side"),
            "expiry": leg.get("expiry"),
            "dte": leg.get("dte"),
            "strike": leg.get("strike"),
            "mark": leg.get("mark"),
            "bid": leg.get("bid"),
            "ask": leg.get("ask"),
            "delta": leg.get("delta"),
            "iv": leg.get("iv"),
            "openInterest": leg.get("openInterest"),
            "dayVolume": leg.get("dayVolume"),
        })

    pricing = {}
    try:
        if candidate_type == "debit" and len(present) >= 2:
            a, b = present[:2]
            debit = max(0.01, float(a.get("mark") or 0) - float(b.get("mark") or 0))
            width = abs(float(b.get("strike")) - float(a.get("strike")))
            spread_bps = (((a.get("ask") - a.get("bid")) + (b.get("ask") - b.get("bid"))) / max(0.01, debit)) * 10000.0
            pricing = {"entryDebit": round(debit, 2), "width": round(width, 2), "spreadBps": round(spread_bps, 1)}
        elif candidate_type == "credit" and len(present) >= 2:
            a, b = present[:2]
            credit = max(0.01, float(a.get("mark") or 0) - float(b.get("mark") or 0))
            width = abs(float(a.get("strike")) - float(b.get("strike")))
            spread_bps = (((a.get("ask") - a.get("bid")) + (b.get("ask") - b.get("bid"))) / max(0.01, credit)) * 10000.0
            pricing = {"entryCredit": round(credit, 2), "width": round(width, 2), "spreadBps": round(spread_bps, 1)}
        elif candidate_type == "condor" and len(present) >= 4:
            sp, lp, sc, lc = present[:4]
            credit = max(0.01, float(sp.get("mark") or 0) + float(sc.get("mark") or 0) - float(lp.get("mark") or 0) - float(lc.get("mark") or 0))
            wing = min(abs(float(sp.get("strike")) - float(lp.get("strike"))), abs(float(lc.get("strike")) - float(sc.get("strike"))))
            spread_bps = (sum((l.get("ask") - l.get("bid")) for l in [sp, lp, sc, lc]) / max(0.01, credit)) * 10000.0
            pricing = {"entryCredit": round(credit, 2), "width": round(wing, 2), "spreadBps": round(spread_bps, 1)}
    except Exception:
        pricing = pricing or {}

    return {"name": candidate_type, "expiry": expiry, "dte": dte, "legs": leg_rows, "pricing": pricing}


def _strategy_legs_for_candidate(candidate_type, legs):
    if candidate_type == "debit":
        long_c, short_c = legs
        return [
            {"side": "long", "option_type": "call", "strike": float(long_c["strike"]), "qty": 1},
            {"side": "short", "option_type": "call", "strike": float(short_c["strike"]), "qty": 1},
        ]
    if candidate_type == "credit":
        short_p, long_p = legs
        return [
            {"side": "short", "option_type": "put", "strike": float(short_p["strike"]), "qty": 1},
            {"side": "long", "option_type": "put", "strike": float(long_p["strike"]), "qty": 1},
        ]
    sp, lp, sc, lc = legs
    return [
        {"side": "short", "option_type": "put", "strike": float(sp["strike"]), "qty": 1},
        {"side": "long", "option_type": "put", "strike": float(lp["strike"]), "qty": 1},
        {"side": "short", "option_type": "call", "strike": float(sc["strike"]), "qty": 1},
        {"side": "long", "option_type": "call", "strike": float(lc["strike"]), "qty": 1},
    ]


def attach_mc_decision(candidate, legs, spot):
    if candidate is None or spot in (None, 0):
        return candidate

    dte = min((l.get("dte") or 999) for l in legs if l is not None)
    strategy_type = {"debit": "call_debit_spread", "credit": "put_credit_spread", "condor": "iron_condor"}[candidate["type"]]
    iv = (candidate.get("expectedMove") or {}).get("ivUsed")
    if iv is None:
        for leg in legs:
            iv = _to_float(leg.get("iv"))
            if iv is not None:
                break

    live = load_live(LIVE_PATH) or {}
    rows = watchlist_from_live(live) if isinstance(live, dict) else []
    closes = _load_dxlink_candles()
    returns = []
    if len(closes) >= 2:
        for a, b in zip(closes[:-1], closes[1:]):
            if a and b and a > 0 and b > 0:
                returns.append(math.log(b / a))

    rv = ann_realized_vol(closes, 10)
    mc_validation = validate_mc_inputs(float(spot), _to_float(iv), rv, int(dte), legs, candidate.get("type"))
    if not mc_validation['valid']:
        candidate["decisionSource"] = "mc_engine"
        candidate["decision"] = "PASS"
        candidate.setdefault("gateFailures", [])
        candidate["gateFailures"] = [g for g in candidate["gateFailures"] if not str(g).startswith('mc:')] + ['mc:blocked_invalid_inputs']
        candidate["mc"] = {
            "status": "BLOCKED_INVALID_INPUTS",
            "allowTrade": False,
            "dataQualityStatus": "BLOCKED_INVALID_INPUTS",
            "metrics": None,
            "multiSeedConfidence": None,
            "gates": {"allow_trade": False, "blocked_invalid_inputs": True},
            "edgeAttribution": None,
            "breakevens": None,
            "strategy": strategy_type,
            "inputValidation": mc_validation,
        }
        score = candidate.get("score") or {}
        rescored = compute_final_score(score, candidate.get("gateFailures") or [])
        candidate["score"] = {
            **score,
            "RawTotal": rescored["rawTotal"],
            "Total": rescored["adjustedTotal"],
            "AdjustedTotal": rescored["adjustedTotal"],
            "GatePenalty": rescored["gatePenalty"],
            "GatesPassed": rescored["gatesPassed"],
            "CriticalGateCount": rescored["criticalGateCount"],
            "WarningGateCount": rescored["warningGateCount"],
            "DisplayText": f"{rescored['adjustedTotal']} (raw: {rescored['rawTotal']}, penalized for {len(candidate.get('gateFailures') or [])} gate failures)" if rescored["gatePenalty"] > 0 else str(rescored["adjustedTotal"]),
            "Color": "green" if rescored["adjustedTotal"] >= 70 else ("amber" if rescored["adjustedTotal"] >= 50 else "red"),
        }
        return candidate

    snapshot_payload = {
        "spot": float(spot),
        "strikes": [float(r["strike"]) for r in rows if r.get("strike") is not None and r.get("iv") is not None],
        "ivs": [float(r["iv"]) for r in rows if r.get("strike") is not None and r.get("iv") is not None],
        "expiries_days": [float(r.get("dte") or 0) for r in rows if r.get("strike") is not None and r.get("iv") is not None],
        "returns": returns,
    }

    snapshot_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(snapshot_payload, tmp)
            snapshot_file = tmp.name

        mc_result = MCEngine().run(
            MCEngineConfig(
                symbol="SPY",
                spot=float(spot),
                expiry_days=float(max(dte, 1)),
                dt_days=MC_DT_DAYS,
                n_batches=max(1, MC_N_BATCHES),
                paths_per_batch=max(100, MC_PATHS_PER_BATCH),
                strategy_type=strategy_type,
                strategy_legs=_strategy_legs_for_candidate(candidate["type"], legs),
                snapshot_file=snapshot_file,
                write_artifacts=False,
                output_root=str(ROOT),
            )
        )
    finally:
        if snapshot_file:
            try:
                Path(snapshot_file).unlink(missing_ok=True)
            except Exception:
                pass

    candidate["decisionSource"] = "mc_engine"
    candidate["mc"] = {
        "status": mc_result.payload.get("status"),
        "allowTrade": bool(mc_result.allow_trade),
        "dataQualityStatus": mc_result.data_quality_status,
        "metrics": mc_result.payload.get("metrics"),
        "multiSeedConfidence": mc_result.payload.get("multi_seed_confidence"),
        "gates": mc_result.payload.get("gates"),
        "edgeAttribution": mc_result.payload.get("edge_attribution"),
        "breakevens": mc_result.payload.get("breakevens"),
        "strategy": mc_result.payload.get("assumptions", {}).get("strategy"),
        "inputValidation": mc_validation,
    }

    mc_gates = mc_result.payload.get("gates") or {}
    failed_mc_gates = sorted([f"mc:{k}" for k, v in mc_gates.items() if k != "allow_trade" and v is False])
    existing = [g for g in (candidate.get("gateFailures") or []) if not g.startswith("mc:")]
    candidate["gateFailures"] = existing if mc_result.allow_trade else (existing + failed_mc_gates or existing)
    candidate["decision"] = "TRADE" if mc_result.allow_trade else "PASS"

    target_validation = validate_pot(
        (mc_result.payload.get("metrics") or {}).get("pop"),
        (mc_result.payload.get("metrics") or {}).get("pot"),
        candidate.get("type"),
    )
    if target_validation:
        candidate.setdefault("warnings", []).append(target_validation)
        candidate["gateFailures"] = (candidate.get("gateFailures") or []) + [target_validation["flag"]]

    score = candidate.get("score") or {}
    rescored = compute_final_score(score, candidate.get("gateFailures") or [])
    candidate["score"] = {
        **score,
        "RawTotal": rescored["rawTotal"],
        "Total": rescored["adjustedTotal"],
        "AdjustedTotal": rescored["adjustedTotal"],
        "GatePenalty": rescored["gatePenalty"],
        "GatesPassed": rescored["gatesPassed"],
        "CriticalGateCount": rescored["criticalGateCount"],
        "WarningGateCount": rescored["warningGateCount"],
        "DisplayText": f"{rescored['adjustedTotal']} (raw: {rescored['rawTotal']}, penalized for {len(candidate.get('gateFailures') or [])} gate failures)" if rescored["gatePenalty"] > 0 else str(rescored["adjustedTotal"]),
        "Color": "green" if rescored["adjustedTotal"] >= 70 else ("amber" if rescored["adjustedTotal"] >= 50 else "red"),
    }
    return candidate


def generate_brief_payload():
    live = refresh_live_snapshot_if_needed(LIVE_PATH, max_age_minutes=LIVE_MAX_AGE_MINUTES)
    _ = load_chain(CHAIN_PATH)  # keep compatibility for environment

    brief_id = f"brief_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    live_status = load_live_status(LIVE_STATUS_PATH) or {}
    snapshot_id = ((live or {}).get("snapshotId") or (live or {}).get("snapshot_id")) if isinstance(live, dict) else None

    spot = None
    spot_source = None
    spot_ts = None
    live_fresh = bool(live and _live_is_fresh_compat(live, LIVE_MAX_AGE_MINUTES))

    if live_fresh and live.get("underlying", {}).get("mark"):
        spot = float(live["underlying"]["mark"])
        spot_source = "live_underlying_mark"
        spot_ts = live.get("finishedAt") or live.get("startedAt")

    if not spot:
        dx_spot = get_spot_from_dx(DXLINK_PATH)
        if dx_spot:
            spot = dx_spot
            spot_source = "dx_quote_mid"

    rows = watchlist_from_live(live) if live_fresh else []

    context = regime_snapshot(spot)
    try:
        vol = vol_state(rows, context["realizedVol"].get("rv10"), context["realizedVol"].get("rv20"), spot=spot)
    except TypeError:
        vol = vol_state(rows, context["realizedVol"].get("rv10"), context["realizedVol"].get("rv20"))
    dte_summary = canonical_dte_summary(rows)
    dte_warnings = sorted({r.get("dteWarning") for r in rows if r.get("dteWarning")})

    candidates = build_candidates(rows) if rows else {"debit": (None, None), "credit": (None, None), "condor": (None, None, None, None)}

    # fallback explanatory structures from raw rows even when nothing qualifies as liquid
    if rows:
        if all(x is None for x in candidates["debit"]):
            long_c_fb = choose_leg(rows, "C", 5, 14, 0.35, 0.45, require_liquid=False) or choose_leg(rows, "C", 5, 14, 0.30, 0.55, require_liquid=False)
            short_c_fb = None
            if long_c_fb:
                pool = [r for r in rows if r.get("side") == "C" and r.get("expiry") == long_c_fb.get("expiry") and (r.get("strike") or 0) > (long_c_fb.get("strike") or 0)]
                pool.sort(key=lambda r: (abs(abs(float(r.get("delta") or 0)) - 0.2), abs(((r.get("strike") or 0) - (long_c_fb.get("strike") or 0)) - 10)))
                short_c_fb = pool[0] if pool else None
            candidates["debit"] = (long_c_fb, short_c_fb)

        if all(x is None for x in candidates["credit"]):
            short_p_fb = choose_leg(rows, "P", 7, 35, 0.20, 0.30, require_liquid=False) or choose_leg(rows, "P", 7, 35, 0.15, 0.35, require_liquid=False)
            long_p_fb = None
            if short_p_fb:
                pool = [r for r in rows if r.get("side") == "P" and r.get("expiry") == short_p_fb.get("expiry") and (r.get("strike") or 0) < (short_p_fb.get("strike") or 0)]
                pool.sort(key=lambda r: (abs(abs(float(r.get("delta") or 0)) - 0.12), abs(((short_p_fb.get("strike") or 0) - (r.get("strike") or 0)) - 10)))
                long_p_fb = pool[0] if pool else None
            candidates["credit"] = (short_p_fb, long_p_fb)

        if all(x is None for x in candidates["condor"]):
            expiries = sorted({r.get("expiry") for r in rows if r.get("expiry") and 5 <= (r.get("dte") or 999) <= 30})
            best_fb = None
            for exp in expiries:
                calls = [r for r in rows if r.get("expiry") == exp and r.get("side") == "C" and 0.10 <= abs(float(r.get("delta") or 99)) <= 0.30]
                puts = [r for r in rows if r.get("expiry") == exp and r.get("side") == "P" and 0.10 <= abs(float(r.get("delta") or 99)) <= 0.30]
                if not calls or not puts:
                    continue
                c = sorted(calls, key=lambda r: abs(abs(float(r.get("delta") or 0)) - 0.18))[0]
                p = sorted(puts, key=lambda r: abs(abs(float(r.get("delta") or 0)) - 0.18))[0]
                cwing = [r for r in rows if r.get("expiry") == exp and r.get("side") == "C" and (r.get("strike") or 0) > (c.get("strike") or 0)]
                pwing = [r for r in rows if r.get("expiry") == exp and r.get("side") == "P" and (r.get("strike") or 0) < (p.get("strike") or 0)]
                if cwing and pwing:
                    lc = sorted(cwing, key=lambda r: abs(((r.get("strike") or 0) - (c.get("strike") or 0)) - 5))[0]
                    lp = sorted(pwing, key=lambda r: abs(((p.get("strike") or 0) - (r.get("strike") or 0)) - 5))[0]
                    best_fb = (p, lp, c, lc)
                    break
            if best_fb:
                candidates["condor"] = best_fb

    analyses = []
    debit_legs = list(candidates["debit"])
    credit_legs = list(candidates["credit"])
    condor_legs = list(candidates["condor"])
    analyses.append(attach_mc_decision(build_trade("debit", debit_legs, spot, vol, context), debit_legs, spot))
    analyses.append(attach_mc_decision(build_trade("credit", credit_legs, spot, vol, context), credit_legs, spot))
    analyses.append(attach_mc_decision(build_trade("condor", condor_legs, spot, vol, context), condor_legs, spot))
    analyses = [a for a in analyses if a is not None]
    analyses.sort(key=lambda x: (x.get("decision") == "TRADE", x["score"]["Total"]), reverse=True)

    # Always provide top-3 view (even if PASS) with explicit fail reasons.
    for t in ["debit", "credit", "condor"]:
        if not any(a.get("type") == t for a in analyses):
            fallback_legs = debit_legs if t == "debit" else (credit_legs if t == "credit" else condor_legs)
            analyses.append({
                "type": t,
                "decision": "PASS",
                "score": {"Total": 0},
                "ticket": None,
                "gateFailures": ["NO_CANDIDATES: no structure met liquidity/execution constraints for this setup."],
                "whys": ["Best available structure failed before candidate construction; see attempted legs/pricing below."],
                "counterfactuals": {},
                "maxLossPerContract": None,
                "structure": _candidate_structure_payload(t, fallback_legs),
            })
    analyses.sort(key=lambda x: (x.get("decision") == "TRADE", x.get("score", {}).get("Total", 0)), reverse=True)
    analyses = analyses[:3]

    def near_miss(a):
        gf = a.get("gateFailures") or []
        if "spread_bps_exceeded" in gf:
            return "needs tighter spread (~+3% net credit/debit efficiency)"
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
    constraint_gates = {"min_debit_not_met", "min_credit_not_met", "spread_bps_exceeded"}

    if mandatory_missing:
        final_decision = "NO TRADE"
    elif not analyses:
        final_decision = "PASS"
        no_candidates_reason = "NO_CANDIDATES: no structure met liquidity/execution constraints for this setup."
    else:
        final_decision = analyses[0]["decision"]
        if all(any("NO_CANDIDATES:" in g for g in (a.get("gateFailures") or [])) for a in analyses):
            no_candidates_reason = "NO_CANDIDATES: no structure met liquidity/execution constraints for this setup."
        elif all((a.get("decision") != "TRADE") and any(g in constraint_gates for g in (a.get("gateFailures") or [])) for a in analyses):
            no_candidates_reason = "NO_CANDIDATES: no structure met liquidity/execution constraints for this setup."

    output = {
        "brief_meta": {
            "brief_id": brief_id,
            "snapshot_id": snapshot_id,
            "live_path": LIVE_PATH,
            "live_candles_path": DXLINK_CANDLE_OUT,
            "live_status_path": LIVE_STATUS_PATH,
            "live_fresh": live_fresh,
            "live_status_health": live_status.get("health") if isinstance(live_status, dict) else None,
            "spot_source": spot_source,
            "spot_timestamp": spot_ts,
            "dteWarnings": dte_warnings,
            "context_data_quality": context.get("dataQuality"),
        },
        "TRADE BRIEF": {
            "Time": context["timeUserTz"],
            "Ticker": "SPY",
            "Spot": spot,
            "DTE": dte_summary,
            "DataQuality": context.get("dataQuality"),
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

    return output


def main():
    print(json.dumps(generate_brief_payload(), indent=2))


if __name__ == "__main__":
    main()
