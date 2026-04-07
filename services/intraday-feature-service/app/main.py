"""Intraday Feature Microservice – Port 8009.

Candle data pipeline and feature computation for intraday strategies.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import intraday_features
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Intraday Feature Service")

app.include_router(intraday_features.router, prefix="/api/v1")

add_health_endpoints(app, SERVICE_NAME)
