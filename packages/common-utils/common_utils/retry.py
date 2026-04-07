"""Retry utilities for inter-service communication."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Callable, TypeVar

_log = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator: retry a function with exponential backoff + jitter.

    Works with both sync and async functions.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                last_exc = None
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        if attempt < max_retries:
                            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                            _log.warning(
                                "Retry %d/%d for %s after %.1fs: %s",
                                attempt + 1, max_retries, func.__name__, delay, exc,
                            )
                            await asyncio.sleep(delay)
                raise last_exc
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                last_exc = None
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as exc:
                        last_exc = exc
                        if attempt < max_retries:
                            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                            _log.warning(
                                "Retry %d/%d for %s after %.1fs: %s",
                                attempt + 1, max_retries, func.__name__, delay, exc,
                            )
                            time.sleep(delay)
                raise last_exc
            return sync_wrapper
    return decorator
