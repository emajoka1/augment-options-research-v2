#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ak_system.live_paths import DXLINK_LIVE_PATHS, load_json_file

CANDLE_SCRIPT = os.environ.get('DXLINK_CANDLES_SCRIPT', str(ROOT / 'scripts' / 'dxlink_candles.cjs'))
CANDLE_OUT = Path(os.environ.get('DXLINK_CANDLE_OUT', str(Path.home() / 'lab/data/tastytrade/dxlink_candles.json'))).expanduser()
DAILY_OUT = Path(os.environ.get('DXLINK_STREAM_DAILY_CLOSES_OUT', str(DXLINK_LIVE_PATHS.daily_closes))).expanduser()
LOOKBACK_DAYS = int(os.environ.get('DXLINK_DAILY_BACKFILL_DAYS', '45'))
MARKET_TZ = ZoneInfo('America/New_York')


def run_backfill() -> None:
    from_time_ms = int((datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).timestamp() * 1000)
    env = os.environ.copy()
    env['DXLINK_CANDLE_FROM_TIME'] = str(from_time_ms)
    env['DXLINK_CANDLE_OUT'] = str(CANDLE_OUT)
    subprocess.run(['node', CANDLE_SCRIPT], cwd=str(ROOT), env=env, check=True)


def collapse_to_daily(candles_payload: dict) -> list[dict]:
    rows = candles_payload.get('candles') or []
    now_utc = datetime.now(timezone.utc)
    by_day: dict[str, tuple[int, float]] = {}
    for row in rows:
        raw_close = row.get('close')
        raw_time = row.get('time')
        try:
            close = float(raw_close)
            ts = int(raw_time)
        except Exception:
            continue
        if not math.isfinite(close):
            continue
        dt_utc = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        if dt_utc > now_utc + timedelta(minutes=5):
            continue
        day = dt_utc.astimezone(MARKET_TZ).date().isoformat()
        existing = by_day.get(day)
        if existing is None or ts > existing[0]:
            by_day[day] = (ts, close)
    return [
        {'date': day, 'time': ts, 'close': close}
        for day, (ts, close) in sorted(by_day.items(), key=lambda item: item[1][0])
    ]


def main() -> None:
    run_backfill()
    payload = load_json_file(CANDLE_OUT) or {}
    closes = collapse_to_daily(payload)
    DAILY_OUT.parent.mkdir(parents=True, exist_ok=True)
    DAILY_OUT.write_text(json.dumps({
        'source': 'dxlink-daily-backfill',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'symbol': payload.get('symbol', 'SPY{=5m}'),
        'timezone': 'America/New_York',
        'lookbackDays': LOOKBACK_DAYS,
        'closes': closes,
    }, indent=2))
    print(json.dumps({'ok': True, 'dailyOut': str(DAILY_OUT), 'closes': len(closes)}, indent=2))


if __name__ == '__main__':
    main()
