"""Execution service configuration."""

import os

SERVICE_NAME = "execution"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8007"))
