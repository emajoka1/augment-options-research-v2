from __future__ import annotations

import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ak_system.adapters.data_provider import DataProvider


@dataclass
class BriefResult:
    symbol: str
    payload: dict[str, Any]
    source: str


class BriefGenerator:
    def __init__(self, provider: DataProvider | None = None, root: Path | None = None):
        self.provider = provider
        self.root = root or Path(__file__).resolve().parents[3]

    def generate(self, symbol: str = 'SPY') -> BriefResult:
        if symbol.upper() != 'SPY':
            raise NotImplementedError('Brief generation is currently supported for SPY only')

        payload = self._load_spy_module()['generate_brief_payload']()
        return BriefResult(symbol='SPY', payload=payload, source='native_module')

    def _load_spy_module(self):
        path = self.root / 'scripts' / 'spy_free_brief.py'
        if not path.exists():
            raise RuntimeError('Unable to load spy_free_brief.py')
        return runpy.run_path(str(path))
