"""Thread-safe singleton WebDriver lifecycle manager."""

from __future__ import annotations

import atexit
import logging
import threading
from typing import TYPE_CHECKING, cast

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver

from ..exceptions import BrowserError

if TYPE_CHECKING:
    from ..config import AppSettings

logger = logging.getLogger(__name__)


class BrowserManager:
    """Singleton manager for WebDriver lifecycle.

    Thread-safe lazy initialization ensures only one driver instance exists.
    Automatic cleanup is registered via atexit.

    Attributes:
        _instance: Singleton instance.
        _inst_lock: Lock for singleton creation.
    """

    _instance: BrowserManager | None = None
    _inst_lock = threading.Lock()

    def __init__(self, settings: AppSettings) -> None:
        """Initialize manager with settings. Use instance() instead."""
        self._settings = settings
        self._driver: WebDriver | None = None
        self._driver_lock = threading.Lock()
        atexit.register(self.shutdown)

    @classmethod
    def instance(cls, settings: AppSettings) -> BrowserManager:
        """Get or create the singleton instance.

        Args:
            settings: Application settings for driver configuration.

        Returns:
            The singleton BrowserManager instance.
        """
        if cls._instance is None:
            with cls._inst_lock:
                if cls._instance is None:
                    cls._instance = cls(settings)
                    logger.debug("BrowserManager singleton created")
        elif cls._instance._settings != settings:
            logger.warning("BrowserManager already initialized with different settings")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing purposes."""
        with cls._inst_lock:
            if cls._instance is not None:
                cls._instance.shutdown()
                cls._instance = None

    def get_driver(self) -> WebDriver:
        """Get or create a live WebDriver instance.

        Returns:
            Active WebDriver instance.

        Raises:
            BrowserError: If driver creation fails.
        """
        if self._driver is not None:
            return self._driver

        with self._driver_lock:
            if self._driver is None:
                self._driver = self._create_driver()
        return self._driver

    def _create_driver(self) -> WebDriver:
        """Create a new Chrome WebDriver instance."""
        try:
            options = Options()

            if self._settings.headless:
                options.add_argument("--headless=new")

            # Disable Chrome credential UI to avoid native "save password" popups
            # that can steal focus and block automated page clicks.
            options.add_experimental_option(
                "prefs",
                {
                    "credentials_enable_service": False,
                    "profile.password_manager_enabled": False,
                    "profile.password_manager_leak_detection": False,
                    "autofill.profile_enabled": False,
                    "autofill.credit_card_enabled": False,
                },
            )
            options.add_argument(
                "--disable-features="
                "PasswordManagerOnboarding,"
                "PasswordManagerRedesign,"
                "PasswordManagerEnabled"
            )
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            if self._settings.chrome_driver_path:
                service = Service(executable_path=str(self._settings.chrome_driver_path))
                driver = cast(WebDriver, webdriver.Chrome(service=service, options=options))
            else:
                driver = cast(WebDriver, webdriver.Chrome(options=options))

            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    """
                },
            )

            logger.info("WebDriver created successfully")
            return driver

        except Exception as exc:
            logger.error("Failed to create WebDriver: %s", exc)
            raise BrowserError(f"Failed to start WebDriver: {exc}") from exc

    def shutdown(self) -> None:
        """Quit the WebDriver if present. Safe to call multiple times."""
        with self._driver_lock:
            if self._driver is not None:
                try:
                    self._driver.quit()
                    logger.info("WebDriver shut down")
                except Exception as exc:
                    logger.warning("Error during WebDriver shutdown: %s", exc)
                finally:
                    self._driver = None

    def restart(self) -> WebDriver:
        """Shutdown and create a fresh driver instance.

        Returns:
            New WebDriver instance.
        """
        self.shutdown()
        return self.get_driver()
