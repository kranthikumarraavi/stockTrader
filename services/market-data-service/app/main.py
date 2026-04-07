"""Market Data Microservice – Port 8001.

Handles market data ingestion, historical queries, streaming, and live feeds.
Wraps the existing backend.api.services.market_data module with standard
health/ready/metrics endpoints.
"""

from dotenv import load_dotenv
load_dotenv()

from common_logging import setup_logging
from app.config import SERVICE_NAME

setup_logging(SERVICE_NAME)

# Import the existing market_data app and augment it
from backend.api.services.market_data import app  # noqa: E402

from common_utils.health import add_health_endpoints  # noqa: E402


def _readiness_check():
    """Check if market data service is ready to serve."""
    try:
        from backend.services.market_hours import get_market_status
        status = get_market_status()
        return {"ready": True, "market_status": status.get("status", "unknown")}
    except Exception:
        return {"ready": True}


add_health_endpoints(app, SERVICE_NAME, readiness_check=_readiness_check)
