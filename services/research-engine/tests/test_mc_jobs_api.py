from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from src.api.main import app


@pytest.mark.asyncio
async def test_mc_run_async_returns_job_id(monkeypatch):
    monkeypatch.setattr('src.api.main.submit_mc_job', lambda config: ('job-123', 'memory'))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/v1/mc/run-async', json={'spot': 600, 'strategy_type': 'iron_fly'})
    assert response.status_code == 202
    assert response.json()['job_id'] == 'job-123'
    assert response.json()['backend'] == 'memory'


@pytest.mark.asyncio
async def test_mc_job_status_returns_pending(monkeypatch):
    class Job:
        status = 'pending'
        result = None
        error = None
        backend = 'celery'

    monkeypatch.setattr('src.api.main.get_job', lambda job_id: Job())
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/mc/jobs/job-123')
    assert response.status_code == 200
    assert response.json()['status'] == 'pending'
    assert response.json()['backend'] == 'celery'


@pytest.mark.asyncio
async def test_mc_job_status_returns_result(monkeypatch):
    class Job:
        status = 'complete'
        result = {'status': 'FULL_REFRESH'}
        error = None
        backend = 'memory'

    monkeypatch.setattr('src.api.main.get_job', lambda job_id: Job())
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/v1/mc/jobs/job-123')
    assert response.status_code == 200
    assert response.json()['result']['status'] == 'FULL_REFRESH'
    assert response.json()['backend'] == 'memory'
