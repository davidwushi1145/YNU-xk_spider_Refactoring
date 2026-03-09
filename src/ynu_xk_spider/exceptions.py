"""Custom exception hierarchy for the spider application.

All application-specific exceptions inherit from SpiderError to enable
unified error handling at the application boundary.
"""

from __future__ import annotations


class SpiderError(Exception):
    """Base exception for all spider-related errors."""


class ConfigError(SpiderError):
    """Configuration validation or loading failure."""


class BrowserError(SpiderError):
    """WebDriver lifecycle or browser automation failure."""


class LoginError(SpiderError):
    """Authentication workflow failure."""


class CaptchaError(LoginError):
    """Captcha recognition or validation failure."""


class NetworkError(SpiderError):
    """HTTP transport or connectivity failure."""


class SessionExpiredError(NetworkError):
    """Server session has expired, requires re-login."""


class CourseSelectionError(SpiderError):
    """Course selection business logic failure."""


class StopRequestedError(SpiderError):
    """Operation aborted because stop was requested."""
