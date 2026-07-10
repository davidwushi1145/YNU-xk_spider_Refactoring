from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ynu_xk_spider.config import AppSettings, CoursesConfig
from ynu_xk_spider.exceptions import ConfigError


def test_courses_config_accepts_legacy_pair_format() -> None:
    config = CoursesConfig(public=[["Linear Algebra", "Prof. Li"]])
    assert len(config.public) == 1
    assert config.public[0].name == "Linear Algebra"
    assert config.public[0].teacher == "Prof. Li"


def test_courses_config_rejects_invalid_item() -> None:
    with pytest.raises(ValidationError):
        CoursesConfig(public=["invalid"])  # type: ignore[list-item]


def test_app_settings_load_supports_env_without_default_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YNU_XK_STUDENT_CODE", "20230001")
    monkeypatch.setenv("YNU_XK_PASSWORD", "secret")

    settings = AppSettings.load(Path("config.json"))

    assert settings.student_code == "20230001"
    assert settings.password.get_secret_value() == "secret"


def test_app_settings_load_rejects_missing_explicit_config(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    with pytest.raises(ConfigError):
        AppSettings.load(missing)


def test_app_settings_rejects_inverted_poll_interval() -> None:
    with pytest.raises(ValidationError):
        AppSettings(
            student_code="20230001",
            password="secret",
            poll_interval_min=10.0,
            poll_interval_max=5.0,
        )
