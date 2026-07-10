"""Login service for YNU course selection system."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from ...exceptions import CaptchaError, LoginError, StopRequestedError
from ...utils.stop import StopToken
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
    MAX_START_BUTTON_ATTEMPTS = 3
    INPUT_DELAY = 1.0
    CLICK_DELAY = 1.0

    def __init__(
        self,
        settings: AppSettings,
        browser: BrowserManager,
        solver: CaptchaSolver,
        stop: StopToken | None = None,
    ) -> None:
        """Initialize login service.

        Args:
            settings: Application settings.
            browser: Browser manager for WebDriver access.
            solver: Captcha solver instance.
            stop: Optional stop token signaling shutdown requests.
        """
        self._settings = settings
        self._browser = browser
        self._solver = solver
        self._stop = stop or StopToken()

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
            self._wait_or_stop(2)

            if not self._perform_login(driver):
                raise LoginError("Login failed after maximum attempts")

            self._wait_or_stop(1)
            self._navigate_to_course_selection(driver)

            return self._extract_session_data(driver)

        except (LoginError, CaptchaError, StopRequestedError):
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
                self._wait_until(
                    driver,
                    10,
                    EC.presence_of_element_located((By.ID, "vcodeImg"))
                )
                img_tag = driver.find_element(By.ID, "vcodeImg")

                if not img_tag.get_attribute("src"):
                    driver.refresh()
                    self._wait_or_stop(2)
                    continue

                img_bytes = img_tag.screenshot_as_png

                try:
                    captcha_code = self._solver.solve(img_bytes)
                except CaptchaError as e:
                    logger.warning("Captcha solve failed: %s, refreshing", e)
                    img_tag.click()
                    self._wait_or_stop(2)
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

            except (LoginError, CaptchaError, StopRequestedError):
                raise
            except Exception as exc:
                logger.warning("Login attempt %d failed: %s", attempt + 1, exc)
                driver.refresh()
                self._wait_or_stop(3)

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
        self._wait_or_stop(self.INPUT_DELAY)

        pwd_ele = driver.find_element(By.ID, "loginPwd")
        pwd_ele.clear()
        pwd_ele.send_keys(self._settings.password.get_secret_value())
        self._wait_or_stop(self.INPUT_DELAY)

        code_ele = driver.find_element(By.ID, "verifyCode")
        code_ele.clear()
        code_ele.send_keys(captcha_code)
        self._wait_or_stop(self.INPUT_DELAY)

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

            self._wait_or_stop(self.CLICK_DELAY)

            try:
                err_ele = driver.find_element(By.ID, "errorMsg")
                if err_ele.is_displayed() and err_ele.text:
                    if "验证码" in err_ele.text:
                        logger.warning("Captcha error detected")
                        img_tag.click()
                        self._wait_or_stop(2)
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
        self._wait_or_stop(3)
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
            self._wait_until(
                driver,
                8,
                EC.presence_of_element_located((By.XPATH, enter_xpath))
            )
            driver.find_element(By.XPATH, enter_xpath).click()
            logger.info("Clicked entry button")
            self._wait_or_stop(1)
        except TimeoutException:
            logger.debug("Entry button not found, may already be on next page")

        self._handle_batch_selection_dialog(driver)
        self._handle_generic_confirmation_dialog(driver)

        try:
            self._wait_until(
                driver,
                20,
                EC.presence_of_element_located((By.ID, "courseBtn"))
            )
        except TimeoutException as err:
            raise LoginError("Could not find courseBtn") from err

        if not self._open_course_selection_page(driver):
            raise LoginError("Failed to open course selection page after clicking courseBtn")

        self._wait_or_stop(2)

    def _handle_batch_selection_dialog(self, driver: WebDriver) -> None:
        """Handle elective batch dialog, including acknowledgement checkbox.

        Third-round selection may require:
        1) selecting an elective batch radio option;
        2) checking the acknowledgement checkbox ("我已知晓");
        3) clicking the confirm button ("确定").
        """
        radio_css = 'input.cv-electiveBatch-select[name="electiveBatchSelect"]'
        confirm_xpath = (
            '//button[contains(@class, "bh-btn-primary") and normalize-space()="确定"]'
        )
        ack_css = 'input#tyxz-input, input[name="tyxz"]'

        try:
            self._wait_until(
                driver,
                5,
                EC.presence_of_element_located((By.CSS_SELECTOR, radio_css))
            )
        except TimeoutException:
            logger.debug("Elective batch dialog not present")
            return

        radios = driver.find_elements(By.CSS_SELECTOR, radio_css)
        if not radios:
            logger.debug("Elective batch radios not found")
            return

        target_radio = self._pick_selectable_batch_radio(radios)
        if target_radio is None:
            raise LoginError("No selectable elective batch found")

        if not target_radio.is_selected():
            self._safe_click(driver, target_radio)
            self._wait_or_stop(0.3)
            if not target_radio.is_selected():
                raise LoginError("Failed to select elective batch radio")
        logger.info("Selected elective batch")

        ack_candidates = driver.find_elements(By.CSS_SELECTOR, ack_css)
        ack_checkbox = next(
            (
                ele
                for ele in ack_candidates
                if ele.is_displayed() and ele.is_enabled()
            ),
            None,
        )
        if ack_checkbox is not None and not ack_checkbox.is_selected():
            self._safe_click(driver, ack_checkbox)
            self._wait_or_stop(0.2)
            logger.info("Checked batch acknowledgement checkbox")

        confirm_buttons = driver.find_elements(By.XPATH, confirm_xpath)
        confirm_button = next(
            (ele for ele in confirm_buttons if ele.is_displayed() and ele.is_enabled()),
            None,
        )
        if confirm_button is None:
            raise LoginError("Elective batch confirm button not found")

        self._safe_click(driver, confirm_button)
        logger.info("Confirmed elective batch dialog")

        try:
            self._wait_until(
                driver,
                8,
                lambda d: bool(d.find_elements(By.ID, "courseBtn"))
                or not d.find_elements(By.CSS_SELECTOR, radio_css)
            )
        except TimeoutException:
            logger.debug("Elective batch dialog may still be visible after confirm")

    def _handle_generic_confirmation_dialog(self, driver: WebDriver) -> None:
        """Handle generic post-login confirmation dialogs when present."""
        ok_xpath = (
            '//button[contains(@class, "bh-btn-primary") and '
            'normalize-space()="确定"]'
        )
        for retry in range(3):
            try:
                self._wait_until(
                    driver,
                    5,
                    EC.presence_of_element_located((By.XPATH, ok_xpath))
                )
                ok_elements = driver.find_elements(By.XPATH, ok_xpath)
                ok_ele = next(
                    (
                        ele
                        for ele in ok_elements
                        if ele.is_displayed() and ele.is_enabled()
                    ),
                    None,
                )
                if ok_ele is not None:
                    self._safe_click(driver, ok_ele)
                    logger.info("Clicked confirmation dialog")
                    self._wait_or_stop(1)
                    break
            except TimeoutException:
                if retry < 2:
                    self._wait_or_stop(1)

    def _pick_selectable_batch_radio(
        self,
        radios: list[WebElement],
    ) -> WebElement | None:
        """Pick an available elective batch radio by data-value metadata."""
        fallback: WebElement | None = None

        for radio in radios:
            if not radio.is_displayed() or not radio.is_enabled():
                continue
            if fallback is None:
                fallback = radio

            data_value = radio.get_attribute("data-value")
            if not data_value:
                continue

            try:
                batch_data = json.loads(data_value)
            except json.JSONDecodeError:
                continue
            if not isinstance(batch_data, dict):
                continue

            can_select = str(batch_data.get("canSelect", "1"))
            no_select_reason = batch_data.get("noSelectReason")
            if can_select == "1" and not no_select_reason:
                return radio

        return fallback

    def _safe_click(self, driver: WebDriver, element: WebElement) -> None:
        """Click element with JS fallback for intercepted clicks."""
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                element,
            )
        except Exception:
            pass

        try:
            element.click()
            return
        except Exception:
            pass

        try:
            driver.execute_script("arguments[0].click();", element)
        except Exception as exc:
            raise LoginError(f"Failed to click required element: {exc}") from exc

    def _prepare_for_start_button_click(self, driver: WebDriver) -> None:
        """Dismiss transient overlays and force viewport to page top."""
        try:
            active_ele = driver.switch_to.active_element
            active_ele.send_keys(Keys.ESCAPE)
        except Exception as exc:
            logger.debug("Failed to send ESC to active element: %s", exc)

        try:
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ESCAPE)
        except Exception as exc:
            logger.debug("Failed to send ESC to body: %s", exc)

        try:
            driver.execute_script("window.scrollTo(0, 0);")
        except Exception as exc:
            logger.debug("Failed to scroll viewport to top before courseBtn click: %s", exc)

        try:
            driver.execute_script(
                """
                window.scrollTo(0, 0);
                document.documentElement.scrollTop = 0;
                document.body.scrollTop = 0;
                document.documentElement.style.overflow = 'hidden';
                document.body.style.overflow = 'hidden';
                """
            )
        except Exception as exc:
            logger.debug("Failed to enforce page top/overflow state before courseBtn click: %s", exc)

    def _open_course_selection_page(self, driver: WebDriver) -> bool:
        """Click start button and verify course page is actually opened."""
        for attempt in range(self.MAX_START_BUTTON_ATTEMPTS):
            self._prepare_for_start_button_click(driver)
            try:
                start_ele = driver.find_element(By.ID, "courseBtn")
            except NoSuchElementException:
                logger.warning(
                    "courseBtn not found when attempting to open course page "
                    "(attempt %d/%d)",
                    attempt + 1,
                    self.MAX_START_BUTTON_ATTEMPTS,
                )
                self._wait_or_stop(1)
                continue
            self._safe_click(driver, start_ele)
            logger.info("Clicked courseBtn (attempt %d)", attempt + 1)

            if self._wait_course_page_ready(driver, timeout=10):
                return True

            logger.warning(
                "courseBtn click did not open course page (attempt %d/%d)",
                attempt + 1,
                self.MAX_START_BUTTON_ATTEMPTS,
            )
            self._wait_or_stop(1)

        return False

    def _wait_course_page_ready(self, driver: WebDriver, timeout: int) -> bool:
        """Check if we have successfully entered the course selection page."""
        try:
            self._wait_until(
                driver,
                timeout,
                lambda d: (
                    bool(d.find_elements(By.ID, "aPublicCourse"))
                    or bool(
                        d.execute_script('return sessionStorage.getItem("currentBatch");')
                    )
                )
            )
            logger.info("Course selection page loaded")
            return True
        except TimeoutException:
            return False

    def _wait_until(
        self,
        driver: WebDriver,
        timeout: float,
        condition: Callable[[WebDriver], object],
    ) -> object:
        """Wait for a Selenium condition while allowing stop interruption."""
        deadline = time.monotonic() + timeout
        while True:
            self._stop.raise_if_set()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutException()
            try:
                return WebDriverWait(driver, min(0.2, remaining)).until(condition)
            except TimeoutException:
                continue

    def _wait_or_stop(self, delay: float) -> None:
        """Block for a delay, aborting when stop is requested.

        Raises:
            StopRequestedError: If stop is requested before the delay elapses.
        """
        if not self._stop.wait(delay):
            raise StopRequestedError("Stop requested")

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
        token: str | None = None

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

        return SessionData(cookies=cookies, token=token, batch_code=batch_code)
