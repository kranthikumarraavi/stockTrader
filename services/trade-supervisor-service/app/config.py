"""Trade Supervisor service configuration."""

import os

SERVICE_NAME = "trade-supervisor"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8011"))
