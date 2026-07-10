from __future__ import annotations

from typing import Any

import pytest

from ynu_xk_spider.browser.manager import BrowserManager
from ynu_xk_spider.config import AppSettings


class _FakeDriver:
    def __init__(self) -> None:
        self.cdp_calls: list[tuple[str, dict[str, Any]]] = []

    def execute_cdp_cmd(self, method: str, payload: dict[str, Any]) -> None:
        self.cdp_calls.append((method, payload))

    def quit(self) -> None:
        return None


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
