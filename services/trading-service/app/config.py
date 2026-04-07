"""Trading service configuration."""

import os

SERVICE_NAME = "trading"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8003"))
