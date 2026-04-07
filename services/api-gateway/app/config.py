"""API Gateway service configuration."""

import os

SERVICE_NAME = "api-gateway"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))

# Downstream service URLs
MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://localhost:8001")
PREDICTION_URL = os.getenv("PREDICTION_URL", "http://localhost:8002")
TRADING_URL = os.getenv("TRADING_URL", "http://localhost:8003")
PORTFOLIO_RISK_URL = os.getenv("PORTFOLIO_RISK_URL", "http://localhost:8004")
BACKTEST_URL = os.getenv("BACKTEST_URL", "http://localhost:8005")
MODEL_MANAGEMENT_URL = os.getenv("MODEL_MANAGEMENT_URL", "http://localhost:8006")
EXECUTION_URL = os.getenv("EXECUTION_URL", "http://localhost:8007")
OPTIONS_SIGNAL_URL = os.getenv("OPTIONS_SIGNAL_URL", "http://localhost:8008")
INTRADAY_FEATURE_URL = os.getenv("INTRADAY_FEATURE_URL", "http://localhost:8009")
INTRADAY_PREDICTION_URL = os.getenv("INTRADAY_PREDICTION_URL", "http://localhost:8010")
TRADE_SUPERVISOR_URL = os.getenv("TRADE_SUPERVISOR_URL", "http://localhost:8011")
