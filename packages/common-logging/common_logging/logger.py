"""Structured logging setup for all StockTrader services.

Produces JSON logs in production and human-readable logs in development.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    service_name: str = "stocktrader",
    log_level: str | None = None,
    log_dir: str = "logs",
) -> None:
    """Configure structured logging for a microservice.

    Args:
        service_name: Name used in log records and filenames.
        log_level: Override log level (default: from LOG_LEVEL env var or INFO).
        log_dir: Directory for log files.
    """
    level_str = log_level or os.getenv("LOG_LEVEL", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)

    fmt = f"%(asctime)s | %(levelname)-8s | {service_name} | %(name)s:%(lineno)d | %(message)s"
    formatter = logging.Formatter(fmt)

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(level)

    # File handler (rotating)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path / f"{service_name}.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    # Remove existing handlers to avoid duplicates
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
