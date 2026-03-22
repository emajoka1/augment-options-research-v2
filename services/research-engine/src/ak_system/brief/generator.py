from __future__ import annotations

import importlib.util
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
            return BriefResult(
                symbol=symbol.upper(),
                source='placeholder',
                payload={
                    'TRADE BRIEF': {
                        'Ticker': symbol.upper(),
                        'Spot': None,
                        'Candidates': [],
                        'Final Decision': 'NO TRADE',
                        'NoCandidatesReason': 'Generic brief generation is not yet extracted for non-SPY symbols.',
                        'missingRequiredData': ['symbol_specific_brief_logic_not_migrated'],
                    }
                },
            )

        payload = self._load_spy_module().generate_brief_payload()
        return BriefResult(symbol='SPY', payload=payload, source='native_module')

    def _load_spy_module(self):
        path = self.root / 'scripts' / 'spy_free_brief.py'
        spec = importlib.util.spec_from_file_location('spy_free_brief', path)
        if spec is None or spec.loader is None:
            raise RuntimeError('Unable to load spy_free_brief.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
