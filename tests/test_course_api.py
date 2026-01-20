"""Tests for Course API client."""

from unittest.mock import Mock, MagicMock
import pytest

from ynu_xk_spider.domain.services.course_api import CourseApiClient
from ynu_xk_spider.domain.models import CourseInfo, SelectionResult
from ynu_xk_spider.exceptions import NetworkError


@pytest.fixture
def mock_http():
    """Create mock HTTP client."""
    http = Mock()
    http.token = "test_token"
    return http


@pytest.fixture
def api_client(mock_http):
    """Create API client instance."""
    return CourseApiClient(
        http=mock_http,
        base_url="https://xk.ynu.edu.cn/",
        student_code="20231234567",
        batch_code="2024-1",
        campus="02",
    )


class TestCourseApiClient:
    """Test cases for CourseApiClient."""

    def test_initialization(self, api_client):
        """Test client initializes with correct parameters."""
        assert api_client._student_code == "20231234567"
        assert api_client._batch_code == "2024-1"
        assert api_client._campus == "02"

    def test_query_courses_no_token(self, mock_http):
        """Test query_courses raises error when no token."""
        mock_http.token = None
        client = CourseApiClient(
            http=mock_http,
            base_url="https://xk.ynu.edu.cn/",
            student_code="20231234567",
            batch_code="2024-1",
        )

        with pytest.raises(NetworkError, match="No auth token"):
            client.query_courses("Math", "素选")

    def test_query_courses_success(self, api_client, mock_http):
        """Test successful course query."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "dataList": [
                {
                    "teachingClassID": "cls001",
                    "courseName": "高等数学",
                    "teacherName": "张三",
                    "classCapacity": 100,
                    "numberOfFirstVolunteer": 50,
                }
            ]
        }
        mock_http.post.return_value = mock_response

        courses = api_client.query_courses("高等数学", "素选")

        assert len(courses) == 1
        assert courses[0].course_name == "高等数学"
        assert courses[0].teacher_name == "张三"

    def test_query_courses_empty(self, api_client, mock_http):
        """Test query returns empty list when no courses found."""
        mock_response = Mock()
        mock_response.json.return_value = {"dataList": []}
        mock_http.post.return_value = mock_response

        courses = api_client.query_courses("不存在的课程", "素选")
        assert courses == []

    def test_find_course_by_teacher(self, api_client):
        """Test finding course by teacher name."""
        courses = [
            CourseInfo(
                teachingClassID="c1",
                courseName="Math",
                teacherName="张三",
                classCapacity=100,
                numberOfFirstVolunteer=50,
            ),
            CourseInfo(
                teachingClassID="c2",
                courseName="Math",
                teacherName="李四",
                classCapacity=100,
                numberOfFirstVolunteer=80,
            ),
        ]

        result = api_client.find_course_by_teacher(courses, "张三")
        assert result is not None
        assert result.teacher_name == "张三"

    def test_find_course_by_teacher_not_found(self, api_client):
        """Test returns None when teacher not found."""
        courses = [
            CourseInfo(
                teachingClassID="c1",
                courseName="Math",
                teacherName="张三",
                classCapacity=100,
                numberOfFirstVolunteer=50,
            ),
        ]

        result = api_client.find_course_by_teacher(courses, "王五")
        assert result is None

    def test_find_courses_by_teacher(self, api_client):
        """Test finding all courses by teacher name."""
        courses = [
            CourseInfo(
                teachingClassID="c1",
                courseName="Math",
                teacherName="张三",
                classCapacity=100,
                numberOfFirstVolunteer=50,
            ),
            CourseInfo(
                teachingClassID="c2",
                courseName="Math",
                teacherName="张三",
                classCapacity=50,
                numberOfFirstVolunteer=30,
            ),
            CourseInfo(
                teachingClassID="c3",
                courseName="Math",
                teacherName="李四",
                classCapacity=100,
                numberOfFirstVolunteer=80,
            ),
        ]

        result = api_client.find_courses_by_teacher(courses, "张三")
        assert len(result) == 2

    def test_select_course_no_token(self, api_client, mock_http):
        """Test select_course returns error when no token."""
        mock_http.token = None
        course = CourseInfo(
            teachingClassID="c1",
            courseName="Math",
            teacherName="张三",
            classCapacity=100,
            numberOfFirstVolunteer=50,
        )

        result = api_client.select_course(course, "素选")

        assert result.success is False
        assert "No auth token" in result.message

    def test_select_course_success(self, api_client, mock_http):
        """Test successful course selection."""
        mock_response = Mock()
        mock_response.json.return_value = {"msg": "选课成功"}
        mock_http.post.return_value = mock_response

        course = CourseInfo(
            teachingClassID="c1",
            courseName="高等数学",
            teacherName="张三",
            classCapacity=100,
            numberOfFirstVolunteer=50,
        )

        result = api_client.select_course(course, "素选")

        assert result.success is True
        assert "成功" in result.message

    def test_select_course_failure(self, api_client, mock_http):
        """Test failed course selection."""
        mock_response = Mock()
        mock_response.json.return_value = {"msg": "课程人数已满"}
        mock_http.post.return_value = mock_response

        course = CourseInfo(
            teachingClassID="c1",
            courseName="高等数学",
            teacherName="张三",
            classCapacity=100,
            numberOfFirstVolunteer=100,
        )

        result = api_client.select_course(course, "素选")

        assert result.success is False


class TestCourseInfo:
    """Test CourseInfo model."""

    def test_remaining_spots(self):
        """Test remaining spots calculation."""
        course = CourseInfo(
            teachingClassID="c1",
            courseName="Math",
            teacherName="Teacher",
            classCapacity=100,
            numberOfFirstVolunteer=75,
        )
        assert course.remaining == 25

    def test_has_spots_true(self):
        """Test has_spots returns True when spots available."""
        course = CourseInfo(
            teachingClassID="c1",
            courseName="Math",
            teacherName="Teacher",
            classCapacity=100,
            numberOfFirstVolunteer=75,
        )
        assert course.has_spots is True

    def test_has_spots_false(self):
        """Test has_spots returns False when full."""
        course = CourseInfo(
            teachingClassID="c1",
            courseName="Math",
            teacherName="Teacher",
            classCapacity=100,
            numberOfFirstVolunteer=100,
        )
        assert course.has_spots is False

    def test_remaining_not_negative(self):
        """Test remaining is never negative."""
        course = CourseInfo(
            teachingClassID="c1",
            courseName="Math",
            teacherName="Teacher",
            classCapacity=100,
            numberOfFirstVolunteer=150,  # Over capacity
        )
        assert course.remaining == 0
