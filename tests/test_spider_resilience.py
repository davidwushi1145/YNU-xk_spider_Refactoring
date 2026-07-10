from __future__ import annotations

from collections.abc import Generator

import pytest

from ynu_xk_spider.browser.manager import BrowserManager
from ynu_xk_spider.config import AppSettings, CourseItem, CoursesConfig
from ynu_xk_spider.domain.models import CourseType, MonitorOutcome, SessionData
from ynu_xk_spider.exceptions import LoginError, StopRequestedError
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
    monkeypatch.setattr(spider, "_wait_or_stop", lambda _: True)

    spider.run_loop()

    assert attempts["count"] == spider.MAX_CONSECUTIVE_LOGIN_FAILURES
    assert spider.is_stopped()


def test_group_course_targets_merges_same_name_and_type() -> None:
    settings = AppSettings(
        student_code="20230001",
        password="secret",
        courses=CoursesConfig(
            public=[
                CourseItem(name="Linear Algebra", teacher="Prof. Li"),
                CourseItem(name="Linear Algebra", teacher="Prof. Wang"),
            ],
            pe=[CourseItem(name="Swimming", teacher="Coach Lin")],
        ),
    )
    spider = YnuCourseSpider(settings)

    grouped = spider._group_course_targets(settings.courses.all_courses)

    assert grouped == [
        (
            "Linear Algebra",
            CourseType.PUBLIC,
            [
                CourseItem(name="Linear Algebra", teacher="Prof. Li"),
                CourseItem(name="Linear Algebra", teacher="Prof. Wang"),
            ],
        ),
        (
            "Swimming",
            CourseType.PE,
            [CourseItem(name="Swimming", teacher="Coach Lin")],
        ),
    ]


def test_run_monitoring_returns_stopped_for_manual_stop() -> None:
    settings = AppSettings(
        student_code="20230001",
        password="secret",
        courses=CoursesConfig(
            public=[CourseItem(name="Linear Algebra", teacher="Prof. Li")],
        ),
    )
    spider = YnuCourseSpider(settings)
    spider.stop()

    class _StoppedSelector:
        def run_group_monitoring_loop(self, *args: object, **kwargs: object) -> MonitorOutcome:
            return MonitorOutcome.STOPPED

        def wait_for_notifications(self, timeout: float | None = None) -> None:
            return None

    assert spider._run_monitoring(_StoppedSelector()) is MonitorOutcome.STOPPED


def test_perform_login_reuses_solver_and_stop_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    spider = YnuCourseSpider(_build_settings())
    observed_solver_ids: list[int] = []
    observed_stop_values: list[bool] = []

    class _FakeLoginService:
        def __init__(
            self,
            settings: AppSettings,
            browser: BrowserManager,
            solver: object,
            is_stopped: object,
        ) -> None:
            observed_solver_ids.append(id(solver))
            observed_stop_values.append(bool(is_stopped()))

        def login(self) -> SessionData:
            return SessionData(cookies={"SESSION": "abc"}, token="token", batch_code="batch")

    monkeypatch.setattr(
        "ynu_xk_spider.spiders.ynu_spider.LoginService",
        _FakeLoginService,
    )

    spider._perform_login()
    spider.stop()
    spider._perform_login()

    assert observed_solver_ids[0] == observed_solver_ids[1]
    assert observed_stop_values == [False, True]


def test_run_loop_exits_cleanly_on_stop_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    spider = YnuCourseSpider(_build_settings())
    attempts = {"count": 0}

    def _stop_during_login() -> SessionData:
        attempts["count"] += 1
        spider.stop()
        raise StopRequestedError("stop")

    monkeypatch.setattr(spider, "_perform_login", _stop_during_login)

    spider.run_loop()

    assert attempts["count"] == 1
