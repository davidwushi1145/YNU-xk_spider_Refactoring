"""Course API client for querying and selecting courses."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...exceptions import NetworkError, SessionExpiredError
from ...http.endpoints import Endpoints
from ..models import (
    CourseInfo,
    CourseType,
    QueryRequest,
    SelectionRequest,
    SelectionResult,
)

if TYPE_CHECKING:
    from ...http.client import HttpClient

logger = logging.getLogger(__name__)


class CourseApiClient:
    """API client for course query and selection operations.

    Provides typed methods for interacting with the YNU course selection API.

    Attributes:
        _http: HTTP client for requests.
        _endpoints: URL endpoint builder.
        _student_code: Student ID.
        _batch_code: Current batch code.
        _campus: Campus code.
    """

    def __init__(
        self,
        http: HttpClient,
        base_url: str,
        student_code: str,
        batch_code: str,
        campus: str = "02",
    ) -> None:
        """Initialize API client.

        Args:
            http: HTTP client instance.
            base_url: Base URL of the system.
            student_code: Student ID.
            batch_code: Course selection batch code.
            campus: Campus code (02=呈贡, 01=东陆).
        """
        self._http = http
        self._endpoints = Endpoints(base_url)
        self._student_code = student_code
        self._batch_code = batch_code
        self._campus = campus

    def query_courses(
        self,
        course_name: str,
        course_type: CourseType,
    ) -> list[CourseInfo]:
        """Query available courses by name.

        Args:
            course_name: Course name to search.
            course_type: Course category to query.

        Returns:
            List of matching course information.

        Raises:
            NetworkError: On request failure.
        """
        token = self._http.token
        if not token:
            raise NetworkError("No auth token available")

        url = (
            self._endpoints.public_course(token)
            if course_type is CourseType.PUBLIC
            else self._endpoints.program_course(token)
        )

        request = QueryRequest(
            student_code=self._student_code,
            batch_code=self._batch_code,
            class_type=course_type.class_type_code,
            query_content=course_name,
            campus=self._campus,
        )

        resp = self._http.post(url, data=request.to_api_payload())

        try:
            data = resp.json()
        except Exception as exc:
            raise NetworkError(f"Invalid JSON response: {exc}") from exc

        return self._parse_course_list(data, course_type)

    def _parse_course_list(
        self,
        data: dict[str, Any],
        course_type: CourseType,
    ) -> list[CourseInfo]:
        """Parse course list from API response.

        Args:
            data: API response data.
            course_type: Course category (drives the response shape).

        Returns:
            Parsed course information list.
        """
        courses: list[CourseInfo] = []
        data_list = data.get("dataList", [])

        if not data_list:
            return courses

        if course_type.nested_response:
            for category in data_list:
                tc_list = category.get("tcList", [])
                for item in tc_list:
                    try:
                        courses.append(CourseInfo(**item))
                    except Exception as exc:
                        logger.debug("Failed to parse course: %s", exc)
        else:
            for item in data_list:
                try:
                    courses.append(CourseInfo(**item))
                except Exception as exc:
                    logger.debug("Failed to parse course: %s", exc)

        return courses

    def find_courses_by_teacher(
        self,
        courses: list[CourseInfo],
        teacher_name: str,
    ) -> list[CourseInfo]:
        """Find all courses by teacher name (multiple time slots).

        Args:
            courses: List of courses to search.
            teacher_name: Teacher name to match.

        Returns:
            List of all matching courses.
        """
        return [course for course in courses if teacher_name in course.teacher_name]

    def select_course(
        self,
        course: CourseInfo,
        course_type: CourseType,
    ) -> SelectionResult:
        """Attempt to select a course.

        Args:
            course: Target course information.
            course_type: Course category of the target.

        Returns:
            Selection result with success status and message.
        """
        token = self._http.token
        if not token:
            return SelectionResult(
                success=False,
                message="No auth token",
                course_name=course.course_name,
                teacher_name=course.teacher_name,
            )

        url = self._endpoints.volunteer(token)

        request = SelectionRequest(
            student_code=self._student_code,
            batch_code=self._batch_code,
            teaching_class_id=course.teaching_class_id,
            class_type=course_type.class_type_code,
            campus=self._campus,
        )

        try:
            resp = self._http.post(url, data=request.to_api_payload())
            data = resp.json()
            message = data.get("msg", "Unknown result")

            success = "成功" in message

            logger.info(
                "Selection [%s - %s]: %s",
                course.course_name,
                course.teacher_name,
                message,
            )

            return SelectionResult(
                success=success,
                message=message,
                course_name=course.course_name,
                teacher_name=course.teacher_name,
            )

        except SessionExpiredError:
            raise
        except NetworkError:
            raise
        except Exception as exc:
            logger.error("Selection failed: %s", exc)
            return SelectionResult(
                success=False,
                message=str(exc),
                course_name=course.course_name,
                teacher_name=course.teacher_name,
            )
