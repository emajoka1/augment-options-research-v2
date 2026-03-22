from __future__ import annotations

import os
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any
from uuid import uuid4

from celery import Celery

from ak_system.mc_options.engine import MCEngine, MCEngineConfig


@dataclass
class JobRecord:
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    backend: str = 'memory'


_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_JOBS: dict[str, JobRecord] = {}
_FUTURES: dict[str, Future] = {}
_LOCK = Lock()
_REDIS_URL = os.environ.get('REDIS_URL')
_CELERY_APP = Celery('research_engine_jobs', broker=_REDIS_URL, backend=_REDIS_URL) if _REDIS_URL else None


if _CELERY_APP:
    @_CELERY_APP.task(name='research_engine.run_mc_job')
    def run_mc_job_task(config_dict: dict[str, Any]) -> dict[str, Any]:
        config = MCEngineConfig(**config_dict)
        return MCEngine().run(config).payload


def submit_mc_job(config: MCEngineConfig) -> tuple[str, str]:
    if _CELERY_APP:
        task = _CELERY_APP.send_task('research_engine.run_mc_job', args=[config.__dict__])
        return task.id, 'celery'

    job_id = str(uuid4())
    with _LOCK:
        _JOBS[job_id] = JobRecord(status='pending', backend='memory')

    future = _EXECUTOR.submit(_run_job, job_id, config)
    with _LOCK:
        _FUTURES[job_id] = future
    return job_id, 'memory'


def _run_job(job_id: str, config: MCEngineConfig) -> None:
    with _LOCK:
        _JOBS[job_id] = JobRecord(status='running', backend='memory')
    try:
        result = MCEngine().run(config).payload
        with _LOCK:
            _JOBS[job_id] = JobRecord(status='complete', result=result, backend='memory')
    except Exception as exc:
        with _LOCK:
            _JOBS[job_id] = JobRecord(status='failed', error=str(exc), backend='memory')


def get_job(job_id: str) -> JobRecord | None:
    if _CELERY_APP:
        task = _CELERY_APP.AsyncResult(job_id)
        state = task.state.lower()
        if state == 'pending':
            return JobRecord(status='pending', backend='celery')
        if state in {'started', 'retry'}:
            return JobRecord(status='running', backend='celery')
        if state == 'success':
            return JobRecord(status='complete', result=task.result, backend='celery')
        if state == 'failure':
            return JobRecord(status='failed', error=str(task.result), backend='celery')
        return JobRecord(status=state, backend='celery')

    with _LOCK:
        return _JOBS.get(job_id)
