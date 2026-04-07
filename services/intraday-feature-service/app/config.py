"""Intraday Feature service configuration."""

import os

SERVICE_NAME = "intraday-features"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8009"))
