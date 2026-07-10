"""Domain models for course selection system."""

from __future__ import annotations

import json
from enum import Enum
from typing import TYPE_CHECKING, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from ..config import CourseItem


class SessionData(BaseModel):
    """Authenticated session data from login.

    Attributes:
        cookies: Browser cookies dictionary.
        token: Authentication token.
        batch_code: Current course selection batch code.
    """

    cookies: dict[str, str]
    token: str
    batch_code: str


class MonitorOutcome(Enum):
    """Outcome of a monitoring loop or monitoring batch."""

    SUCCESS = "success"
    STOPPED = "stopped"
    SESSION_EXPIRED = "session_expired"
    FAILED = "failed"


class CourseType(Enum):
    """Course category with its API mapping attributes.

    Single source of truth for how each category maps onto the selection
    system API: display label, teachingClassType code, and response shape.

    Attributes:
        label: Human-readable category name used in logs.
        class_type_code: teachingClassType value expected by the API.
        nested_response: Whether the query response nests classes in tcList.
    """

    PUBLIC = ("素选", "XGXK", False)
    PROGRAM = ("主修", "FANKC", True)
    PE = ("体育", "TYKC", True)

    def __init__(
        self,
        label: str,
        class_type_code: str,
        nested_response: bool,
    ) -> None:
        self.label = label
        self.class_type_code = class_type_code
        self.nested_response = nested_response

    def __str__(self) -> str:
        return self.label


class CourseTarget(NamedTuple):
    """A configured course target paired with its category.

    Attributes:
        item: Course name/teacher pair from configuration.
        course_type: Category the course belongs to.
    """

    item: CourseItem
    course_type: CourseType


class CourseInfo(BaseModel):
    """Course information from API response.

    Attributes:
        teaching_class_id: Unique class identifier.
        course_name: Course name.
        teacher_name: Teacher name(s).
        capacity: Total class capacity.
        selected_count: Number of first-choice selections.
        remaining: Available spots.
    """

    teaching_class_id: str = Field(alias="teachingClassID")
    course_name: str = Field(alias="courseName", default="")
    teacher_name: str = Field(alias="teacherName", default="")
    capacity: int = Field(alias="classCapacity", default=0)
    selected_count: int = Field(alias="numberOfFirstVolunteer", default=0)

    model_config = ConfigDict(populate_by_name=True)

    @property
    def remaining(self) -> int:
        """Calculate remaining spots."""
        return max(0, self.capacity - self.selected_count)

    @property
    def has_spots(self) -> bool:
        """Check if course has available spots."""
        return self.remaining > 0


class SelectionRequest(BaseModel):
    """Course selection request parameters.

    Attributes:
        student_code: Student ID.
        batch_code: Course selection batch code.
        teaching_class_id: Target class ID.
        class_type: Teaching class type code.
        campus: Campus code.
    """

    student_code: str
    batch_code: str
    teaching_class_id: str
    class_type: str
    campus: str

    def to_api_payload(self) -> dict[str, str]:
        """Convert to API request payload format.

        Returns:
            Dictionary with 'addParam' key containing serialized request data.
        """
        return {
            "addParam": json.dumps(
                {
                    "data": {
                        "operationType": "1",
                        "studentCode": self.student_code,
                        "electiveBatchCode": self.batch_code,
                        "teachingClassId": self.teaching_class_id,
                        "isMajor": "1",
                        "campus": self.campus,
                        "teachingClassType": self.class_type,
                    }
                },
                ensure_ascii=False,
            )
        }


class QueryRequest(BaseModel):
    """Course query request parameters.

    Attributes:
        student_code: Student ID.
        batch_code: Course selection batch code.
        class_type: Teaching class type code.
        query_content: Course name to search.
        campus: Campus code.
    """

    student_code: str
    batch_code: str
    class_type: str
    query_content: str
    campus: str

    def to_api_payload(self) -> dict[str, str]:
        """Convert to API request payload format.

        Returns:
            Dictionary with 'querySetting' key containing serialized query data.
        """
        return {
            "querySetting": json.dumps(
                {
                    "data": {
                        "studentCode": self.student_code,
                        "campus": self.campus,
                        "electiveBatchCode": self.batch_code,
                        "isMajor": "1",
                        "teachingClassType": self.class_type,
                        "checkConflict": "2",
                        "checkCapacity": "2",
                        "queryContent": self.query_content,
                    },
                    "pageSize": "10",
                    "pageNumber": "0",
                    "order": "",
                },
                ensure_ascii=False,
            )
        }


class SelectionResult(BaseModel):
    """Course selection result.

    Attributes:
        success: Whether selection succeeded.
        message: Result message from server.
        course_name: Target course name.
        teacher_name: Target teacher name.
    """

    success: bool
    message: str
    course_name: str = ""
    teacher_name: str = ""
