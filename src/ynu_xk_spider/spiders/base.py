"""Base spider with lifecycle management and graceful shutdown."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Final

from ..utils.stop import StopToken

logger = logging.getLogger(__name__)


class BaseSpider(ABC):
    """Abstract base spider providing lifecycle and stop signal handling.

    Subclasses implement run_loop() and use self.stop_token to detect
    shutdown requests. The start() method handles the full lifecycle.

    Attributes:
        stop_token: Cancellation token for graceful shutdown signaling.
    """

    def __init__(self) -> None:
        """Initialize spider with stop token."""
        self.stop_token: Final[StopToken] = StopToken()

    def start(self) -> None:
        """Start the spider run loop with lifecycle hooks."""
        logger.info("Spider starting")
        try:
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
        self.stop_token.set()

    def is_stopped(self) -> bool:
        """Check if stop has been requested.

        Returns:
            True if stop was signaled.
        """
        return self.stop_token.is_set()

    @abstractmethod
    def run_loop(self) -> None:
        """Main execution loop. Must honor self.stop_token."""

    def on_stop(self) -> None:  # noqa: B027 - optional hook, intentionally empty
        """Hook called after run_loop. Override for cleanup."""
