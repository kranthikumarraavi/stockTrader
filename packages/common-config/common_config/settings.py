"""Unified configuration model for all StockTrader services.

Each service reads from environment variables (or .env file).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()


class ServiceSettings(BaseSettings):
    """Base settings shared by every microservice."""

    # ── Service identity ────────────────────────────────────────────────
    service_name: str = "stocktrader"
    service_port: int = 8000
    log_level: str = "INFO"
    debug: bool = False

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite:///stocktrader.db",
        description="Postgres or SQLite connection string",
    )

    # ── Redis ───────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── RabbitMQ ────────────────────────────────────────────────────────
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # ── Paths ───────────────────────────────────────────────────────────
    model_registry_path: str = "models/registry.json"
    market_data_path: str = "storage/raw"
    storage_path: str = "storage"

    # ── Service URLs (for inter-service communication) ──────────────────
    gateway_url: str = "http://localhost:8000"
    market_data_url: str = "http://localhost:8001"
    prediction_url: str = "http://localhost:8002"
    trading_url: str = "http://localhost:8003"
    portfolio_risk_url: str = "http://localhost:8004"
    backtest_url: str = "http://localhost:8005"
    model_management_url: str = "http://localhost:8006"
    execution_url: str = "http://localhost:8007"
    options_signal_url: str = "http://localhost:8008"
    intraday_feature_url: str = "http://localhost:8009"
    intraday_prediction_url: str = "http://localhost:8010"
    trade_supervisor_url: str = "http://localhost:8011"

    # ── CORS ────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:4200"

    # ── Broker (Angel One) ──────────────────────────────────────────────
    angel_api_key: Optional[str] = None
    angel_client_id: Optional[str] = None
    angel_mpin: Optional[str] = None
    angel_totp_secret: Optional[str] = None

    # ── Monitoring ──────────────────────────────────────────────────────
    sentry_dsn: Optional[str] = None
    prometheus_enabled: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> ServiceSettings:
    """Singleton settings instance (cached)."""
    return ServiceSettings()
