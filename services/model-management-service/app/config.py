"""Model Management service configuration."""

import os

SERVICE_NAME = "model-management"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8006"))
