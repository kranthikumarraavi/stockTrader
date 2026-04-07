"""Options Signal Microservice – Port 8008.

F&O derivatives signal generation for intraday options.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import intraday_options
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Options Signal Service")

app.include_router(intraday_options.router, prefix="/api/v1")

add_health_endpoints(app, SERVICE_NAME)
