"""HTTP client wrapper with retry and session management."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import requests

from ..exceptions import NetworkError, SessionExpiredError
from ..utils.retry import retry

if TYPE_CHECKING:
    from ..config import AppSettings
    from ..utils.stop import StopToken

logger = logging.getLogger(__name__)


@dataclass
class _ThreadSessionState:
    """Thread-local requests session and its auth generation."""

    session: requests.Session
    generation: int


class HttpClient:
    """HTTP client with automatic retry and session management.

    Wraps requests.Session with:
    - Automatic retry on network errors
    - Cookie persistence
    - Standard headers for YNU system
    - Session expiration detection

    Attributes:
        _thread_local: Per-thread session state storage.
        _sessions: Registry of active sessions for coordinated shutdown.
        _timeout: Default request timeout.
        _settings: Application settings reference.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        settings: AppSettings,
        stop: StopToken | None = None,
    ) -> None:
        """Initialize HTTP client.

        Args:
            settings: Application settings.
            stop: Optional stop token used to interrupt retry backoff.
        """
        self._settings = settings
        self._timeout = settings.http_timeout
        self._stop = stop
        self._thread_local = threading.local()
        self._sessions: list[requests.Session] = []
        self._sessions_lock = threading.Lock()
        self._auth_lock = threading.Lock()
        self._token: str | None = None
        self._cookies: dict[str, str] = {}
        self._auth_generation = 0
        self._base_headers = self._build_base_headers()
        self._retry = self._create_retry_decorator()

    def _build_base_headers(self) -> dict[str, str]:
        """Build default headers shared by all per-thread sessions."""
        return {
            "User-Agent": self.USER_AGENT,
            "Referer": f"{self._settings.base_url}xsxkapp/sys/xsxkapp/*default/index.do",
            "Origin": self._settings.base_url.rstrip("/"),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _create_session(
        self,
        token: str | None,
        cookies: dict[str, str],
    ) -> requests.Session:
        """Create a requests session bound to the current auth snapshot."""
        session = requests.Session()
        session.headers.update(self._base_headers)
        if token:
            session.headers.update(
                {
                    "Authorization": f"Bearer {token}",
                    "Token": token,
                }
            )
        if cookies:
            session.cookies.update(cookies)
        with self._sessions_lock:
            self._sessions.append(session)
        return session

    def _discard_session(self, session: requests.Session) -> None:
        """Remove a session from shutdown tracking if it is no longer current."""
        with self._sessions_lock:
            try:
                self._sessions.remove(session)
            except ValueError:
                return

    def _get_session(self) -> requests.Session:
        """Get a thread-local session for the current auth generation."""
        with self._auth_lock:
            generation = self._auth_generation
            token = self._token
            cookies = dict(self._cookies)

        state = getattr(self._thread_local, "session_state", None)
        if isinstance(state, _ThreadSessionState) and state.generation == generation:
            return state.session

        if isinstance(state, _ThreadSessionState):
            self._discard_session(state.session)
            try:
                state.session.close()
            except Exception:
                logger.debug("Failed to close stale thread-local HTTP session", exc_info=True)

        session = self._create_session(token, cookies)
        self._thread_local.session_state = _ThreadSessionState(
            session=session,
            generation=generation,
        )
        return session

    def set_auth(self, token: str, cookies: dict[str, str]) -> None:
        """Set authentication credentials.

        Args:
            token: Authentication token from login.
            cookies: Cookies from browser session.
        """
        with self._auth_lock:
            self._token = token
            self._cookies = dict(cookies)
            self._auth_generation += 1
        logger.debug("Auth configured with token: %s...", token[:8] if token else "N/A")

    @property
    def token(self) -> str | None:
        """Current authentication token."""
        with self._auth_lock:
            return self._token

    def _sleep_for_retry(self, delay: float) -> bool:
        """Sleep between retries, aborting early when stop is requested."""
        if self._stop is None:
            time.sleep(delay)
            return True
        return self._stop.wait(delay)

    def _create_retry_decorator(
        self,
    ) -> Callable[[Callable[[], requests.Response]], Callable[[], requests.Response]]:
        """Create retry decorator with current settings."""
        return retry(
            exceptions=(requests.RequestException, NetworkError),
            tries=self._settings.max_retries,
            delay=self._settings.retry_backoff,
            backoff=self._settings.retry_factor,
            jitter=0.1,
            logger=logger,
            sleep=self._sleep_for_retry,
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Send an HTTP request with retry and session-expiry detection.

        Args:
            method: HTTP method name (e.g. "GET", "POST").
            url: Target URL.
            **kwargs: Additional arguments for requests.Session.request.

        Returns:
            Response object.

        Raises:
            NetworkError: On request failure.
            SessionExpiredError: If session is expired.
        """
        kwargs.setdefault("timeout", self._timeout)

        @self._retry
        def _do() -> requests.Response:
            try:
                session = self._get_session()
                resp = session.request(method, url, **kwargs)
                self._check_session_expired(resp)
                return resp
            except requests.RequestException as exc:
                raise NetworkError(str(exc)) from exc

        return _do()

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Send GET request with retry.

        Args:
            url: Target URL.
            **kwargs: Additional arguments for the underlying request.

        Returns:
            Response object.

        Raises:
            NetworkError: On request failure.
            SessionExpiredError: If session is expired.
        """
        return self._request("GET", url, **kwargs)

    def post(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send POST request with retry.

        Args:
            url: Target URL.
            data: Form data.
            json: JSON payload.
            **kwargs: Additional arguments for the underlying request.

        Returns:
            Response object.

        Raises:
            NetworkError: On request failure.
            SessionExpiredError: If session is expired.
        """
        return self._request("POST", url, data=data, json=json, **kwargs)

    def _check_session_expired(self, resp: requests.Response) -> None:
        """Check if response indicates session expiration.

        Args:
            resp: Response to check.

        Raises:
            SessionExpiredError: If session has expired.
            NetworkError: If response status indicates an error.
        """
        if resp.status_code == 401:
            raise SessionExpiredError("HTTP 401 - Session expired")

        if "未查询到登录信息" in resp.text:
            raise SessionExpiredError("Session expired - login info not found")

        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            raise NetworkError(f"HTTP {resp.status_code}: {exc}") from exc

    def close(self) -> None:
        """Close the session."""
        with self._sessions_lock:
            sessions = list(self._sessions)
            self._sessions.clear()

        for session in sessions:
            session.close()

        self._thread_local = threading.local()
