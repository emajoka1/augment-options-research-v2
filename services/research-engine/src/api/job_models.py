from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class JobAcceptedResponse(BaseModel):
    job_id: str
    status: str = 'pending'


class JobStatusResponse(BaseModel):
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
