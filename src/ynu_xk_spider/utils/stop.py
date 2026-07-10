"""Unified cancellation primitive shared across the application."""

from __future__ import annotations

import threading
import weakref

from ..exceptions import StopRequestedError


class StopToken:
    """Cooperative stop signal wrapping a threading.Event.

    A single token is owned by the spider and handed to every component
    that sleeps or loops, so waiting is native blocking (no polling
    slices) and stop semantics are identical everywhere. Child tokens
    provide scoped cancellation (e.g. one monitoring batch) that also
    fires when the parent stops.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._children: weakref.WeakSet[StopToken] = weakref.WeakSet()
        self._parent: StopToken | None = None
        self._lock = threading.Lock()

    def set(self) -> None:
        """Request stop, propagating to child tokens."""
        self._event.set()
        with self._lock:
            children = list(self._children)
        for child in children:
            child.set()
        self._parent = None

    def is_set(self) -> bool:
        """Return True if stop has been requested."""
        return self._event.is_set()

    def wait(self, delay: float) -> bool:
        """Block for up to delay seconds.

        Args:
            delay: Maximum time to wait in seconds.

        Returns:
            True if the full delay elapsed, False if interrupted by stop.
        """
        return not self._event.wait(delay)

    def raise_if_set(self) -> None:
        """Raise when stop has been requested.

        Raises:
            StopRequestedError: If the token is set.
        """
        if self._event.is_set():
            raise StopRequestedError("Stop requested")

    def child(self) -> StopToken:
        """Create a linked token that also stops when this one does."""
        token = StopToken()
        # Keep the propagation chain alive while any descendant remains active.
        token._parent = self
        with self._lock:
            self._children.add(token)
        if self._event.is_set():
            token.set()
        return token
