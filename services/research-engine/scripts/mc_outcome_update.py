#!/usr/bin/env python3
"""Backfill outcome checkpoints for MC signals.

Uses Yahoo chart data (no API key) to evaluate T+30m, T+2h, and same-day close.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "snapshots" / "mc_runs.jsonl"
OUT = ROOT / "snapshots" / "mc_outcomes.jsonl"


def http_json(url: str, timeout: int = 10):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def save_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def fetch_intraday(symbol: str, start_ts: int, end_ts: int):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start_ts}&period2={end_ts}&interval=1m"
    )
    d = http_json(url)
    result = d.get("chart", {}).get("result") or []
    if not result:
        return []
    r0 = result[0]
    tss = r0.get("timestamp") or []
    closes = ((r0.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out = []
    for i, ts in enumerate(tss):
        if i < len(closes) and isinstance(closes[i], (int, float)):
            out.append((int(ts), float(closes[i])))
    return out


def fetch_daily(symbol: str, start_ts: int, end_ts: int):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d"
    )
    d = http_json(url)
    result = d.get("chart", {}).get("result") or []
    if not result:
        return []
    r0 = result[0]
    tss = r0.get("timestamp") or []
    closes = ((r0.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out = []
    for i, ts in enumerate(tss):
        if i < len(closes) and isinstance(closes[i], (int, float)):
            out.append((int(ts), float(closes[i])))
    return out


def nearest_after(series, target_ts: int, max_slip_sec: int = 1800):
    for ts, px in series:
        if ts >= target_ts and (ts - target_ts) <= max_slip_sec:
            return px
    return None


def main() -> int:
    runs = load_jsonl(RUNS)
    if not runs:
        print("No runs found")
        return 0

    existing = {r.get("signal_timestamp"): r for r in load_jsonl(OUT) if r.get("signal_timestamp")}
    now = datetime.now(timezone.utc)

    for r in runs:
        ts = r.get("timestamp")
        spot0 = r.get("spot")
        if not ts or not isinstance(spot0, (int, float)):
            continue

        sig = parse_iso(ts)
        key = ts
        row = existing.get(key, {
            "signal_timestamp": key,
            "action_state": r.get("action_state"),
            "final_decision": r.get("final_decision"),
            "spot0": float(spot0),
        })

        start = int((sig - timedelta(minutes=10)).timestamp())
        end = int((max(now, sig + timedelta(hours=3))).timestamp())
        intraday = fetch_intraday("SPY", start, end)

        t30 = int((sig + timedelta(minutes=30)).timestamp())
        t120 = int((sig + timedelta(hours=2)).timestamp())
        p30 = nearest_after(intraday, t30)
        p120 = nearest_after(intraday, t120)

        if p30 is not None:
            row["px_30m"] = p30
            row["ret_30m"] = (p30 / float(spot0)) - 1.0
        if p120 is not None:
            row["px_2h"] = p120
            row["ret_2h"] = (p120 / float(spot0)) - 1.0

        dstart = int(datetime(sig.year, sig.month, sig.day, tzinfo=timezone.utc).timestamp())
        dend = int((datetime(sig.year, sig.month, sig.day, tzinfo=timezone.utc) + timedelta(days=3)).timestamp())
        daily = fetch_daily("SPY", dstart, dend)
        if daily:
            # first available close on/after signal day
            row["px_eod"] = daily[0][1]
            row["ret_eod"] = (daily[0][1] / float(spot0)) - 1.0

        existing[key] = row

    merged = sorted(existing.values(), key=lambda x: x.get("signal_timestamp", ""))
    save_jsonl(OUT, merged)
    print(f"Updated outcomes: {len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
