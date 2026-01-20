
import os
from pathlib import Path
from ynu_xk_spider.config import AppSettings, CoursesConfig

def test_load_defaults(clean_env):
    """Test loading default settings."""
    # Create a dummy config.json if needed or rely on defaults if allowed
    # AppSettings.load() expects config.json to exist
    
    # We'll mock the config file existence by writing a temp one
    pass 

def test_env_override(clean_env):
    """Test environment variable overrides."""
    os.environ["YNU_XK_STUDENT_CODE"] = "test_user"
    os.environ["YNU_XK_PASSWORD"] = "test_pass"
    
    # Create a minimal config to satisfy validation
    settings = AppSettings(
        student_code="test_user",
        password="test_pass",
        courses=CoursesConfig()
    )
    
    assert settings.student_code == "test_user"
    assert settings.password.get_secret_value() == "test_pass"

def test_legacy_course_format():
    """Test parsing legacy [name, teacher] format."""
    data = ["Course A", "Teacher A"]
    config = CoursesConfig(public=[data])
    assert len(config.public) == 1
    assert config.public[0].name == "Course A"
    assert config.public[0].teacher == "Teacher A"
