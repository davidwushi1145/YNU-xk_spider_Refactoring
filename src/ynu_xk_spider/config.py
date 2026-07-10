"""Pydantic-based configuration with environment variable override support.

Configuration can be loaded from:
1. Environment variables (prefix: YNU_XK_)
2. .env file
3. JSON config file (config.json)

Environment variables take precedence over file-based configuration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .domain.models import CourseTarget, CourseType


class CourseItem(BaseModel):
    """Single course target configuration."""

    name: str = Field(..., min_length=1, description="Course name to search")
    teacher: str = Field(..., min_length=1, description="Teacher name to match")

    @classmethod
    def from_list(cls, data: list[str]) -> CourseItem:
        """Create from legacy [name, teacher] list format.

        Args:
            data: Two-item list [name, teacher].

        Returns:
            CourseItem instance.

        Raises:
            ValueError: If the list contains fewer than two items.
        """
        if len(data) >= 2:
            return cls(name=data[0], teacher=data[1])
        raise ValueError(f"Invalid course format: {data}")


class CoursesConfig(BaseModel):
    """Course targets grouped by category."""

    public: list[CourseItem] = Field(default_factory=list, description="素选课")
    program: list[CourseItem] = Field(default_factory=list, description="主修课")
    pe: list[CourseItem] = Field(default_factory=list, description="体育课")

    @field_validator("public", "program", "pe", mode="before")
    @classmethod
    def _convert_legacy_format(cls, v: Any) -> list[CourseItem]:
        """Convert legacy config entries to CourseItem list.

        Args:
            v: Items from config; supports dict entries or [name, teacher] pairs.

        Returns:
            Normalized list of CourseItem objects.
        """
        if not v:
            return []
        if not isinstance(v, list):
            raise ValueError("Courses must be a list")

        result: list[CourseItem] = []
        for index, item in enumerate(v):
            if isinstance(item, dict):
                result.append(CourseItem(**item))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                result.append(CourseItem(name=item[0], teacher=item[1]))
            elif isinstance(item, CourseItem):
                result.append(item)
            else:
                raise ValueError(
                    f"Invalid course item at index {index}: "
                    "expected {'name','teacher'} or [name, teacher]"
                )
        return result

    @property
    def all_courses(self) -> list[CourseTarget]:
        """Return all configured targets with their course category.

        Returns:
            List of CourseTarget in public, program, pe order.
        """
        groups: tuple[tuple[CourseType, list[CourseItem]], ...] = (
            (CourseType.PUBLIC, self.public),
            (CourseType.PROGRAM, self.program),
            (CourseType.PE, self.pe),
        )
        return [
            CourseTarget(item=item, course_type=course_type)
            for course_type, items in groups
            for item in items
        ]


class AppSettings(BaseSettings):
    """Application settings with env override and JSON file support.

    Attributes:
        base_url: Base URL of the YNU course selection system.
        student_code: Student ID for authentication.
        password: Account password (stored securely).
        chrome_driver_path: Optional path to chromedriver executable.
        server_chan_key: Optional ServerChan key for WeChat notifications.
        courses: Course selection targets.
        headless: Run browser in headless mode.
        log_level: Logging verbosity level.
        log_file: Path for rotating log file output.
        http_timeout: Default HTTP request timeout in seconds.
        max_retries: Maximum retry attempts for network operations.
        retry_backoff: Initial backoff delay in seconds.
        retry_factor: Exponential backoff multiplier.
        poll_interval_min: Minimum polling interval in seconds.
        poll_interval_max: Maximum polling interval in seconds.
        campus: Campus code (02=呈贡校区, 01=东陆校区).
    """

    model_config = SettingsConfigDict(
        env_prefix="YNU_XK_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Ensure env/.env override file/init settings."""
        return (
            env_settings,
            dotenv_settings,
            init_settings,
            file_secret_settings,
        )

    base_url: str = Field(
        default="https://xk.ynu.edu.cn/",
        description="Base URL of the course selection system",
    )
    student_code: str = Field(..., min_length=1, description="Student ID")
    password: SecretStr = Field(..., description="Account password")
    chrome_driver_path: Path | None = Field(
        default=None, description="Path to chromedriver"
    )
    server_chan_key: str | None = Field(
        default=None, description="ServerChan notification key"
    )
    courses: CoursesConfig = Field(
        default_factory=CoursesConfig, description="Target courses"
    )

    headless: bool = Field(default=False, description="Run browser headless")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    log_file: Path = Field(
        default=Path("logs/spider.log"), description="Log file path"
    )

    http_timeout: float = Field(default=10.0, gt=0, description="HTTP timeout seconds")
    max_retries: int = Field(default=5, ge=1, description="Max retry attempts")
    retry_backoff: float = Field(default=0.5, gt=0, description="Initial backoff")
    retry_factor: float = Field(default=2.0, ge=1, description="Backoff multiplier")

    poll_interval_min: float = Field(default=3.0, gt=0, description="Min poll interval")
    poll_interval_max: float = Field(default=6.0, gt=0, description="Max poll interval")

    campus: str = Field(
        default="02",
        description="Campus code: 02=呈贡校区, 01=东陆校区",
    )

    @field_validator("log_file", mode="before")
    @classmethod
    def _expand_log_file(cls, v: Path | str) -> Path:
        """Expand user home and resolve to absolute path.

        Args:
            v: Input path value.

        Returns:
            Absolute Path with user home expanded.
        """
        return Path(v).expanduser().resolve()

    @field_validator("chrome_driver_path", mode="before")
    @classmethod
    def _normalize_chromedriver(cls, v: Path | str | None) -> Path | None:
        """Normalize chromedriver path value.

        Treats empty strings as None to avoid invalid Service paths.

        Args:
            v: Raw value from config or environment.

        Returns:
            Normalized Path or None.
        """
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return Path(v)

    @model_validator(mode="after")
    def _validate_poll_interval(self) -> AppSettings:
        """Reject configurations where the poll interval bounds are inverted.

        Returns:
            Self when the poll interval bounds are consistent.

        Raises:
            ValueError: If poll_interval_min > poll_interval_max.
        """
        if self.poll_interval_min > self.poll_interval_max:
            raise ValueError(
                "poll_interval_min must be <= poll_interval_max "
                f"(got {self.poll_interval_min} > {self.poll_interval_max})"
            )
        return self

    @classmethod
    def load(cls, config_file: Path | None = None) -> AppSettings:
        """Load settings from JSON file with env override.

        Environment variables take precedence over file-based configuration.

        Args:
            config_file: Optional path to JSON config file.
                        Defaults to config.json in current directory. If the
                        default file is missing, environment variables/.env are
                        used as a fallback.

        Returns:
            Validated AppSettings instance.

        Raises:
            ConfigError: If configuration is invalid or the requested config file
                cannot be used.
        """
        from .exceptions import ConfigError

        if config_file is None:
            config_file = Path("config.json")

        if not config_file.exists():
            if config_file != Path("config.json"):
                raise ConfigError(f"Config file not found: {config_file}")

            try:
                return cls()  # type: ignore[call-arg]
            except ValidationError as e:
                raise ConfigError(
                    "Config file not found: config.json. Provide the file or set "
                    "required YNU_XK_* environment variables."
                ) from e

        try:
            with open(config_file, encoding="utf-8") as f:
                file_data = json.load(f)

            # Map legacy field names
            if "chrome_driver_path" not in file_data and "chromedriver_path" in file_data:
                file_data["chrome_driver_path"] = file_data.pop("chromedriver_path")

            # settings_customise_sources ensures env > dotenv > init (file_data)
            return cls(**file_data)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in config file: {e}") from e
        except Exception as e:
            raise ConfigError(f"Failed to load config: {e}") from e
