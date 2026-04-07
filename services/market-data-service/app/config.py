"""Market Data service configuration."""

import os

SERVICE_NAME = "market-data"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))
