from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from src.api.main import app


@pytest.mark.asyncio
async def test_chain_endpoint_uses_builtin_fallback_without_snapshot():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY')
    assert response.status_code == 200
    payload = response.json()
    assert payload['source'] == 'builtin_demo'
    assert payload['spot'] == 600.0


@pytest.mark.asyncio
async def test_vol_surface_uses_builtin_fallback_without_snapshot():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/vol-surface/SPY')
    assert response.status_code == 200
    payload = response.json()
    assert payload['symbol'] == 'SPY'
    assert 'fitted_ivs' in payload


@pytest.mark.asyncio
async def test_chain_endpoint_keeps_snapshot_override(tmp_path):
    path = tmp_path / 'chain.json'
    path.write_text('{"spot": 500, "chain": [{"strike": 500, "iv": 0.2, "expiry_days": 7}], "returns": [0.01, 0.02]}')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY', params={'snapshot_path': str(path)})
    assert response.status_code == 200
    assert response.json()['spot'] == 500
