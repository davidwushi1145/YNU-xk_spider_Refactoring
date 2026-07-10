from __future__ import annotations

import gc
import weakref
from typing import Any

import pytest

from ynu_xk_spider.browser.manager import BrowserManager
from ynu_xk_spider.config import AppSettings


class _FakeDriver:
    def __init__(self) -> None:
        self.cdp_calls: list[tuple[str, dict[str, Any]]] = []
        self.quit_calls = 0

    def execute_cdp_cmd(self, method: str, payload: dict[str, Any]) -> None:
        self.cdp_calls.append((method, payload))

    def quit(self) -> None:
        self.quit_calls += 1


def test_chrome_password_prompt_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_driver = _FakeDriver()

    def _fake_chrome(*_: Any, **kwargs: Any) -> _FakeDriver:
        captured["options"] = kwargs["options"]
        return fake_driver

    monkeypatch.setattr(
        "ynu_xk_spider.browser.manager.webdriver.Chrome",
        _fake_chrome,
    )

    settings = AppSettings(student_code="20230001", password="secret")
    manager = BrowserManager(settings)

    driver = manager.get_driver()
    assert driver is fake_driver

    options = captured["options"]
    prefs = options.experimental_options.get("prefs", {})
    assert prefs.get("credentials_enable_service") is False
    assert prefs.get("profile.password_manager_enabled") is False
    assert prefs.get("profile.password_manager_leak_detection") is False

    disable_features_args = [
        arg for arg in options.arguments if arg.startswith("--disable-features=")
    ]
    assert any("PasswordManagerEnabled" in arg for arg in disable_features_args)

    assert fake_driver.cdp_calls
    assert fake_driver.cdp_calls[0][0] == "Page.addScriptToEvaluateOnNewDocument"

    manager_ref = weakref.ref(manager)
    manager.shutdown()
    assert fake_driver.quit_calls == 1

    del manager
    gc.collect()

    assert manager_ref() is None


def test_atexit_hook_follows_each_live_driver_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_callbacks: list[Any] = []
    drivers = [_FakeDriver(), _FakeDriver()]
    driver_iter = iter(drivers)

    def _register(callback: Any) -> Any:
        active_callbacks.append(callback)
        return callback

    def _unregister(callback: Any) -> None:
        active_callbacks.remove(callback)

    monkeypatch.setattr("ynu_xk_spider.browser.manager.atexit.register", _register)
    monkeypatch.setattr("ynu_xk_spider.browser.manager.atexit.unregister", _unregister)
    monkeypatch.setattr(
        "ynu_xk_spider.browser.manager.webdriver.Chrome",
        lambda *args, **kwargs: next(driver_iter),
    )

    settings = AppSettings(student_code="20230001", password="secret")
    manager = BrowserManager(settings)

    assert active_callbacks == []

    assert manager.get_driver() is drivers[0]
    assert len(active_callbacks) == 1

    manager.shutdown()
    assert drivers[0].quit_calls == 1
    assert active_callbacks == []

    assert manager.get_driver() is drivers[1]
    assert len(active_callbacks) == 1

    manager.shutdown()
    assert drivers[1].quit_calls == 1
    assert active_callbacks == []
