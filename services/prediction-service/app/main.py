"""Prediction Microservice – Port 8002.

ML inference, regime detection, strategy selection, and intelligence.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import predict, model, strategy, intelligence
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Prediction Service")

app.include_router(predict.router, prefix="/api/v1")
app.include_router(model.router, prefix="/api/v1")
app.include_router(strategy.router, prefix="/api/v1")
app.include_router(intelligence.router, prefix="/api/v1")


def _readiness_check():
    try:
        from backend.services.model_manager import ModelManager
        mgr = ModelManager()
        return {"ready": mgr.model is not None, "model_loaded": mgr.model is not None}
    except Exception:
        return {"ready": True}


add_health_endpoints(app, SERVICE_NAME, readiness_check=_readiness_check)
