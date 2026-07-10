"""Notification services for selection results."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Protocol

import requests

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    """Anything that can push a notification to the user."""

    @property
    def enabled(self) -> bool:
        """Whether sending is configured."""
        ...

    def send(self, title: str, content: str) -> None:
        """Send a notification."""
        ...


class ServerChanNotifier:
    """Synchronous WeChat push via ServerChan."""

    def __init__(self, server_key: str | None = None) -> None:
        """Initialize notifier.

        Args:
            server_key: ServerChan API key; empty or None disables sending.
        """
        self._server_key = server_key

    @property
    def enabled(self) -> bool:
        """Whether notification sending is configured."""
        return bool(self._server_key)

    def send(self, title: str, content: str) -> None:
        """Send notification via WeChat.

        Args:
            title: Notification title.
            content: Notification body.
        """
        if not self._server_key:
            return

        try:
            url = f"https://sctapi.ftqq.com/{self._server_key}.send"
            requests.post(url, data={"text": title, "desp": content}, timeout=5)
            logger.debug("Notification sent: %s", title)
        except Exception as exc:
            logger.warning("Notification failed: %s", exc)


class AsyncNotifier:
    """Wraps a notifier so sends happen off the caller's thread.

    Sends are dispatched on a single background worker so the selection
    hot path never blocks on network I/O. flush() waits for pending
    sends and releases the worker; the wrapper is reusable afterwards
    (the worker is recreated on the next send).
    """

    def __init__(self, inner: Notifier) -> None:
        """Initialize wrapper.

        Args:
            inner: Notifier performing the actual (blocking) send.
        """
        self._inner = inner
        self._executor: ThreadPoolExecutor | None = None
        self._futures: list[Future[None]] = []
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """Whether the wrapped notifier is configured."""
        return self._inner.enabled

    def send(self, title: str, content: str) -> None:
        """Queue a notification without blocking the caller.

        Args:
            title: Notification title.
            content: Notification body.
        """
        if not self._inner.enabled:
            return
        with self._lock:
            self._futures = [f for f in self._futures if not f.done()]
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="notification-sender",
                )
            self._futures.append(self._executor.submit(self._inner.send, title, content))

    def flush(self, timeout: float | None = None) -> None:
        """Wait for pending sends to finish and release the worker.

        Args:
            timeout: Optional maximum seconds to wait; None waits until done.
        """
        with self._lock:
            futures = list(self._futures)
            executor = self._executor
            self._futures.clear()
            self._executor = None

        if futures:
            wait(futures, timeout=timeout)

        if executor is not None:
            executor.shutdown(wait=timeout is None)
