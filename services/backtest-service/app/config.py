"""Backtest service configuration."""

import os

SERVICE_NAME = "backtest"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8005"))
