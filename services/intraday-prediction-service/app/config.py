"""Intraday Prediction service configuration."""

import os

SERVICE_NAME = "intraday-prediction"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8010"))
