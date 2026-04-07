"""Common response schemas used across all services."""

from __future__ import annotations

from pydantic import BaseModel


class ServiceHealth(BaseModel):
    status: str = "ok"
    service: str = ""


class ServiceStatus(BaseModel):
    service: str
    status: str = "running"
    uptime_seconds: float = 0.0
    version: str = "0.1.0"
