"""Model Management Microservice – Port 8006.

Model retraining, drift detection, canary deployments, registry, metrics, logging.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

from backend.api.services.base import create_service_app
from backend.api.routers import admin, log
from common_utils.health import add_health_endpoints

app = create_service_app(title="StockTrader – Model Management Service")

app.include_router(admin.router, prefix="/api/v1")
app.include_router(log.router, prefix="/api/v1")

add_health_endpoints(app, SERVICE_NAME)
