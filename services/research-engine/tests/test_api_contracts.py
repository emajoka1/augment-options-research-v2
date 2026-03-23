from __future__ import annotations

import json

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
async def test_chain_contract_contains_source(sample_snapshot):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/chain/SPY', params={'snapshot_path': str(sample_snapshot)})
    payload = response.json()
    assert response.status_code == 200
    assert payload['source'] == 'snapshot_file'
    assert isinstance(payload['strikes'], list)


@pytest.mark.asyncio
async def test_mc_run_contract_contains_status(tmp_path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/mc/run', json={'n_batches': 1, 'paths_per_batch': 100, 'expiry_days': 1, 'dt_days': 1, 'output_root': str(tmp_path), 'write_artifacts': False})
    payload = response.json()
    assert response.status_code == 200
    assert payload['status'] in {'FULL_REFRESH', 'NO_NEW_INPUTS', 'NO_ACTION_DQ_FAIL_DUPLICATE'}
    assert 'gates' in payload or payload['status'] != 'FULL_REFRESH'


@pytest.mark.asyncio
async def test_strategy_contract_contains_greeks_aggregate():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/strategy/analyze', json={
            'legs': [
                {'side': 'long', 'option_type': 'call', 'strike': 600, 'qty': 1, 'expiry_years': 0.0137},
                {'side': 'short', 'option_type': 'call', 'strike': 605, 'qty': 1, 'expiry_years': 0.0137},
            ],
            'spot': 600,
            'r': 0.03,
            'q': 0.0,
        })
    payload = response.json()
    assert response.status_code == 200
    assert set(payload['greeks_aggregate'].keys()) == {'delta', 'gamma', 'vega', 'theta_daily'}
    assert any(abs(payload['greeks_aggregate'][k]) > 0 for k in payload['greeks_aggregate'])
