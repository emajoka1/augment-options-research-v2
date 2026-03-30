from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_LIVE_DATA_DIR = Path.home() / 'lab' / 'data' / 'tastytrade'


@dataclass(frozen=True)
class DxlinkLivePaths:
    data_dir: Path
    snapshot: Path
    candles: Path
    daily_closes: Path
    status: Path



def build_dxlink_live_paths() -> DxlinkLivePaths:
    data_dir = Path(os.environ.get('DXLINK_STREAM_OUT_DIR', str(DEFAULT_LIVE_DATA_DIR))).expanduser()
    snapshot = Path(
        os.environ.get(
            'DXLINK_STREAM_SNAPSHOT_OUT',
            os.environ.get('SPY_LIVE_OUT', str(data_dir / 'dxlink_live_snapshot.json')),
        )
    ).expanduser()
    candles = Path(
        os.environ.get(
            'DXLINK_STREAM_CANDLES_OUT',
            os.environ.get('DXLINK_CANDLE_OUT', str(data_dir / 'dxlink_live_candles.json')),
        )
    ).expanduser()
    daily_closes = Path(
        os.environ.get('DXLINK_STREAM_DAILY_CLOSES_OUT', str(data_dir / 'dxlink_daily_closes.json'))
    ).expanduser()
    status = Path(
        os.environ.get('DXLINK_STREAM_STATUS_OUT', str(data_dir / 'dxlink_live_status.json'))
    ).expanduser()
    return DxlinkLivePaths(data_dir=data_dir, snapshot=snapshot, candles=candles, daily_closes=daily_closes, status=status)


DXLINK_LIVE_PATHS = build_dxlink_live_paths()



def load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
