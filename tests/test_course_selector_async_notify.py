from __future__ import annotations

import time

from ynu_xk_spider.config import AppSettings, CourseItem
from ynu_xk_spider.domain.models import CourseInfo, SelectionResult
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
        self.slot = CourseInfo(
            teachingClassID="class-1",
            courseName="Linear Algebra",
            teacherName="Prof. Li",
            classCapacity=10,
            numberOfFirstVolunteer=0,
        )

    def query_courses(self, course_name: str, course_type: str) -> list[CourseInfo]:
        return [self.slot]

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


def test_notifications_are_async_and_do_not_block_selection() -> None:
    settings = AppSettings(student_code="20230001", password="secret")
    notifier = _SlowNotifier()
    selector = CourseSelector(api=_FakeApi(), settings=settings, notifier=notifier)
    course = CourseItem(name="Linear Algebra", teacher="Prof. Li")

    start = time.perf_counter()
    result = selector.run_monitoring_loop(course, "素选", is_stopped=lambda: False)
    elapsed = time.perf_counter() - start

    assert result is True
    assert elapsed < 0.2

    time.sleep(0.35)
    assert len(notifier.messages) >= 1
