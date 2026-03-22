from __future__ import annotations

import json
import subprocess
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

        out = subprocess.run(
            ['python3', 'scripts/spy_free_brief.py'],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or 'spy_free_brief.py failed')
        payload = self._extract_json_blob(out.stdout)
        return BriefResult(symbol='SPY', payload=payload, source='legacy_cli')

    @staticmethod
    def _extract_json_blob(text: str) -> dict[str, Any]:
        start = text.find('{')
        end = text.rfind('}')
        if start < 0 or end < start:
            raise ValueError('No JSON object found in command output')
        return json.loads(text[start : end + 1])
