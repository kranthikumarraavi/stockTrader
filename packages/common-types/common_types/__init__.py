"""Shared Pydantic types re-exported from the backend schemas.

Keeps backward compatibility with existing backend code while
making types available as an installable package.
"""

# Re-export from existing backend schemas so services can import from here
# without coupling to the full backend package.
try:
    from backend.api.schemas import (
        ActionEnum,
        OrderSide,
        OrderType,
        OptionType,
        OptionStrategy,
        JobStatus,
        ErrorResponse,
        Greeks,
        PriceTickEvent,
        PredictionEntry,
        PredictRequest,
        PredictResponse,
        BatchPredictRequest,
        BatchPredictResponse,
    )
except ImportError:
    pass  # Standalone mode – types defined locally below

from common_types.schemas import ServiceHealth, ServiceStatus

__all__ = ["ServiceHealth", "ServiceStatus"]
