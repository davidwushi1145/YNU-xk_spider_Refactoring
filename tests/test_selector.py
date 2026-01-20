
from unittest.mock import Mock, MagicMock
import pytest
from ynu_xk_spider.domain.services.course_selector import CourseSelector
from ynu_xk_spider.domain.models import CourseInfo, SelectionResult

@pytest.fixture
def mock_api():
    return Mock()

@pytest.fixture
def mock_settings():
    settings = Mock()
    settings.poll_interval_min = 0.01  # Fast poll for tests
    settings.poll_interval_max = 0.02
    settings.server_chan_key = None
    return settings

def test_monitoring_loop_finds_spot(mock_api, mock_settings):
    """Test that selector finds a spot and selects it."""
    # Setup
    selector = CourseSelector(mock_api, mock_settings)
    course = Mock(name="TestCourse")
    course.name = "Math" 
    course.teacher = "Li"
    
    # Mock API responses
    # 1. Query finds courses
    found_courses = [CourseInfo(
        teachingClassID="123",
        courseName="Math",
        teacherName="Li", 
        classCapacity=100,
        numberOfFirstVolunteer=99 # 1 spot left
    )]
    mock_api.query_courses.return_value = found_courses
    mock_api.find_courses_by_teacher.return_value = found_courses
    
    # 2. Selection succeeds
    mock_api.select_course.return_value = SelectionResult(
        success=True, message="Success"
    )

    # Run
    # We use a side_effect to stop the loop after first iteration if needed,
    # but the selector logic returns True immediately upon success.
    result = selector.run_monitoring_loop(course, "素选", lambda: False)

    assert result is True
    mock_api.select_course.assert_called_once()
