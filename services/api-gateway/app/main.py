"""API Gateway – Port 8000.

Lightweight reverse proxy routing requests to downstream microservices.
Also serves the Angular frontend static files in production.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from common_logging import setup_logging
from common_utils.health import add_health_endpoints

from app.config import (
    SERVICE_NAME, SERVICE_PORT,
    MARKET_DATA_URL, PREDICTION_URL, TRADING_URL,
    PORTFOLIO_RISK_URL, BACKTEST_URL, MODEL_MANAGEMENT_URL,
    EXECUTION_URL, OPTIONS_SIGNAL_URL,
    INTRADAY_FEATURE_URL, INTRADAY_PREDICTION_URL, TRADE_SUPERVISOR_URL,
)

setup_logging(SERVICE_NAME)

# ── Normalize URLs ──────────────────────────────────────────────────────────

def _normalize(raw: str, fallback: str) -> str:
    value = (raw or "").strip() or fallback
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https", "ws", "wss"}:
        return value.rstrip("/")
    if value.startswith("//"):
        value = value[2:]
    return f"http://{value}".rstrip("/")


_MARKET_DATA = _normalize(MARKET_DATA_URL, "http://localhost:8001")
_PREDICTION = _normalize(PREDICTION_URL, "http://localhost:8002")
_TRADING = _normalize(TRADING_URL, "http://localhost:8003")
_PORTFOLIO_RISK = _normalize(PORTFOLIO_RISK_URL, "http://localhost:8004")
_BACKTEST = _normalize(BACKTEST_URL, "http://localhost:8005")
_MODEL_MGMT = _normalize(MODEL_MANAGEMENT_URL, "http://localhost:8006")
_EXECUTION = _normalize(EXECUTION_URL, "http://localhost:8007")
_OPTIONS_SIGNAL = _normalize(OPTIONS_SIGNAL_URL, "http://localhost:8008")
_INTRADAY_FEAT = _normalize(INTRADAY_FEATURE_URL, "http://localhost:8009")
_INTRADAY_PRED = _normalize(INTRADAY_PREDICTION_URL, "http://localhost:8010")
_TRADE_SUPER = _normalize(TRADE_SUPERVISOR_URL, "http://localhost:8011")

# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="StockTrader API Gateway", version="0.1.0")

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:4200")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
if "*" in _origins:
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
else:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])


def _gateway_readiness():
    return {"ready": True, "downstream_services": 11}


add_health_endpoints(app, SERVICE_NAME, readiness_check=_gateway_readiness)

# ── Downstream services for health aggregation ──────────────────────────────

ALL_SERVICES = {
    "market_data": _MARKET_DATA,
    "prediction": _PREDICTION,
    "trading": _TRADING,
    "portfolio_risk": _PORTFOLIO_RISK,
    "backtest": _BACKTEST,
    "model_management": _MODEL_MGMT,
    "execution": _EXECUTION,
    "options_signal": _OPTIONS_SIGNAL,
    "intraday_features": _INTRADAY_FEAT,
    "intraday_prediction": _INTRADAY_PRED,
    "trade_supervisor": _TRADE_SUPER,
}


@app.get("/api/v1/health/services")
async def health_services():
    """Aggregated health check for all downstream services."""
    services = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in ALL_SERVICES.items():
            try:
                resp = await client.get(f"{url}/health")
                services[name] = "ok" if resp.status_code == 200 else "degraded"
            except Exception:
                services[name] = "unreachable"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return {"status": overall, "services": services}


# ── Route mapping ───────────────────────────────────────────────────────────

def _resolve_upstream(path: str) -> str | None:
    p = path.lstrip("/")

    # Market Data Service (8001)
    if p.startswith(("api/v1/stream", "api/v1/market/", "api/v1/account/",
                     "api/v1/symbols/", "api/v1/historical/", "api/v1/quote/",
                     "api/v1/provider/status", "api/v1/jobs/", "api/v1/status")):
        return _MARKET_DATA

    # Prediction Service (8002)
    if p.startswith(("api/v1/predict", "api/v1/batch_predict",
                     "api/v1/model/", "api/v1/regime", "api/v1/strategy/",
                     "api/v1/sentiment/", "api/v1/news/", "api/v1/anomaly/")):
        return _PREDICTION

    # Trading Service (8003)
    if p.startswith(("api/v1/trade_intent", "api/v1/execute",
                     "api/v1/paper", "api/v1/bot", "api/v1/options/",
                     "api/v1/orchestrator/")):
        return _TRADING

    # Portfolio Risk Service (8004)
    if p.startswith(("api/v1/risk/", "api/v1/portfolio/")):
        return _PORTFOLIO_RISK

    # Backtest Service (8005)
    if p.startswith("api/v1/backtest"):
        return _BACKTEST

    # Model Management Service (8006)
    if p.startswith(("api/v1/retrain", "api/v1/metrics", "api/v1/registry/",
                     "api/v1/drift/", "api/v1/canary/", "api/v1/log")):
        return _MODEL_MGMT

    # Execution Service (8007)
    if p.startswith("api/v1/execution/"):
        return _EXECUTION
    if p.startswith("api/v1/intraday/execution"):
        return _EXECUTION

    # Options Signal Service (8008)
    if p.startswith("api/v1/intraday/options"):
        return _OPTIONS_SIGNAL

    # Intraday Feature Service (8009)
    if p.startswith("api/v1/intraday/features"):
        return _INTRADAY_FEAT

    # Intraday Prediction Service (8010)
    if p.startswith("api/v1/intraday/predict"):
        return _INTRADAY_PRED

    # Trade Supervisor Service (8011)
    if p.startswith(("api/v1/intraday/supervisor", "api/v1/intraday/train")):
        return _TRADE_SUPER

    return None


def _timeout_for_path(path: str) -> float:
    p = path.lstrip("/")
    if p.startswith("api/v1/retrain"):
        return float(os.getenv("GATEWAY_RETRAIN_TIMEOUT_S", "900"))
    if p.startswith("api/v1/backtest"):
        return float(os.getenv("GATEWAY_BACKTEST_TIMEOUT_S", "600"))
    if p.startswith("api/v1/model/reload"):
        return float(os.getenv("GATEWAY_MODEL_RELOAD_TIMEOUT_S", "120"))
    return float(os.getenv("GATEWAY_UPSTREAM_TIMEOUT_S", "60"))


# ── Reverse proxy ───────────────────────────────────────────────────────────

@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_rest(request: Request, path: str):
    full_path = f"/api/v1/{path}"
    upstream = _resolve_upstream(full_path)
    if upstream is None:
        raise HTTPException(status_code=404, detail=f"No upstream for: {full_path}")

    target_url = f"{upstream}{full_path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    timeout_s = _timeout_for_path(full_path)

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            resp = await client.request(method=request.method, url=target_url,
                                         content=body, headers=headers)
        except httpx.ReadTimeout as exc:
            raise HTTPException(504, f"Upstream timeout after {timeout_s:.0f}s") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"Upstream unavailable: {exc}") from exc

    if "text/event-stream" in resp.headers.get("content-type", ""):
        async def _stream():
            async with httpx.AsyncClient(timeout=None) as sc:
                async with sc.stream(method=request.method, url=target_url,
                                     content=body, headers=headers) as sr:
                    async for chunk in sr.aiter_bytes():
                        yield chunk
        return StreamingResponse(_stream(), media_type="text/event-stream")

    return StreamingResponse(
        iter([resp.content]), status_code=resp.status_code,
        headers=dict(resp.headers), media_type=resp.headers.get("content-type"),
    )


# ── WebSocket proxy ─────────────────────────────────────────────────────────

@app.websocket("/api/v1/stream/price/{symbol}")
async def ws_price_proxy(websocket: WebSocket, symbol: str):
    await _proxy_websocket(
        websocket, f"{_MARKET_DATA.replace('http', 'ws')}/api/v1/stream/price/{symbol}")


@app.websocket("/api/v1/stream/multi")
async def ws_multi_proxy(websocket: WebSocket):
    await _proxy_websocket(
        websocket, f"{_MARKET_DATA.replace('http', 'ws')}/api/v1/stream/multi")


async def _proxy_websocket(client_ws: WebSocket, upstream_url: str):
    import asyncio
    import websockets

    await client_ws.accept()
    try:
        async with websockets.connect(upstream_url) as upstream_ws:
            async def c2u():
                try:
                    while True:
                        data = await client_ws.receive_text()
                        await upstream_ws.send(data)
                except WebSocketDisconnect:
                    await upstream_ws.close()
                except Exception:
                    pass

            async def u2c():
                try:
                    async for msg in upstream_ws:
                        await client_ws.send_text(msg)
                except Exception:
                    pass

            await asyncio.gather(c2u(), u2c())
    except Exception:
        try:
            await client_ws.close()
        except Exception:
            pass


# ── Serve Angular frontend (production) ────────────────────────────────────

_static_dir = Path("static")
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        file_path = _static_dir / path
        if file_path.is_file():
            return FileResponse(file_path)
        index = _static_dir / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(404)
