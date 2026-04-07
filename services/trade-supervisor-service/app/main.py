"""Trade Supervisor Microservice – Port 8011.

Centralized risk supervisor for intraday automated trading.
Also hosts intraday model training endpoints.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import intraday_supervisor, intraday_train
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Trade Supervisor Service")

app.include_router(intraday_supervisor.router, prefix="/api/v1")
app.include_router(intraday_train.router, prefix="/api/v1")

add_health_endpoints(app, SERVICE_NAME)
