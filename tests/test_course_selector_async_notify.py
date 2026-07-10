from __future__ import annotations

import threading
import time

import pytest

from ynu_xk_spider.config import AppSettings, CourseItem
from ynu_xk_spider.domain.models import (
    CourseInfo,
    CourseType,
    MonitorOutcome,
    SelectionResult,
)
from ynu_xk_spider.domain.services.course_selector import CourseSelector
from ynu_xk_spider.domain.services.notification import AsyncNotifier, ServerChanNotifier
from ynu_xk_spider.exceptions import CourseSelectionError, NetworkError
from ynu_xk_spider.utils.stop import StopToken


class _SlowNotifier:
    enabled = True

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, title: str, content: str) -> None:
        time.sleep(0.2)
        self.messages.append((title, content))


class _FakeApi:
    def __init__(self) -> None:
        self.query_count = 0
        self.slots = [
            CourseInfo(
                teachingClassID="class-1",
                courseName="Linear Algebra",
                teacherName="Prof. Li",
                classCapacity=10,
                numberOfFirstVolunteer=0,
            ),
            CourseInfo(
                teachingClassID="class-2",
                courseName="Linear Algebra",
                teacherName="Prof. Wang",
                classCapacity=10,
                numberOfFirstVolunteer=0,
            ),
        ]

    def query_courses(self, course_name: str, course_type: CourseType) -> list[CourseInfo]:
        self.query_count += 1
        return self.slots

    def find_courses_by_teacher(
        self,
        courses: list[CourseInfo],
        teacher_name: str,
    ) -> list[CourseInfo]:
        return [c for c in courses if teacher_name in c.teacher_name]

    def select_course(self, course: CourseInfo, course_type: CourseType) -> SelectionResult:
        return SelectionResult(
            success=True,
            message="选课成功",
            course_name=course.course_name,
            teacher_name=course.teacher_name,
        )


class _FailingQueryApi(_FakeApi):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def query_courses(self, course_name: str, course_type: CourseType) -> list[CourseInfo]:
        self.query_count += 1
        raise self._exc


class _PartialFailureApi(_FakeApi):
    def __init__(self) -> None:
        super().__init__()
        self.selection_attempts: dict[str, int] = {"Prof. Li": 0, "Prof. Wang": 0}

    def select_course(self, course: CourseInfo, course_type: CourseType) -> SelectionResult:
        self.selection_attempts[course.teacher_name] += 1
        if course.teacher_name == "Prof. Wang" and self.selection_attempts[course.teacher_name] == 1:
            raise NetworkError("temporary selection failure")
        return super().select_course(course, course_type)


def test_notifications_are_async_and_flushed() -> None:
    settings = AppSettings(student_code="20230001", password="secret")
    inner = _SlowNotifier()
    notifier = AsyncNotifier(inner)
    api = _FakeApi()
    selector = CourseSelector(api=api, settings=settings, notifier=notifier)
    course = CourseItem(name="Linear Algebra", teacher="Prof. Li")

    start = time.perf_counter()
    result = selector.run_monitoring_loop(course, CourseType.PUBLIC, stop=StopToken())
    elapsed = time.perf_counter() - start

    assert result is MonitorOutcome.SUCCESS
    assert elapsed < 0.2

    notifier.flush()
    assert len(inner.messages) == 2
    assert api.query_count == 1


def test_async_notifier_is_reusable_after_flush() -> None:
    inner = _SlowNotifier()
    notifier = AsyncNotifier(inner)

    notifier.send("first", "1")
    notifier.flush()
    notifier.send("second", "2")
    notifier.flush()

    assert [title for title, _ in inner.messages] == ["first", "second"]


def test_async_notifier_skips_sending_when_disabled() -> None:
    class _DisabledNotifier:
        enabled = False

        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def send(self, title: str, content: str) -> None:
            self.messages.append((title, content))

    inner = _DisabledNotifier()
    notifier = AsyncNotifier(inner)

    notifier.send("ignored", "x")
    notifier.flush()

    assert inner.messages == []


def test_default_notifier_does_not_create_an_unowned_async_executor() -> None:
    settings = AppSettings(
        student_code="20230001",
        password="secret",
        server_chan_key="configured",
    )
    selector = CourseSelector(api=_FakeApi(), settings=settings)

    assert isinstance(selector._notifier, ServerChanNotifier)


def test_group_monitoring_queries_once_for_multiple_teachers() -> None:
    settings = AppSettings(student_code="20230001", password="secret")
    api = _FakeApi()
    selector = CourseSelector(api=api, settings=settings)

    result = selector.run_group_monitoring_loop(
        course_name="Linear Algebra",
        course_type=CourseType.PUBLIC,
        targets=[
            CourseItem(name="Linear Algebra", teacher="Prof. Li"),
            CourseItem(name="Linear Algebra", teacher="Prof. Wang"),
        ],
        stop=StopToken(),
    )

    assert result is MonitorOutcome.SUCCESS
    assert api.query_count == 1


def test_group_monitoring_with_empty_targets_is_success() -> None:
    settings = AppSettings(student_code="20230001", password="secret")
    api = _FakeApi()
    selector = CourseSelector(api=api, settings=settings)

    result = selector.run_group_monitoring_loop(
        course_name="Linear Algebra",
        course_type=CourseType.PUBLIC,
        targets=[],
        stop=StopToken(),
    )

    assert result is MonitorOutcome.SUCCESS
    assert api.query_count == 0


def test_monitoring_wait_is_interruptible() -> None:
    settings = AppSettings(
        student_code="20230001",
        password="secret",
        poll_interval_min=1.0,
        poll_interval_max=1.0,
    )
    selector = CourseSelector(api=_FakeApi(), settings=settings)
    stop = StopToken()
    course = CourseItem(name="Nonexistent", teacher="Nobody")

    class _NoResultApi(_FakeApi):
        def query_courses(self, course_name: str, course_type: CourseType) -> list[CourseInfo]:
            self.query_count += 1
            return []

    selector = CourseSelector(api=_NoResultApi(), settings=settings)

    def _trigger_stop() -> None:
        time.sleep(0.05)
        stop.set()

    stopper = threading.Thread(target=_trigger_stop)
    stopper.start()

    start = time.perf_counter()
    result = selector.run_monitoring_loop(course, CourseType.PUBLIC, stop=stop)
    elapsed = time.perf_counter() - start
    stopper.join()

    assert result is MonitorOutcome.STOPPED
    assert elapsed < 0.5


@pytest.mark.parametrize(
    "raised_exc",
    [
        NetworkError("network down"),
        CourseSelectionError("selection failed"),
        RuntimeError("unexpected failure"),
    ],
)
def test_monitoring_retries_failures_until_threshold(
    monkeypatch: pytest.MonkeyPatch,
    raised_exc: Exception,
) -> None:
    settings = AppSettings(student_code="20230001", password="secret")
    api = _FailingQueryApi(raised_exc)
    selector = CourseSelector(api=api, settings=settings)
    course = CourseItem(name="Linear Algebra", teacher="Prof. Li")
    wait_delays: list[float] = []

    monkeypatch.setattr(
        selector,
        "_wait_with_stop",
        lambda delay, stop: wait_delays.append(delay) or True,
    )

    result = selector.run_monitoring_loop(course, CourseType.PUBLIC, stop=StopToken())

    assert result is MonitorOutcome.FAILED
    assert api.query_count == 5
    assert wait_delays == [5, 5, 5, 5]


def test_group_monitoring_preserves_successful_targets_across_target_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings(student_code="20230001", password="secret")
    api = _PartialFailureApi()
    selector = CourseSelector(api=api, settings=settings)
    wait_delays: list[float] = []

    monkeypatch.setattr(
        selector,
        "_wait_with_stop",
        lambda delay, stop: wait_delays.append(delay) or True,
    )

    result = selector.run_group_monitoring_loop(
        course_name="Linear Algebra",
        course_type=CourseType.PUBLIC,
        targets=[
            CourseItem(name="Linear Algebra", teacher="Prof. Li"),
            CourseItem(name="Linear Algebra", teacher="Prof. Wang"),
        ],
        stop=StopToken(),
    )

    assert result is MonitorOutcome.SUCCESS
    assert api.query_count == 2
    assert api.selection_attempts == {"Prof. Li": 1, "Prof. Wang": 2}
    assert wait_delays == [5]
