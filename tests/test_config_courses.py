from __future__ import annotations

import pytest
from pydantic import ValidationError

from ynu_xk_spider.config import CoursesConfig


def test_courses_config_accepts_legacy_pair_format() -> None:
    config = CoursesConfig(public=[["Linear Algebra", "Prof. Li"]])
    assert len(config.public) == 1
    assert config.public[0].name == "Linear Algebra"
    assert config.public[0].teacher == "Prof. Li"


def test_courses_config_rejects_invalid_item() -> None:
    with pytest.raises(ValidationError):
        CoursesConfig(public=["invalid"])  # type: ignore[list-item]
