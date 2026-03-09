"""Retry decorator with exponential backoff and jitter."""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def retry(
    exceptions: tuple[type[BaseException], ...],
    tries: int = 5,
    delay: float = 0.5,
    backoff: float = 2.0,
    jitter: float = 0.1,
    logger: logging.Logger | None = None,
    sleep: Callable[[float], bool] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry decorator with exponential backoff and jitter.

    Args:
        exceptions: Exception types to catch and retry on.
        tries: Total number of attempts (>= 1).
        delay: Initial delay between retries in seconds.
        backoff: Multiplier applied to delay after each failure.
        jitter: Random jitter range (+/-) added to delay.
        logger: Optional logger for warning messages.
        sleep: Optional sleep function. Returns True if the full delay elapsed,
            False if the wait was interrupted and retrying should stop.

    Returns:
        Decorated function with retry behavior.

    Example:
        @retry(exceptions=(NetworkError,), tries=3, delay=1.0)
        def fetch_data() -> dict:
            ...

    Raises:
        ValueError: If parameters are invalid.
    """
    if tries < 1:
        raise ValueError("tries must be >= 1")
    if delay <= 0:
        raise ValueError("delay must be > 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")
    if jitter < 0:
        raise ValueError("jitter must be >= 0")
    if not exceptions:
        raise ValueError("exceptions must not be empty")

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            remaining = tries
            current_delay = delay
            sleep_func = sleep or _default_sleep

            while remaining > 1:
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    wait = max(0.0, current_delay + random.uniform(-jitter, jitter))
                    if logger:
                        logger.warning(
                            "Retryable error in %s: %s. Retrying in %.2fs (%d attempts left)",
                            func.__name__,
                            exc,
                            wait,
                            remaining - 1,
                        )
                    if not sleep_func(wait):
                        raise exc
                    remaining -= 1
                    current_delay *= backoff

            return func(*args, **kwargs)

        return wrapper

    return decorator


def _default_sleep(delay: float) -> bool:
    """Sleep for the requested delay and report completion."""
    time.sleep(delay)
    return True
