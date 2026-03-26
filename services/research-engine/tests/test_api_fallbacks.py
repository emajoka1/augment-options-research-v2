from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from src.api.main import app


@pytest.mark.asyncio
async def test_chain_endpoint_requires_dxlink_live(monkeypatch):
    monkeypatch.setattr('src.api.main._load_local_spy_live_snapshot', lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY')
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_chain_endpoint_uses_local_live_snapshot_when_available(monkeypatch):
    from ak_system.mc_options.calibration import ChainSnapshot
    import numpy as np

    monkeypatch.setattr('src.api.main._load_live_status', lambda: {'health': {'ok': True, 'stale': False}})
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
async def test_vol_surface_requires_dxlink_live(monkeypatch):
    monkeypatch.setattr('src.api.main._load_local_spy_live_snapshot', lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/vol-surface/SPY')
    assert response.status_code == 503
