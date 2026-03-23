from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from src.api.main import app


@pytest.mark.asyncio
async def test_chain_endpoint_requires_live_or_snapshot_by_default(monkeypatch):
    monkeypatch.setattr('src.api.main.ALLOW_DEMO_FALLBACK', False)
    monkeypatch.setattr('src.api.main._load_local_spy_live_snapshot', lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY')
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_chain_endpoint_uses_builtin_fallback_when_enabled(monkeypatch):
    monkeypatch.setattr('src.api.main.ALLOW_DEMO_FALLBACK', True)
    monkeypatch.setattr('src.api.main._load_local_spy_live_snapshot', lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY')
    assert response.status_code == 200
    payload = response.json()
    assert payload['source'] == 'builtin_demo'
    assert payload['spot'] == 600.0


@pytest.mark.asyncio
async def test_vol_surface_requires_live_or_snapshot_by_default(monkeypatch):
    monkeypatch.setattr('src.api.main.ALLOW_DEMO_FALLBACK', False)
    monkeypatch.setattr('src.api.main._load_local_spy_live_snapshot', lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/vol-surface/SPY')
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_chain_endpoint_uses_local_live_snapshot_when_available(monkeypatch):
    from ak_system.mc_options.calibration import ChainSnapshot
    import numpy as np

    monkeypatch.setattr('src.api.main.ALLOW_DEMO_FALLBACK', False)
    monkeypatch.setattr(
        'src.api.main._load_local_spy_live_snapshot',
        lambda: ChainSnapshot(
            spot=650.0,
            strikes=np.array([645.0, 650.0, 655.0]),
            ivs=np.array([0.22, 0.23, 0.24]),
            expiries_days=np.array([7.0, 7.0, 7.0]),
            returns=None,
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY')
    assert response.status_code == 200
    payload = response.json()
    assert payload['source'] == 'dxlink_live_snapshot'
    assert payload['spot'] == 650.0


@pytest.mark.asyncio
async def test_chain_endpoint_keeps_snapshot_override(tmp_path, monkeypatch):
    monkeypatch.setattr('src.api.main.ALLOW_DEMO_FALLBACK', False)
    path = tmp_path / 'chain.json'
    path.write_text('{"spot": 500, "chain": [{"strike": 500, "iv": 0.2, "expiry_days": 7}], "returns": [0.01, 0.02]}')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY', params={'snapshot_path': str(path)})
    assert response.status_code == 200
    assert response.json()['spot'] == 500
