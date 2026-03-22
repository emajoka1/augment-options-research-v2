from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from src.api.main import app


@pytest.mark.asyncio
async def test_brief_endpoint_returns_placeholder_for_non_spy():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/brief/QQQ')
    payload = response.json()
    assert response.status_code == 200
    assert payload['TRADE BRIEF']['Ticker'] == 'QQQ'
    assert payload['TRADE BRIEF']['Final Decision'] == 'NO TRADE'


@pytest.mark.asyncio
async def test_brief_endpoint_uses_generator(monkeypatch):
    class FakeGenerator:
        def generate(self, symbol: str):
            return type('BriefResult', (), {'payload': {'TRADE BRIEF': {'Ticker': symbol, 'Final Decision': 'TRADE', 'Candidates': []}}})()

    monkeypatch.setattr('src.api.main.BriefGenerator', lambda: FakeGenerator())
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/brief/SPY')
    payload = response.json()
    assert response.status_code == 200
    assert payload['TRADE BRIEF']['Final Decision'] == 'TRADE'


@pytest.mark.asyncio
async def test_brief_endpoint_shape_contains_trade_brief_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/brief/QQQ')
    assert response.status_code == 200
    assert 'TRADE BRIEF' in response.json()
