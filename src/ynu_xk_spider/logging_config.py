"""Logging configuration with console and rotating file handlers."""

from __future__ import annotations

import logging
from logging.config import dictConfig
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import AppSettings


def setup_logging(settings: AppSettings) -> None:
    """Configure application logging with console and file output.

    Args:
        settings: Application settings providing log level and file path.
    """
    log_dir = settings.log_file.parent
    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": (
                    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
                ),
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": settings.log_level,
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed",
                "level": settings.log_level,
                "filename": str(settings.log_file),
                "maxBytes": 2_000_000,
                "backupCount": 3,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "ynu_xk_spider": {
                "handlers": ["console", "file"],
                "level": settings.log_level,
                "propagate": False,
            },
            "selenium": {
                "level": "WARNING",
                "propagate": True,
            },
            "urllib3": {
                "level": "WARNING",
                "propagate": True,
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": settings.log_level,
        },
    }

    dictConfig(config)
    logging.getLogger("ynu_xk_spider").info(
        "Logging configured: level=%s, file=%s", settings.log_level, settings.log_file
    )
