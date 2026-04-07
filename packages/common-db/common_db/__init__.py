"""Shared database access re-exported from backend.db.

Provides session factory and models for all microservices.
"""

try:
    from backend.db.session import SessionLocal, engine, get_db
    from backend.db.models import (
        Base,
        Order,
        Fill,
        BacktestJob,
        AuditLog,
        BotState,
        BotStateTransition,
        RiskSnapshot,
        TradeJournal,
        SystemEvent,
    )
except ImportError:
    # Standalone mode – services must configure their own DB
    SessionLocal = None
    engine = None
    get_db = None
    Base = None

__all__ = [
    "SessionLocal",
    "engine",
    "get_db",
    "Base",
]
