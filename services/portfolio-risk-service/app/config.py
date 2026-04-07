"""Portfolio Risk service configuration."""

import os

SERVICE_NAME = "portfolio-risk"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8004"))
