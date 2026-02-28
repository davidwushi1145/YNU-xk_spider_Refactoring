from __future__ import annotations

from collections.abc import Generator

import pytest

from ynu_xk_spider.browser.manager import BrowserManager
from ynu_xk_spider.config import AppSettings
from ynu_xk_spider.exceptions import LoginError
from ynu_xk_spider.spiders.ynu_spider import YnuCourseSpider


@pytest.fixture(autouse=True)
def _reset_browser_manager() -> Generator[None, None, None]:
    BrowserManager.reset()
    yield
    BrowserManager.reset()


def _build_settings() -> AppSettings:
    return AppSettings(student_code="20230001", password="secret")


def test_worker_count_respects_limit() -> None:
    spider = YnuCourseSpider(_build_settings(), max_workers=1)
    assert spider._resolve_worker_count(3) == 1


def test_run_loop_stops_after_repeated_login_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spider = YnuCourseSpider(_build_settings())
    attempts = {"count": 0}

    def _always_fail_login() -> None:
        attempts["count"] += 1
        raise LoginError("bad credentials")

    monkeypatch.setattr(spider, "_perform_login", _always_fail_login)
    monkeypatch.setattr("ynu_xk_spider.spiders.ynu_spider.time.sleep", lambda _: None)

    spider.run_loop()

    assert attempts["count"] == spider.MAX_CONSECUTIVE_LOGIN_FAILURES
    assert spider.is_stopped()
