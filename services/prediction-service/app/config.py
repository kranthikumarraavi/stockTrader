"""Prediction service configuration."""

import os

SERVICE_NAME = "prediction"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8002"))
