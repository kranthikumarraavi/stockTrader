"""Intraday Prediction Microservice – Port 8010.

ML inference for intraday trading signals.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import intraday_predict
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Intraday Prediction Service")

app.include_router(intraday_predict.router, prefix="/api/v1")

add_health_endpoints(app, SERVICE_NAME)
