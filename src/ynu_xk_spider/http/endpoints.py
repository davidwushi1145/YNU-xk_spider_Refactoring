"""URL endpoint builders for YNU course selection API."""

from __future__ import annotations

import time


class Endpoints:
    """URL builder for YNU course selection system APIs."""

    def __init__(self, base_url: str) -> None:
        """Initialize with base URL.

        Args:
            base_url: Base URL of the course selection system.
        """
        self._base = base_url.rstrip("/")

    @property
    def base(self) -> str:
        """Base URL.

        Returns:
            Base URL string.
        """
        return self._base

    def public_course(self, token: str) -> str:
        """Build URL for public course query.

        Args:
            token: Authentication token.

        Returns:
            Fully qualified API URL.
        """
        return f"{self._base}/xsxkapp/sys/xsxkapp/elective/publicCourse.do?token={token}"

    def program_course(self, token: str) -> str:
        """Build URL for program/PE course query.

        Args:
            token: Authentication token.

        Returns:
            Fully qualified API URL.
        """
        return f"{self._base}/xsxkapp/sys/xsxkapp/elective/programCourse.do?token={token}"

    def volunteer(self, token: str) -> str:
        """Build URL for course selection submission.

        Args:
            token: Authentication token.

        Returns:
            Fully qualified API URL.
        """
        return f"{self._base}/xsxkapp/sys/xsxkapp/elective/volunteer.do?token={token}"

    def course_result(self, student_code: str, batch_code: str) -> str:
        """Build URL for querying selected courses.

        Args:
            student_code: Student ID.
            batch_code: Course selection batch code.

        Returns:
            Fully qualified API URL.
        """

        timestamp = int(time.time() * 1000)
        return f"{self._base}/xsxkapp/sys/xsxkapp/elective/courseResult.do?timestamp={timestamp}&studentCode={student_code}&electiveBatchCode={batch_code}"
