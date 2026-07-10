"""Application entry point with dependency wiring and signal handling."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from types import FrameType

from .config import AppSettings
from .exceptions import ConfigError, SpiderError
from .logging_config import setup_logging
from .spiders.ynu_spider import YnuCourseSpider

logger = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Explicit argument list; defaults to the process argv.

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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Main application entry point.

    Args:
        argv: Explicit CLI arguments; defaults to the process argv. Pass
            a list (e.g. []) when calling programmatically to avoid
            picking up unrelated process arguments.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    args = parse_args(argv)

    try:
        settings = AppSettings.load(args.config)

        updates = {}
        if args.headless:
            updates["headless"] = True
        if args.log_level:
            updates["log_level"] = args.log_level
        if updates:
            settings = settings.model_copy(update=updates)

    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    setup_logging(settings)

    logger.info("=" * 60)
    logger.info("YNU Auto Course Selector (Refactored v2.0)")
    logger.info("=" * 60)
    logger.info("Student: %s****", settings.student_code[:4] if len(settings.student_code) > 4 else "****")
    logger.info("Headless: %s", settings.headless)

    courses = settings.courses.all_courses
    logger.info("Target courses: %d", len(courses))
    for target in courses:
        logger.info(
            "  [%s] %s - %s",
            target.course_type.label,
            target.item.name,
            target.item.teacher,
        )

    spider = YnuCourseSpider(settings)

    def signal_handler(signum: int, frame: FrameType | None) -> None:
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
