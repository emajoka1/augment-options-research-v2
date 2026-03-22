from __future__ import annotations

import numpy as np
import pytest

from ak_system.adapters.polygon_adapter import PolygonAdapter
from ak_system.mc_options.calibration import calibrate_from_snapshot


@pytest.mark.asyncio
async def test_polygon_adapter_converts_to_chain_snapshot(monkeypatch):
    async def fake_get_json(self, path, params):
        if 'reference/options/contracts' in path:
            return {'results': [{'ticker': 'O:SPY260327C00600000', 'details': {'ticker': 'O:SPY260327C00600000', 'strike_price': 600, 'expiration_date': '2026-03-27'}}]}
        if 'snapshot/options/SPY' in path:
            return {'results': [{'details': {'ticker': 'O:SPY260327C00600000'}, 'implied_volatility': 0.25}]}
        if '/v2/last/trade/' in path:
            return {'results': {'p': 602.5, 't': 123}}
        if '/v2/aggs/ticker/' in path:
            return {'results': [{'c': 600.0}, {'c': 603.0}, {'c': 601.0}]}
        raise AssertionError(path)

    monkeypatch.setattr(PolygonAdapter, '_get_json', fake_get_json)
    adapter = PolygonAdapter(api_key='test')
    snapshot = await adapter.get_options_chain('SPY')
    assert snapshot.spot == 602.5
    assert snapshot.strikes.tolist() == [600.0]
    assert snapshot.ivs.tolist() == [0.25]


@pytest.mark.asyncio
async def test_polygon_adapter_returns_feed_calibrates(monkeypatch):
    async def fake_get_json(self, path, params):
        if 'reference/options/contracts' in path:
            return {'results': [{'ticker': 'O:SPY260327C00600000', 'details': {'ticker': 'O:SPY260327C00600000', 'strike_price': 600, 'expiration_date': '2026-03-27'}}]}
        if 'snapshot/options/SPY' in path:
            return {'results': [{'details': {'ticker': 'O:SPY260327C00600000'}, 'implied_volatility': 0.25}]}
        if '/v2/last/trade/' in path:
            return {'results': {'p': 600.0, 't': 123}}
        if '/v2/aggs/ticker/' in path:
            closes = [590.0 + i for i in range(40)]
            return {'results': [{'c': c} for c in closes]}
        raise AssertionError(path)

    monkeypatch.setattr(PolygonAdapter, '_get_json', fake_get_json)
    adapter = PolygonAdapter(api_key='test')
    snapshot = await adapter.get_options_chain('SPY')
    calibrated = calibrate_from_snapshot(snapshot)
    assert calibrated.iv.iv_atm > 0
    assert calibrated.rv10 is not None


@pytest.mark.asyncio
async def test_polygon_adapter_get_returns_shape(monkeypatch):
    async def fake_get_json(self, path, params):
        if '/v2/aggs/ticker/' in path:
            return {'results': [{'c': 100.0}, {'c': 101.0}, {'c': 102.0}, {'c': 101.5}]}
        return {'results': []}

    monkeypatch.setattr(PolygonAdapter, '_get_json', fake_get_json)
    adapter = PolygonAdapter(api_key='test')
    returns = await adapter.get_returns('SPY', days=3)
    assert isinstance(returns, np.ndarray)
    assert returns.size == 3
