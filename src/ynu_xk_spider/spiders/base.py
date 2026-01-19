"""Base spider with lifecycle management and graceful shutdown."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import Final

logger = logging.getLogger(__name__)


class BaseSpider(ABC):
    """Abstract base spider providing lifecycle and stop signal handling.

    Subclasses implement run_loop() and use self.stop_event to detect
    shutdown requests. The start() method handles the full lifecycle.

    Attributes:
        stop_event: Threading event for graceful shutdown signaling.
    """

    def __init__(self) -> None:
        """Initialize spider with stop event."""
        self.stop_event: Final[threading.Event] = threading.Event()

    def start(self) -> None:
        """Start the spider run loop with lifecycle hooks."""
        logger.info("Spider starting")
        try:
            self.on_start()
            self.run_loop()
        except Exception as exc:
            logger.error("Spider error: %s", exc)
            raise
        finally:
            self.on_stop()
            logger.info("Spider stopped")

    def stop(self) -> None:
        """Signal the spider to stop gracefully."""
        logger.info("Stop signal received")
        self.stop_event.set()

    def is_stopped(self) -> bool:
        """Check if stop has been requested.

        Returns:
            True if stop was signaled.
        """
        return self.stop_event.is_set()

    def raise_if_stopped(self) -> None:
        """Raise RuntimeError if stop was requested.

        Raises:
            RuntimeError: If stop_event is set.
        """
        if self.is_stopped():
            raise RuntimeError("Stop requested")

    @abstractmethod
    def run_loop(self) -> None:
        """Main execution loop. Must honor self.stop_event."""

    def on_start(self) -> None:
        """Hook called before run_loop. Override for setup."""

    def on_stop(self) -> None:
        """Hook called after run_loop. Override for cleanup."""
