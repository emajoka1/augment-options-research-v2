from __future__ import annotations

import json

import pytest

from ak_system.storage import persist_mc_result


@pytest.mark.asyncio
async def test_persist_mc_result_returns_none_without_db(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    result = await persist_mc_result({'gates': {'allow_trade': False}}, {'symbol': 'SPY', 'strategy_type': 'iron_fly'})
    assert result is None


@pytest.mark.asyncio
async def test_persist_mc_result_inserts_when_db_present(monkeypatch):
    class FakeConn:
        async def fetchrow(self, query, *args):
            assert 'INSERT INTO mc_results' in query
            assert json.loads(args[2])['symbol'] == 'SPY'
            return {'id': 'abc-123'}

        async def close(self):
            return None

    async def fake_connect(dsn):
        assert dsn == 'postgres://example'
        return FakeConn()

    monkeypatch.setenv('DATABASE_URL', 'postgres://example')
    monkeypatch.setattr('ak_system.storage.asyncpg.connect', fake_connect)
    result = await persist_mc_result({'gates': {'allow_trade': True}, 'multi_seed_confidence': {'ev_mean': 1.2}}, {'symbol': 'SPY', 'strategy_type': 'iron_fly'})
    assert result == 'abc-123'


@pytest.mark.asyncio
async def test_persist_mc_result_uses_payload_fields(monkeypatch):
    captured = {}

    class FakeConn:
        async def fetchrow(self, query, *args):
            captured['args'] = args
            return {'id': 'row-1'}

        async def close(self):
            return None

    async def fake_connect(dsn):
        return FakeConn()

    monkeypatch.setenv('DATABASE_URL', 'postgres://example')
    monkeypatch.setattr('ak_system.storage.asyncpg.connect', fake_connect)
    payload = {'canonical_inputs_hash': 'hash', 'gates': {'allow_trade': True}, 'multi_seed_confidence': {'ev_mean': 0.7}, 'data_quality_status': 'OK'}
    await persist_mc_result(payload, {'symbol': 'QQQ', 'strategy_type': 'calendar'})
    assert captured['args'][0] == 'QQQ'
    assert captured['args'][1] == 'calendar'
    assert captured['args'][4] == 'hash'
    assert captured['args'][5] is True
