# Database session setup
"""Database session configuration.

Uses Postgres when DATABASE_URL is provided; otherwise falls back to SQLite
for local development.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import logging as _logging

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./stocktrader.db",
)

_app_env = os.getenv("APP_ENV", "development").lower()
if _app_env == "production" and DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "DATABASE_URL is not set or points to SQLite. "
        "Set DATABASE_URL to a Postgres connection string for production."
    )
if DATABASE_URL.startswith("sqlite"):
    _logging.getLogger(__name__).warning(
        "Using SQLite (%s). Set DATABASE_URL for production.", DATABASE_URL,
    )

# SQLite requires connect_args for multi-thread access
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

