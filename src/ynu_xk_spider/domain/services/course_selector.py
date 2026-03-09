"""Course selector with monitoring and selection logic."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import TYPE_CHECKING

import requests  # type: ignore[import-untyped]

from ...exceptions import CourseSelectionError, NetworkError, SessionExpiredError
from ..models import MonitorOutcome

if TYPE_CHECKING:
    from ...config import AppSettings, CourseItem
    from ..models import CourseInfo
    from .course_api import CourseApiClient

logger = logging.getLogger(__name__)


class NotificationService:
    """Simple notification service via ServerChan."""

    def __init__(self, server_key: str | None = None) -> None:
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

    @property
    def enabled(self) -> bool:
        """Whether notification sending is configured."""
        return bool(self._server_key)


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

    HOT_PATH_LOG_INTERVAL = 30.0

    def __init__(
        self,
        api: CourseApiClient,
        settings: AppSettings,
        notifier: NotificationService | None = None,
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
        self._notification_executor: ThreadPoolExecutor | None = None
        self._notification_futures: list[Future[None]] = []
        self._notification_lock = threading.Lock()
        self._hot_path_log_times: dict[str, float] = {}

    def _notify_async(self, title: str, content: str) -> None:
        """Send notifications off the critical selection path."""
        if not self._notifier.enabled:
            return
        with self._notification_lock:
            self._notification_futures = [
                future for future in self._notification_futures if not future.done()
            ]
            if self._notification_executor is None:
                self._notification_executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="notification-sender",
                )
            future = self._notification_executor.submit(self._notifier.send, title, content)
            self._notification_futures.append(future)

    def wait_for_notifications(self, timeout: float | None = None) -> None:
        """Wait for pending async notifications to finish sending."""
        with self._notification_lock:
            futures = list(self._notification_futures)
            executor = self._notification_executor
            self._notification_futures.clear()
            self._notification_executor = None

        if futures:
            wait(futures, timeout=timeout)

        if executor is not None:
            executor.shutdown(wait=timeout is None)

    def run_monitoring_loop(
        self,
        course: CourseItem,
        course_type: str,
        is_stopped: Callable[[], bool],
    ) -> MonitorOutcome:
        """Monitor a single course and attempt selection when available.

        Args:
            course: Target course configuration.
            course_type: One of "素选", "主修", "体育".
            is_stopped: Callable returning True when stop requested.

        Returns:
            Monitoring outcome for this single target.
        """
        return self.run_group_monitoring_loop(
            course_name=course.name,
            course_type=course_type,
            targets=[course],
            is_stopped=is_stopped,
        )

    def run_group_monitoring_loop(
        self,
        course_name: str,
        course_type: str,
        targets: Sequence[CourseItem],
        is_stopped: Callable[[], bool],
    ) -> MonitorOutcome:
        """Monitor a course group with one shared query per polling cycle."""
        pending_targets = list(targets)
        teacher_names = ", ".join(target.teacher for target in pending_targets)
        logger.info(
            "Starting monitor: [%s] teachers=%s",
            course_name,
            teacher_names,
        )

        fail_count = 0
        max_consecutive_failures = 5

        while pending_targets and not is_stopped():
            try:
                courses = self._api.query_courses(course_name, course_type)

                if not courses:
                    self._debug_throttled(
                        f"no_courses:{course_type}:{course_name}",
                        "[%s] No courses found",
                        course_name,
                    )
                    if not self._wait_random(is_stopped):
                        return MonitorOutcome.STOPPED
                    continue

                remaining_targets: list[CourseItem] = []
                for target in pending_targets:
                    if is_stopped():
                        return MonitorOutcome.STOPPED

                    teacher_slots = self._api.find_courses_by_teacher(
                        courses,
                        target.teacher,
                    )

                    if not teacher_slots:
                        self._debug_throttled(
                            f"teacher_missing:{course_type}:{target.name}:{target.teacher}",
                            "[%s] Teacher not found: %s",
                            target.name,
                            target.teacher,
                        )
                        remaining_targets.append(target)
                        continue

                    available_slots = [slot for slot in teacher_slots if slot.has_spots]

                    if not available_slots:
                        self._log_full_slots(target, teacher_slots)
                        remaining_targets.append(target)
                        continue

                    if not self._try_select_available_slots(
                        target,
                        course_type,
                        available_slots,
                    ):
                        remaining_targets.append(target)

                if not remaining_targets:
                    return MonitorOutcome.SUCCESS

                pending_targets = remaining_targets
                if not self._wait_random(is_stopped):
                    return MonitorOutcome.STOPPED
                fail_count = 0

            except SessionExpiredError:
                logger.warning("[%s] Session expired", course_name)
                return MonitorOutcome.SESSION_EXPIRED

            except (NetworkError, CourseSelectionError) as exc:
                if is_stopped():
                    return MonitorOutcome.STOPPED
                fail_count += 1
                logger.warning("[%s] Error: %s (fail %d)", course_name, exc, fail_count)

                if fail_count >= max_consecutive_failures:
                    logger.error("[%s] Too many failures, stopping", course_name)
                    return MonitorOutcome.FAILED

                if not self._wait_with_stop(5, is_stopped):
                    return MonitorOutcome.STOPPED

            except Exception as exc:
                if is_stopped():
                    return MonitorOutcome.STOPPED
                fail_count += 1
                logger.error("[%s] Unexpected error: %s", course_name, exc)

                if fail_count >= max_consecutive_failures:
                    return MonitorOutcome.FAILED

                if not self._wait_with_stop(5, is_stopped):
                    return MonitorOutcome.STOPPED

        return MonitorOutcome.STOPPED if is_stopped() else MonitorOutcome.FAILED

    def _try_select_available_slots(
        self,
        course: CourseItem,
        course_type: str,
        available_slots: Sequence[CourseInfo],
    ) -> bool:
        """Try selecting the target from available slots."""
        logger.info(
            "Found %d available slot(s) for [%s] %s",
            len(available_slots),
            course.name,
            course.teacher,
        )

        for slot in available_slots:
            msg = f"Found spot! {course.name}-{course.teacher} remaining: {slot.remaining}"
            logger.info(msg)
            self._notify_async("Course Alert", msg)

            result = self._api.select_course(slot, course_type)

            if result.success:
                success_msg = f"Selection successful: {course.name}"
                logger.info(success_msg)
                self._notify_async("Selection Success", success_msg)
                return True

            if "时间冲突" in result.message or "该课程与已选课程时间冲突" in result.message:
                logger.info("[%s] Time conflict, trying next slot", course.name)
                continue

            if "人数已满" in result.message or "已满" in result.message:
                logger.debug("[%s] Slot full, trying next slot", course.name)
                continue

            logger.warning("[%s] Selection failed: %s", course.name, result.message)
            break

        return False

    def _log_full_slots(
        self,
        course: CourseItem,
        teacher_slots: Sequence[CourseInfo],
    ) -> None:
        """Log that all matched slots are full."""
        total_capacity = sum(slot.capacity for slot in teacher_slots)
        total_selected = sum(slot.selected_count for slot in teacher_slots)
        self._debug_throttled(
            f"full:{course.name}:{course.teacher}",
            "[%s] %s full (%d/%d) across %d slot(s) %s",
            course.name,
            course.teacher,
            total_selected,
            total_capacity,
            len(teacher_slots),
            time.strftime("%H:%M:%S"),
        )

    def _debug_throttled(self, key: str, message: str, *args: object) -> None:
        """Emit repetitive hot-path debug logs at a limited frequency."""
        now = time.monotonic()
        last = self._hot_path_log_times.get(key)
        if last is not None and now - last < self.HOT_PATH_LOG_INTERVAL:
            return
        self._hot_path_log_times[key] = now
        logger.debug(message, *args)

    def _wait_random(self, is_stopped: Callable[[], bool]) -> bool:
        """Wait for a random interval within configured bounds."""
        interval = random.uniform(
            self._settings.poll_interval_min,
            self._settings.poll_interval_max,
        )
        return self._wait_with_stop(interval, is_stopped)

    def _wait_with_stop(
        self,
        delay: float,
        is_stopped: Callable[[], bool],
    ) -> bool:
        """Sleep in short slices so stop requests can interrupt polling."""
        deadline = time.monotonic() + delay
        while not is_stopped():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(0.1, remaining))
        return False
