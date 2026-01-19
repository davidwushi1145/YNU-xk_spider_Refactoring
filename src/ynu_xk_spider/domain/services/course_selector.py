"""Course selector with monitoring and selection logic."""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Callable, Optional

import requests

from ...exceptions import CourseSelectionError, NetworkError, SessionExpiredError

if TYPE_CHECKING:
    from ...config import AppSettings, CourseItem
    from .course_api import CourseApiClient

logger = logging.getLogger(__name__)


class NotificationService:
    """Simple notification service via ServerChan."""

    def __init__(self, server_key: Optional[str] = None) -> None:
        """Initialize notification service.

        Args:
            server_key: ServerChan API key.
        """
        self._server_key = server_key

    def send(self, title: str, content: str) -> None:
        """Send notification via WeChat.

        Args:
            title: Notification title.
            content: Notification body.
        """
        if not self._server_key:
            return

        try:
            url = f"https://sctapi.ftqq.com/{self._server_key}.send"
            requests.post(url, data={"text": title, "desp": content}, timeout=5)
            logger.debug("Notification sent: %s", title)
        except Exception as exc:
            logger.warning("Notification failed: %s", exc)


class CourseSelector:
    """Business logic for course monitoring and selection.

    Implements the main selection loop with:
    - Periodic course availability checking
    - Automatic selection when spots available
    - Session expiration detection
    - Configurable polling intervals

    Attributes:
        _api: Course API client.
        _settings: Application settings.
        _notifier: Notification service.
    """

    def __init__(
        self,
        api: CourseApiClient,
        settings: AppSettings,
        notifier: Optional[NotificationService] = None,
    ) -> None:
        """Initialize course selector.

        Args:
            api: Course API client.
            settings: Application settings.
            notifier: Optional notification service.
        """
        self._api = api
        self._settings = settings
        self._notifier = notifier or NotificationService(settings.server_chan_key)

    def run_monitoring_loop(
        self,
        course: CourseItem,
        course_type: str,
        is_stopped: Callable[[], bool],
    ) -> bool:
        """Monitor a single course and attempt selection when available.

        Args:
            course: Target course configuration.
            course_type: One of "素选", "主修", "体育".
            is_stopped: Callable returning True when stop requested.

        Returns:
            True if selection succeeded, False if session expired or stopped.
        """
        logger.info("Starting monitor: [%s] - %s", course.name, course.teacher)

        fail_count = 0
        max_consecutive_failures = 5

        while not is_stopped():
            try:
                courses = self._api.query_courses(course.name, course_type)

                if not courses:
                    logger.debug("[%s] No courses found", course.name)
                    self._wait_random()
                    continue

                target = self._api.find_course_by_teacher(courses, course.teacher)

                if not target:
                    logger.debug("[%s] Teacher not found: %s", course.name, course.teacher)
                    self._wait_random()
                    continue

                if target.has_spots:
                    msg = f"Found spot! {course.name}-{course.teacher} remaining: {target.remaining}"
                    logger.info(msg)
                    self._notifier.send("Course Alert", msg)

                    result = self._api.select_course(target, course_type)

                    if result.success:
                        success_msg = f"Selection successful: {course.name}"
                        logger.info(success_msg)
                        self._notifier.send("Selection Success", success_msg)
                        return True
                else:
                    logger.info(
                        "[%s] %s full (%d/%d) %s",
                        course.name,
                        course.teacher,
                        target.selected_count,
                        target.capacity,
                        time.strftime("%H:%M:%S"),
                    )

                self._wait_random()
                fail_count = 0

            except SessionExpiredError:
                logger.warning("[%s] Session expired", course.name)
                return False

            except (NetworkError, CourseSelectionError) as exc:
                fail_count += 1
                logger.warning("[%s] Error: %s (fail %d)", course.name, exc, fail_count)

                if fail_count >= max_consecutive_failures:
                    logger.error("[%s] Too many failures, stopping", course.name)
                    return False

                time.sleep(5)

            except Exception as exc:
                fail_count += 1
                logger.error("[%s] Unexpected error: %s", course.name, exc)

                if fail_count >= max_consecutive_failures:
                    return False

                time.sleep(5)

        return True

    def _wait_random(self) -> None:
        """Wait for a random interval within configured bounds."""
        interval = random.uniform(
            self._settings.poll_interval_min,
            self._settings.poll_interval_max,
        )
        time.sleep(interval)
