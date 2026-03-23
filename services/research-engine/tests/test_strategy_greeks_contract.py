from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from src.api.main import app


@pytest.mark.asyncio
async def test_strategy_analyze_returns_nonzero_call_delta():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/strategy/analyze', json={
            'legs': [
                {'side': 'long', 'option_type': 'call', 'strike': 600, 'qty': 1, 'expiry_years': 0.0137},
            ],
            'spot': 600,
            'r': 0.03,
            'q': 0.013,
        })
    payload = response.json()
    assert response.status_code == 200
    assert payload['greeks_aggregate']['delta'] > 0


@pytest.mark.asyncio
async def test_strategy_analyze_short_call_flips_delta_sign():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/strategy/analyze', json={
            'legs': [
                {'side': 'short', 'option_type': 'call', 'strike': 600, 'qty': 1, 'expiry_years': 0.0137},
            ],
            'spot': 600,
            'r': 0.03,
            'q': 0.013,
        })
    payload = response.json()
    assert response.status_code == 200
    assert payload['greeks_aggregate']['delta'] < 0


@pytest.mark.asyncio
async def test_strategy_analyze_straddle_has_near_zero_delta():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/strategy/analyze', json={
            'legs': [
                {'side': 'long', 'option_type': 'call', 'strike': 600, 'qty': 1, 'expiry_years': 0.0137},
                {'side': 'long', 'option_type': 'put', 'strike': 600, 'qty': 1, 'expiry_years': 0.0137},
            ],
            'spot': 600,
            'r': 0.03,
            'q': 0.013,
        })
    payload = response.json()
    assert response.status_code == 200
    assert abs(payload['greeks_aggregate']['delta']) < 0.2
