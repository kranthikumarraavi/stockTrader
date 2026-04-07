"""Options Signal service configuration."""

import os

SERVICE_NAME = "options-signal"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8008"))
