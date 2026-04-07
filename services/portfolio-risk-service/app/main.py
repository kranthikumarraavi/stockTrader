"""Portfolio Risk Microservice – Port 8004.

Risk management, portfolio analytics, exposure tracking.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import risk, portfolio
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Portfolio Risk Service")

app.include_router(risk.router, prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")

add_health_endpoints(app, SERVICE_NAME)
