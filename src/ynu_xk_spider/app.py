"""Application entry point with dependency wiring and signal handling."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from types import FrameType
from typing import Optional

from .config import AppSettings
from .exceptions import ConfigError, SpiderError
from .logging_config import setup_logging
from .spiders.ynu_spider import YnuCourseSpider


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="YNU Course Selection Spider",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to configuration file",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Override log level",
    )
    return parser.parse_args()


def main(config_path: Optional[Path] = None) -> int:
    """Main application entry point.

    Args:
        config_path: Optional config file path override.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    args = parse_args()

    if config_path is None:
        config_path = args.config

    try:
        settings = AppSettings.load(config_path)

        if args.headless:
            settings.headless = True
        if args.log_level:
            settings.log_level = args.log_level

    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    setup_logging(settings)

    import logging

    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("YNU Auto Course Selector (Refactored v2.0)")
    logger.info("=" * 60)
    logger.info("Student: %s****", settings.student_code[:4] if len(settings.student_code) > 4 else "****")
    logger.info("Headless: %s", settings.headless)

    courses = settings.courses.all_courses
    logger.info("Target courses: %d", len(courses))
    for course, ctype in courses:
        logger.info("  [%s] %s - %s", ctype, course.name, course.teacher)

    spider = YnuCourseSpider(settings)

    def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
        logger.info("Received signal %d, stopping...", signum)
        spider.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        spider.start()
        return 0
    except SpiderError as exc:
        logger.error("Spider error: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted")
        return 0
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        return 1


def run() -> None:
    """Console script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    run()
