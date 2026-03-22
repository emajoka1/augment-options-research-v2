from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Any
from uuid import uuid4

from ak_system.mc_options.engine import MCEngine, MCEngineConfig


@dataclass
class JobRecord:
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_JOBS: dict[str, JobRecord] = {}
_FUTURES: dict[str, Future] = {}
_LOCK = Lock()


def submit_mc_job(config: MCEngineConfig) -> str:
    job_id = str(uuid4())
    with _LOCK:
        _JOBS[job_id] = JobRecord(status='pending')

    future = _EXECUTOR.submit(_run_job, job_id, config)
    with _LOCK:
        _FUTURES[job_id] = future
    return job_id


def _run_job(job_id: str, config: MCEngineConfig) -> None:
    with _LOCK:
        _JOBS[job_id] = JobRecord(status='running')
    try:
        result = MCEngine().run(config).payload
        with _LOCK:
            _JOBS[job_id] = JobRecord(status='complete', result=result)
    except Exception as exc:
        with _LOCK:
            _JOBS[job_id] = JobRecord(status='failed', error=str(exc))


def get_job(job_id: str) -> JobRecord | None:
    with _LOCK:
        return _JOBS.get(job_id)
