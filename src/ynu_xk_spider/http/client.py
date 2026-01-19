"""HTTP client wrapper with retry and session management."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, Callable, Optional

import requests

from ..exceptions import NetworkError, SessionExpiredError
from ..utils.retry import retry

if TYPE_CHECKING:
    from ..config import AppSettings

logger = logging.getLogger(__name__)


class HttpClient:
    """HTTP client with automatic retry and session management.

    Wraps requests.Session with:
    - Automatic retry on network errors
    - Cookie persistence
    - Standard headers for YNU system
    - Session expiration detection

    Attributes:
        _session: Underlying requests.Session.
        _timeout: Default request timeout.
        _settings: Application settings reference.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, settings: AppSettings) -> None:
        """Initialize HTTP client.

        Args:
            settings: Application settings.
        """
        self._settings = settings
        self._timeout = settings.http_timeout
        self._session = requests.Session()
        self._session_lock = threading.Lock()
        self._token: Optional[str] = None
        self._setup_session()

    def _setup_session(self) -> None:
        """Configure session with default headers."""
        self._session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Referer": f"{self._settings.base_url}xsxkapp/sys/xsxkapp/*default/index.do",
                "Origin": self._settings.base_url.rstrip("/"),
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def set_auth(self, token: str, cookies: dict[str, str]) -> None:
        """Set authentication credentials.

        Args:
            token: Authentication token from login.
            cookies: Cookies from browser session.
        """
        self._token = token
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Token": token,
            }
        )
        self._session.cookies.update(cookies)
        logger.debug("Auth configured with token: %s...", token[:8] if token else "N/A")

    @property
    def token(self) -> Optional[str]:
        """Current authentication token."""
        return self._token

    def _create_retry_decorator(self) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
        """Create retry decorator with current settings."""
        return retry(
            exceptions=(requests.RequestException, NetworkError),
            tries=self._settings.max_retries,
            delay=self._settings.retry_backoff,
            backoff=self._settings.retry_factor,
            jitter=0.1,
            logger=logger,
        )

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Send GET request with retry.

        Args:
            url: Target URL.
            **kwargs: Additional arguments for requests.get.

        Returns:
            Response object.

        Raises:
            NetworkError: On request failure.
            SessionExpiredError: If session is expired.
        """
        kwargs.setdefault("timeout", self._timeout)

        @self._create_retry_decorator()
        def _get() -> requests.Response:
            try:
                with self._session_lock:
                    resp = self._session.get(url, **kwargs)
                self._check_session_expired(resp)
                return resp
            except requests.RequestException as exc:
                raise NetworkError(str(exc)) from exc

        return _get()

    def post(
        self,
        url: str,
        data: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send POST request with retry.

        Args:
            url: Target URL.
            data: Form data.
            json: JSON payload.
            **kwargs: Additional arguments for requests.post.

        Returns:
            Response object.

        Raises:
            NetworkError: On request failure.
            SessionExpiredError: If session is expired.
        """
        kwargs.setdefault("timeout", self._timeout)

        @self._create_retry_decorator()
        def _post() -> requests.Response:
            try:
                with self._session_lock:
                    resp = self._session.post(url, data=data, json=json, **kwargs)
                self._check_session_expired(resp)
                return resp
            except requests.RequestException as exc:
                raise NetworkError(str(exc)) from exc

        return _post()

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
        self._session.close()
