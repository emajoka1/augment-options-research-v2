from __future__ import annotations

import json
from pathlib import Path

from httpx import ASGITransport, AsyncClient
import pytest

from src.api.main import app


@pytest.fixture()
def sample_snapshot(tmp_path):
    p = tmp_path / 'chain.json'
    p.write_text(json.dumps({
        'spot': 600.0,
        'chain': [
            {'strike': 590, 'iv': 0.24, 'expiry_days': 7},
            {'strike': 600, 'iv': 0.25, 'expiry_days': 7},
            {'strike': 610, 'iv': 0.26, 'expiry_days': 7},
        ],
        'returns': [0.01] * 30,
    }))
    return p


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


@pytest.mark.asyncio
async def test_chain_endpoint(sample_snapshot):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY', params={'snapshot_path': str(sample_snapshot)})
    assert response.status_code == 200
    assert response.json()['spot'] == 600.0


@pytest.mark.asyncio
async def test_greeks_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/greeks', params={'S': 600, 'K': 600, 'r': 0.03, 'q': 0, 'sigma': 0.25, 'T': 0.0137, 'option_type': 'call'})
    assert response.status_code == 200
    assert 'price' in response.json()


@pytest.mark.asyncio
async def test_mc_run_endpoint(tmp_path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/mc/run', json={'n_batches': 1, 'paths_per_batch': 100, 'expiry_days': 1, 'dt_days': 1, 'output_root': str(tmp_path), 'write_artifacts': False})
    assert response.status_code == 200
    assert 'metrics' in response.json()


@pytest.mark.asyncio
async def test_vol_surface_and_risk_endpoints(sample_snapshot):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        vs = await client.get('/v1/vol-surface/SPY', params={'snapshot_path': str(sample_snapshot)})
        rk = await client.get('/v1/risk/estimate', params={'structure_type': 'iron_fly', 'risk_cap': 250, 'credit': 1.5, 'width': 5, 'wing': 5})
    assert vs.status_code == 200
    assert 'iv_atm' in vs.json()
    assert rk.status_code == 200
