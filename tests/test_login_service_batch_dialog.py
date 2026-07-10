from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By

from ynu_xk_spider.config import AppSettings
from ynu_xk_spider.domain.services.login import LoginService
from ynu_xk_spider.exceptions import StopRequestedError
from ynu_xk_spider.utils.stop import StopToken


class _DummyBrowser:
    def get_driver(self) -> Any:
        raise AssertionError("Dummy browser should not be asked for a real driver in this test")

    def shutdown(self) -> None:
        return None


class _DummySolver:
    def solve(self, img_bytes: bytes) -> str:
        return "0000"


class _ImmediateWait:
    def __init__(self, driver: _FakeDriver, timeout: int) -> None:
        self.driver = driver
        self.timeout = timeout

    def until(self, condition: Callable[[_FakeDriver], object]) -> object:
        try:
            result = condition(self.driver)
        except NoSuchElementException:
            result = False
        if not result:
            raise TimeoutException()
        return result


class _FakeElement:
    def __init__(
        self,
        *,
        displayed: bool = True,
        enabled: bool = True,
        selected: bool = False,
        attrs: dict[str, str] | None = None,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        self._displayed = displayed
        self._enabled = enabled
        self._selected = selected
        self._attrs = attrs or {}
        self._on_click = on_click
        self.click_count = 0

    def is_displayed(self) -> bool:
        return self._displayed

    def is_enabled(self) -> bool:
        return self._enabled

    def is_selected(self) -> bool:
        return self._selected

    def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)

    def click(self) -> None:
        self.click_count += 1
        if self._attrs.get("type") in {"radio", "checkbox"}:
            self._selected = True
        if self._on_click is not None:
            self._on_click()


class _FakeDriver:
    RADIO_CSS = 'input.cv-electiveBatch-select[name="electiveBatchSelect"]'
    ACK_CSS = 'input#tyxz-input, input[name="tyxz"]'
    CONFIRM_XPATH = (
        '//button[contains(@class, "bh-btn-primary") and normalize-space()="确定"]'
    )

    def __init__(self, *, dialog_open: bool = True) -> None:
        self.dialog_open = dialog_open
        self.course_btn_visible = False
        self.script_calls: list[str] = []

        batch_payload = json.dumps({"canSelect": "1", "noSelectReason": None})
        self.radio = _FakeElement(attrs={"type": "radio", "data-value": batch_payload})
        self.checkbox = _FakeElement(attrs={"type": "checkbox", "id": "tyxz-input"})

        def _confirm_dialog() -> None:
            self.dialog_open = False
            self.course_btn_visible = True

        self.confirm_button = _FakeElement(on_click=_confirm_dialog)

    def find_element(self, by: str, value: str) -> _FakeElement:
        elements = self.find_elements(by, value)
        if not elements:
            raise NoSuchElementException()
        return elements[0]

    def find_elements(self, by: str, value: str) -> list[_FakeElement]:
        if by == By.CSS_SELECTOR and value == self.RADIO_CSS:
            return [self.radio] if self.dialog_open else []
        if by == By.CSS_SELECTOR and value == self.ACK_CSS:
            return [self.checkbox] if self.dialog_open else []
        if by == By.XPATH and value == self.CONFIRM_XPATH:
            return [self.confirm_button] if self.dialog_open else []
        if by == By.ID and value == "courseBtn":
            return [self.confirm_button] if self.course_btn_visible else []
        return []

    def execute_script(self, script: str, element: _FakeElement) -> None:
        self.script_calls.append(script)
        if "click" in script:
            element.click()


class _CourseReadyDriver:
    def __init__(
        self,
        *,
        has_public_course: bool = False,
        current_batch: str | None = None,
        current_url: str = "https://example.invalid/path?token=abc123",
    ) -> None:
        self._has_public_course = has_public_course
        self._current_batch = current_batch
        self.current_url = current_url

    def find_elements(self, by: str, value: str) -> list[_FakeElement]:
        if by == By.ID and value == "aPublicCourse" and self._has_public_course:
            return [_FakeElement()]
        return []

    def execute_script(self, script: str) -> str | None:
        if script == 'return sessionStorage.getItem("currentBatch");':
            return self._current_batch
        return None


class _MissingCourseBtnDriver:
    def __init__(self) -> None:
        self.find_attempts = 0

    def find_element(self, by: str, value: str) -> _FakeElement:
        if by == By.ID and value == "courseBtn":
            self.find_attempts += 1
            raise NoSuchElementException()
        raise NoSuchElementException()


def _build_service() -> LoginService:
    settings = AppSettings(student_code="20230001", password="secret")
    return LoginService(settings, _DummyBrowser(), _DummySolver())


def test_handle_batch_selection_dialog_selects_ack_and_confirms(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "ynu_xk_spider.domain.services.login.WebDriverWait",
        _ImmediateWait,
    )
    service = _build_service()
    driver = _FakeDriver(dialog_open=True)

    service._handle_batch_selection_dialog(driver)

    assert driver.radio.is_selected()
    assert driver.checkbox.is_selected()
    assert driver.confirm_button.click_count == 1
    assert driver.course_btn_visible is True


def test_handle_batch_selection_dialog_noop_without_dialog(monkeypatch) -> None:
    monkeypatch.setattr(
        "ynu_xk_spider.domain.services.login.WebDriverWait",
        _ImmediateWait,
    )
    service = _build_service()
    driver = _FakeDriver(dialog_open=False)

    service._handle_batch_selection_dialog(driver)

    assert driver.confirm_button.click_count == 0


def test_wait_course_page_ready_rejects_token_only_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "ynu_xk_spider.domain.services.login.WebDriverWait",
        _ImmediateWait,
    )
    service = _build_service()
    driver = _CourseReadyDriver(has_public_course=False, current_batch=None)

    assert service._wait_course_page_ready(driver, timeout=1) is False


def test_wait_course_page_ready_accepts_current_batch_signal(monkeypatch) -> None:
    monkeypatch.setattr(
        "ynu_xk_spider.domain.services.login.WebDriverWait",
        _ImmediateWait,
    )
    service = _build_service()
    driver = _CourseReadyDriver(
        has_public_course=False,
        current_batch='{"code":"2024-2025-2"}',
    )

    assert service._wait_course_page_ready(driver, timeout=1) is True


def test_open_course_selection_page_retries_when_course_button_missing(monkeypatch) -> None:
    service = _build_service()
    driver = _MissingCourseBtnDriver()

    monkeypatch.setattr(
        service,
        "_prepare_for_start_button_click",
        lambda _: None,
    )
    monkeypatch.setattr(service, "_wait_or_stop", lambda _delay: None)

    assert service._open_course_selection_page(driver) is False
    assert driver.find_attempts == service.MAX_START_BUTTON_ATTEMPTS


def test_wait_or_stop_is_interruptible() -> None:
    stop = StopToken()
    settings = AppSettings(student_code="20230001", password="secret")
    service = LoginService(
        settings,
        _DummyBrowser(),
        _DummySolver(),
        stop=stop,
    )

    def _trigger_stop() -> None:
        time.sleep(0.05)
        stop.set()

    stopper = threading.Thread(target=_trigger_stop)
    stopper.start()

    start = time.perf_counter()
    with pytest.raises(StopRequestedError):
        service._wait_or_stop(1.0)
    elapsed = time.perf_counter() - start
    stopper.join()

    assert elapsed < 0.5
