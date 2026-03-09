from __future__ import annotations

import threading
import time

from ynu_xk_spider.config import AppSettings, CourseItem
from ynu_xk_spider.domain.models import CourseInfo, MonitorOutcome, SelectionResult
from ynu_xk_spider.domain.services.course_selector import CourseSelector


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

    def query_courses(self, course_name: str, course_type: str) -> list[CourseInfo]:
        self.query_count += 1
        return self.slots

    def find_courses_by_teacher(
        self,
        courses: list[CourseInfo],
        teacher_name: str,
    ) -> list[CourseInfo]:
        return [c for c in courses if teacher_name in c.teacher_name]

    def select_course(self, course: CourseInfo, course_type: str) -> SelectionResult:
        return SelectionResult(
            success=True,
            message="选课成功",
            course_name=course.course_name,
            teacher_name=course.teacher_name,
        )


def test_notifications_are_async_and_flushed_on_wait() -> None:
    settings = AppSettings(student_code="20230001", password="secret")
    notifier = _SlowNotifier()
    api = _FakeApi()
    selector = CourseSelector(api=api, settings=settings, notifier=notifier)
    course = CourseItem(name="Linear Algebra", teacher="Prof. Li")

    start = time.perf_counter()
    result = selector.run_monitoring_loop(course, "素选", is_stopped=lambda: False)
    elapsed = time.perf_counter() - start

    assert result is MonitorOutcome.SUCCESS
    assert elapsed < 0.2

    selector.wait_for_notifications()
    assert len(notifier.messages) == 2
    assert api.query_count == 1


def test_group_monitoring_queries_once_for_multiple_teachers() -> None:
    settings = AppSettings(student_code="20230001", password="secret")
    api = _FakeApi()
    selector = CourseSelector(api=api, settings=settings)

    result = selector.run_group_monitoring_loop(
        course_name="Linear Algebra",
        course_type="素选",
        targets=[
            CourseItem(name="Linear Algebra", teacher="Prof. Li"),
            CourseItem(name="Linear Algebra", teacher="Prof. Wang"),
        ],
        is_stopped=lambda: False,
    )

    assert result is MonitorOutcome.SUCCESS
    assert api.query_count == 1


def test_monitoring_wait_is_interruptible() -> None:
    settings = AppSettings(
        student_code="20230001",
        password="secret",
        poll_interval_min=1.0,
        poll_interval_max=1.0,
    )
    selector = CourseSelector(api=_FakeApi(), settings=settings)
    stop_event = threading.Event()
    course = CourseItem(name="Nonexistent", teacher="Nobody")

    class _NoResultApi(_FakeApi):
        def query_courses(self, course_name: str, course_type: str) -> list[CourseInfo]:
            self.query_count += 1
            return []

    selector = CourseSelector(api=_NoResultApi(), settings=settings)

    def _trigger_stop() -> None:
        time.sleep(0.05)
        stop_event.set()

    stopper = threading.Thread(target=_trigger_stop)
    stopper.start()

    start = time.perf_counter()
    result = selector.run_monitoring_loop(course, "素选", is_stopped=stop_event.is_set)
    elapsed = time.perf_counter() - start
    stopper.join()

    assert result is MonitorOutcome.STOPPED
    assert elapsed < 0.5
