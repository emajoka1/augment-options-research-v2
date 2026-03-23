from __future__ import annotations

import pytest

from ak_system.brief.generator import BriefGenerator


def test_brief_generator_rejects_non_spy():
    with pytest.raises(NotImplementedError):
        BriefGenerator().generate('QQQ')


def test_brief_generator_uses_native_module_for_spy(monkeypatch):
    class FakeModule:
        @staticmethod
        def generate_brief_payload():
            return {'TRADE BRIEF': {'Ticker': 'SPY', 'Final Decision': 'TRADE', 'Candidates': []}}

    monkeypatch.setattr(BriefGenerator, '_load_spy_module', lambda self: FakeModule())
    result = BriefGenerator().generate('SPY')
    assert result.symbol == 'SPY'
    assert result.source == 'native_module'
    assert result.payload['TRADE BRIEF']['Final Decision'] == 'TRADE'


def test_brief_generator_loads_module_path(monkeypatch, tmp_path):
    generator = BriefGenerator(root=tmp_path)

    class FakeLoader:
        def exec_module(self, module):
            module.generate_brief_payload = lambda: {'TRADE BRIEF': {'Ticker': 'SPY'}}

    class FakeSpec:
        loader = FakeLoader()

    monkeypatch.setattr('ak_system.brief.generator.importlib.util.spec_from_file_location', lambda name, path: FakeSpec())
    monkeypatch.setattr('ak_system.brief.generator.importlib.util.module_from_spec', lambda spec: type('M', (), {})())
    module = generator._load_spy_module()
    assert module.generate_brief_payload()['TRADE BRIEF']['Ticker'] == 'SPY'
