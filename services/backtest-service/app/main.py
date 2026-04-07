"""Backtest Microservice – Port 8005.

Backtesting engine for strategy validation.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import backtest
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Backtest Service")

app.include_router(backtest.router, prefix="/api/v1")

add_health_endpoints(app, SERVICE_NAME)
