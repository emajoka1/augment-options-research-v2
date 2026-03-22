from __future__ import annotations

import pytest

from ak_system.brief.generator import BriefGenerator


def test_brief_generator_extracts_json_blob():
    payload = BriefGenerator._extract_json_blob('prefix {"a": 1} suffix')
    assert payload == {'a': 1}


def test_brief_generator_returns_placeholder_for_non_spy():
    result = BriefGenerator().generate('QQQ')
    assert result.symbol == 'QQQ'
    assert result.payload['TRADE BRIEF']['Final Decision'] == 'NO TRADE'


def test_brief_generator_runs_legacy_cli_for_spy(monkeypatch):
    class Result:
        returncode = 0
        stdout = '{"TRADE BRIEF": {"Ticker": "SPY", "Final Decision": "TRADE", "Candidates": []}}'
        stderr = ''

    monkeypatch.setattr('ak_system.brief.generator.subprocess.run', lambda *args, **kwargs: Result())
    result = BriefGenerator().generate('SPY')
    assert result.symbol == 'SPY'
    assert result.payload['TRADE BRIEF']['Final Decision'] == 'TRADE'
