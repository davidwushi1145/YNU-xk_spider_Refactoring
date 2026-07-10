from __future__ import annotations

import pytest
from pydantic import ValidationError

from ynu_xk_spider.config import CourseItem, CoursesConfig
from ynu_xk_spider.domain.models import (
    CourseTarget,
    CourseType,
    QueryRequest,
    SelectionRequest,
)
from ynu_xk_spider.domain.services.course_api import CourseApiClient


def test_course_type_carries_api_mapping() -> None:
    assert CourseType.PUBLIC.class_type_code == "XGXK"
    assert CourseType.PROGRAM.class_type_code == "FANKC"
    assert CourseType.PE.class_type_code == "TYKC"
    assert CourseType.PUBLIC.nested_response is False
    assert CourseType.PROGRAM.nested_response is True
    assert CourseType.PE.nested_response is True
    assert str(CourseType.PUBLIC) == "素选"
    assert [course_type.label for course_type in CourseType] == ["素选", "主修", "体育"]


def test_all_courses_returns_targets_in_category_order() -> None:
    config = CoursesConfig(
        public=[CourseItem(name="A", teacher="T1")],
        program=[CourseItem(name="B", teacher="T2")],
        pe=[CourseItem(name="C", teacher="T3")],
    )

    targets = config.all_courses

    assert targets == [
        CourseTarget(CourseItem(name="A", teacher="T1"), CourseType.PUBLIC),
        CourseTarget(CourseItem(name="B", teacher="T2"), CourseType.PROGRAM),
        CourseTarget(CourseItem(name="C", teacher="T3"), CourseType.PE),
    ]
    assert targets[0].item.name == "A"
    assert targets[0].course_type is CourseType.PUBLIC


def _api() -> CourseApiClient:
    return CourseApiClient(
        http=None,  # type: ignore[arg-type]
        base_url="https://xk.example.invalid/",
        student_code="20230001",
        batch_code="batch-1",
        campus="02",
    )


def test_parse_course_list_flat_for_public() -> None:
    data = {"dataList": [{"teachingClassID": "c1", "classCapacity": 10}]}

    courses = _api()._parse_course_list(data, CourseType.PUBLIC)

    assert [course.teaching_class_id for course in courses] == ["c1"]


@pytest.mark.parametrize("course_type", [CourseType.PROGRAM, CourseType.PE])
def test_parse_course_list_nested_for_program_and_pe(course_type: CourseType) -> None:
    data = {"dataList": [{"tcList": [{"teachingClassID": "c2"}]}]}

    courses = _api()._parse_course_list(data, course_type)

    assert [course.teaching_class_id for course in courses] == ["c2"]


def test_request_models_require_explicit_campus() -> None:
    with pytest.raises(ValidationError):
        SelectionRequest(  # type: ignore[call-arg]
            student_code="s",
            batch_code="b",
            teaching_class_id="t",
            class_type="XGXK",
        )
    with pytest.raises(ValidationError):
        QueryRequest(  # type: ignore[call-arg]
            student_code="s",
            batch_code="b",
            class_type="XGXK",
            query_content="q",
        )
