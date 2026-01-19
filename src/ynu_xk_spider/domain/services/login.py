"""Login service for YNU course selection system."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Optional
from urllib.parse import parse_qs, urlparse

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from ...exceptions import CaptchaError, LoginError
from ..models import SessionData

if TYPE_CHECKING:
    from ...browser.captcha import CaptchaSolver
    from ...browser.manager import BrowserManager
    from ...config import AppSettings

logger = logging.getLogger(__name__)


class LoginService:
    """Handles authentication workflow via Selenium.

    Manages the complete login flow including:
    - Page navigation
    - Captcha solving
    - Form submission with retry
    - Session data extraction

    Attributes:
        _settings: Application settings.
        _browser: Browser manager instance.
        _solver: Captcha solver instance.
    """

    MAX_LOGIN_ATTEMPTS = 10
    MAX_CLICK_ATTEMPTS = 5
    INPUT_DELAY = 1.0
    CLICK_DELAY = 1.0

    def __init__(
        self,
        settings: AppSettings,
        browser: BrowserManager,
        solver: CaptchaSolver,
    ) -> None:
        """Initialize login service.

        Args:
            settings: Application settings.
            browser: Browser manager for WebDriver access.
            solver: Captcha solver instance.
        """
        self._settings = settings
        self._browser = browser
        self._solver = solver

    def login(self) -> SessionData:
        """Perform login and return session data.

        Returns:
            SessionData with cookies, token, and batch code.

        Raises:
            LoginError: On authentication failure.
            CaptchaError: On captcha solving failure.
        """
        driver = self._browser.get_driver()

        try:
            logger.info("Opening login page: %s", self._settings.base_url)
            driver.get(self._settings.base_url)
            time.sleep(2)

            if not self._perform_login(driver):
                raise LoginError("Login failed after maximum attempts")

            time.sleep(1)
            self._navigate_to_course_selection(driver)

            return self._extract_session_data(driver)

        except (LoginError, CaptchaError):
            raise
        except Exception as exc:
            logger.error("Login error: %s", exc)
            raise LoginError(f"Login failed: {exc}") from exc

    def _perform_login(self, driver: WebDriver) -> bool:
        """Execute login attempts with captcha solving.

        Args:
            driver: WebDriver instance.

        Returns:
            True if login succeeded.
        """
        for attempt in range(self.MAX_LOGIN_ATTEMPTS):
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "vcodeImg"))
                )
                img_tag = driver.find_element(By.ID, "vcodeImg")

                if not img_tag.get_attribute("src"):
                    driver.refresh()
                    time.sleep(2)
                    continue

                img_bytes = img_tag.screenshot_as_png

                try:
                    captcha_code = self._solver.solve(img_bytes)
                except CaptchaError as e:
                    logger.warning("Captcha solve failed: %s, refreshing", e)
                    img_tag.click()
                    time.sleep(2)
                    continue

                logger.debug("Attempt %d: captcha=%s", attempt + 1, captcha_code)

                self._fill_login_form(driver, captcha_code)

                result = self._submit_and_check(driver, img_tag)

                if result == "success":
                    return True
                elif result == "captcha_error":
                    continue
                elif result == "auth_error":
                    raise LoginError("Invalid username or password")

            except (LoginError, CaptchaError):
                raise
            except Exception as exc:
                logger.warning("Login attempt %d failed: %s", attempt + 1, exc)
                driver.refresh()
                time.sleep(3)

        return False

    def _fill_login_form(self, driver: WebDriver, captcha_code: str) -> None:
        """Fill username, password, and captcha fields.

        Args:
            driver: WebDriver instance.
            captcha_code: Solved captcha text.
        """
        user_ele = driver.find_element(By.ID, "loginName")
        user_ele.clear()
        user_ele.send_keys(self._settings.student_code)
        time.sleep(self.INPUT_DELAY)

        pwd_ele = driver.find_element(By.ID, "loginPwd")
        pwd_ele.clear()
        pwd_ele.send_keys(self._settings.password.get_secret_value())
        time.sleep(self.INPUT_DELAY)

        code_ele = driver.find_element(By.ID, "verifyCode")
        code_ele.clear()
        code_ele.send_keys(captcha_code)
        time.sleep(self.INPUT_DELAY)

    def _submit_and_check(self, driver: WebDriver, img_tag: WebElement) -> str:
        """Submit login form and check result.

        Args:
            driver: WebDriver instance.
            img_tag: Captcha image element for refresh.

        Returns:
            "success", "captcha_error", "auth_error", or "unknown".
        """
        for click_i in range(self.MAX_CLICK_ATTEMPTS):
            try:
                login_btn = driver.find_element(By.ID, "studentLoginBtn")
                login_btn.click()
            except Exception:
                pass

            time.sleep(self.CLICK_DELAY)

            try:
                err_ele = driver.find_element(By.ID, "errorMsg")
                if err_ele.is_displayed() and err_ele.text:
                    if "验证码" in err_ele.text:
                        logger.warning("Captcha error detected")
                        img_tag.click()
                        time.sleep(2)
                        return "captcha_error"
                    elif "认证失败" in err_ele.text or "密码" in err_ele.text:
                        return "auth_error"
            except NoSuchElementException:
                # The error message element may legitimately be absent; treat as no error and retry.
                pass

            try:
                next_page_eles = driver.find_elements(
                    By.XPATH, '//button[contains(@class, "bh-pull-right")]'
                )
                if len(next_page_eles) > 0:
                    logger.info("Login page transition successful")
                    return "success"
            except Exception:
                pass

            logger.debug("Click %d: no response, retrying", click_i + 1)

        driver.refresh()
        time.sleep(3)
        return "unknown"

    def _navigate_to_course_selection(self, driver: WebDriver) -> None:
        """Navigate through post-login pages to course selection.

        Args:
            driver: WebDriver instance.

        Raises:
            LoginError: If navigation fails.
        """
        try:
            enter_xpath = '//button[@class="bh-btn cv-btn bh-btn-primary bh-pull-right"]'
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, enter_xpath))
            )
            driver.find_element(By.XPATH, enter_xpath).click()
            logger.info("Clicked entry button")
            time.sleep(1)
        except TimeoutException:
            logger.debug("Entry button not found, may already be on next page")

        ok_xpath = '//button[@class="bh-btn bh-btn bh-btn-primary bh-pull-right"]'
        for retry in range(3):
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, ok_xpath))
                )
                ok_ele = driver.find_element(By.XPATH, ok_xpath)
                if ok_ele.is_displayed():
                    ok_ele.click()
                    logger.info("Clicked confirmation dialog")
                    time.sleep(1)
                    break
            except TimeoutException:
                if retry < 2:
                    time.sleep(1)

        try:
            start_ele = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "courseBtn"))
            )
            driver.execute_script("arguments[0].click();", start_ele)
            logger.info("Clicked courseBtn via JS")
            time.sleep(1)
        except TimeoutException:
            raise LoginError("Could not find courseBtn")

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "aPublicCourse"))
            )
            logger.info("Course selection page loaded")
        except TimeoutException:
            logger.debug("Course selection page element not found, continuing")

        time.sleep(2)

    def _extract_session_data(self, driver: WebDriver) -> SessionData:
        """Extract authentication data from browser session.

        Args:
            driver: WebDriver instance.

        Returns:
            SessionData with cookies, token, and batch code.

        Raises:
            LoginError: If extraction fails.
        """
        current_url = driver.current_url
        token: Optional[str] = None

        if "token=" in current_url:
            token = current_url.split("token=")[-1].split("&")[0]
        else:
            parsed = urlparse(current_url)
            token = parse_qs(parsed.query).get("token", [None])[0]

        if not token:
            raise LoginError("Failed to extract token from URL")

        batch_str = driver.execute_script('return sessionStorage.getItem("currentBatch");')
        if not batch_str:
            raise LoginError("Failed to get batch code from sessionStorage")

        try:
            batch_code = json.loads(batch_str).get("code")
        except (json.JSONDecodeError, KeyError) as exc:
            raise LoginError(f"Failed to parse batch code: {exc}") from exc

        if not batch_code:
            raise LoginError("Batch code is empty")

        selenium_cookies = driver.get_cookies()
        cookies = {item["name"]: item["value"] for item in selenium_cookies}

        logger.info("Session extracted: token=%s..., batch=%s", token[:8], batch_code)

        # Close browser after successful login (HTTP client takes over)
        self._browser.shutdown()
        logger.info("Browser closed after successful login")

        return SessionData(cookies=cookies, token=token, batch_code=batch_code)
