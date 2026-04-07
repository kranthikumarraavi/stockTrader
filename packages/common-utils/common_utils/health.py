"""Standard health, readiness, and metrics endpoints for all services."""

from __future__ import annotations

import time
from typing import Any, Callable

from fastapi import FastAPI, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

# ── Prometheus metrics ──────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["service", "method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

_start_time = time.time()


def add_health_endpoints(
    app: FastAPI,
    service_name: str,
    readiness_check: Callable[[], dict[str, Any]] | None = None,
) -> None:
    """Add standard /health, /ready, /status, /metrics endpoints.

    Args:
        app: The FastAPI application.
        service_name: Name of the service (e.g. "market-data").
        readiness_check: Optional callable returning readiness details.
    """

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": service_name}

    @app.get("/ready")
    async def ready():
        details: dict[str, Any] = {"service": service_name}
        if readiness_check:
            try:
                check_result = readiness_check()
                details.update(check_result)
                details["ready"] = check_result.get("ready", True)
            except Exception as exc:
                details["ready"] = False
                details["error"] = str(exc)
        else:
            details["ready"] = True
        return details

    @app.get("/status")
    async def status():
        return {
            "service": service_name,
            "status": "running",
            "uptime_seconds": round(time.time() - _start_time, 1),
        }

    @app.get("/metrics")
    async def metrics():
        body = generate_latest(REGISTRY)
        return Response(content=body, media_type=CONTENT_TYPE_LATEST)

    # Also add prefixed versions under /api/v1/
    @app.get("/api/v1/health")
    async def api_health():
        return {"status": "ok", "service": service_name}

    @app.get("/api/v1/ready")
    async def api_ready():
        return await ready()

    @app.get("/api/v1/status")
    async def api_status():
        return await status()

    @app.get("/api/v1/metrics")
    async def api_metrics():
        return await metrics()

    # Middleware: instrument all requests
    @app.middleware("http")
    async def _metrics_middleware(request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        endpoint = request.url.path
        # Skip metrics/health from instrumentation to avoid noise
        if endpoint not in ("/health", "/ready", "/metrics", "/status"):
            REQUEST_COUNT.labels(
                service=service_name,
                method=request.method,
                endpoint=endpoint,
                status=response.status_code,
            ).inc()
            REQUEST_LATENCY.labels(
                service=service_name,
                method=request.method,
                endpoint=endpoint,
            ).observe(duration)

        return response
