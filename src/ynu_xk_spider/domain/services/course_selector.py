"""Course selector with monitoring and selection logic."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from ...exceptions import CourseSelectionError, NetworkError, SessionExpiredError
from ..models import MonitorOutcome
from .notification import Notifier, ServerChanNotifier

if TYPE_CHECKING:
    from ...config import AppSettings, CourseItem
    from ...utils.stop import StopToken
    from ..models import CourseInfo, CourseType
    from .course_api import CourseApiClient

logger = logging.getLogger(__name__)


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
        notifier: Notifier | None = None,
    ) -> None:
        """Initialize course selector.

        Args:
            api: Course API client.
            settings: Application settings.
            notifier: Optional notification sink; defaults to synchronous
                ServerChan push configured from settings. Callers that need
                non-blocking delivery should inject and own an AsyncNotifier.
        """
        self._api = api
        self._settings = settings
        self._notifier: Notifier = (
            notifier
            if notifier is not None
            else ServerChanNotifier(settings.server_chan_key)
        )
        self._hot_path_log_times: dict[str, float] = {}

    def run_monitoring_loop(
        self,
        course: CourseItem,
        course_type: CourseType,
        stop: StopToken,
    ) -> MonitorOutcome:
        """Monitor a single course and attempt selection when available.

        Args:
            course: Target course configuration.
            course_type: Course category of the target.
            stop: Stop token honored during monitoring.

        Returns:
            Monitoring outcome for this single target.
        """
        return self.run_group_monitoring_loop(
            course_name=course.name,
            course_type=course_type,
            targets=[course],
            stop=stop,
        )

    def run_group_monitoring_loop(
        self,
        course_name: str,
        course_type: CourseType,
        targets: Sequence[CourseItem],
        stop: StopToken,
    ) -> MonitorOutcome:
        """Monitor a course group with one shared query per polling cycle."""
        pending_targets = list(targets)
        if not pending_targets:
            return MonitorOutcome.SUCCESS

        teacher_names = ", ".join(target.teacher for target in pending_targets)
        logger.info(
            "Starting monitor: [%s] teachers=%s",
            course_name,
            teacher_names,
        )

        fail_count = 0
        max_consecutive_failures = 5

        while pending_targets and not stop.is_set():
            try:
                courses = self._api.query_courses(course_name, course_type)

                if not courses:
                    self._debug_throttled(
                        f"no_courses:{course_type}:{course_name}",
                        "[%s] No courses found",
                        course_name,
                    )
                    if not self._wait_random(stop):
                        return MonitorOutcome.STOPPED
                    continue

                remaining_targets: list[CourseItem] = []
                for index, target in enumerate(pending_targets):
                    try:
                        if stop.is_set():
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
                    except Exception:
                        pending_targets = remaining_targets + pending_targets[index:]
                        raise

                if not remaining_targets:
                    return MonitorOutcome.SUCCESS

                pending_targets = remaining_targets
                if not self._wait_random(stop):
                    return MonitorOutcome.STOPPED
                fail_count = 0

            except SessionExpiredError:
                logger.warning("[%s] Session expired", course_name)
                return MonitorOutcome.SESSION_EXPIRED

            except (NetworkError, CourseSelectionError) as exc:
                fail_count, outcome = self._handle_monitoring_failure(
                    course_name=course_name,
                    exc=exc,
                    fail_count=fail_count,
                    max_consecutive_failures=max_consecutive_failures,
                    stop=stop,
                    log_method=logger.warning,
                    log_message="[%s] Error: %s (fail %d)",
                )
                if outcome is not None:
                    return outcome

            except Exception as exc:
                fail_count, outcome = self._handle_monitoring_failure(
                    course_name=course_name,
                    exc=exc,
                    fail_count=fail_count,
                    max_consecutive_failures=max_consecutive_failures,
                    stop=stop,
                    log_method=logger.error,
                    log_message="[%s] Unexpected error: %s (fail %d)",
                )
                if outcome is not None:
                    return outcome

        return MonitorOutcome.STOPPED if stop.is_set() else MonitorOutcome.FAILED

    def _handle_monitoring_failure(
        self,
        course_name: str,
        exc: Exception,
        fail_count: int,
        max_consecutive_failures: int,
        stop: StopToken,
        *,
        log_method: Callable[..., None],
        log_message: str,
    ) -> tuple[int, MonitorOutcome | None]:
        """Handle a failed monitoring attempt and decide whether to retry."""
        if stop.is_set():
            return fail_count, MonitorOutcome.STOPPED

        fail_count += 1
        log_method(log_message, course_name, exc, fail_count)

        if fail_count >= max_consecutive_failures:
            logger.error("[%s] Too many failures, stopping", course_name)
            return fail_count, MonitorOutcome.FAILED

        if not self._wait_with_stop(5, stop):
            return fail_count, MonitorOutcome.STOPPED

        return fail_count, None

    def _try_select_available_slots(
        self,
        course: CourseItem,
        course_type: CourseType,
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
            self._notifier.send("Course Alert", msg)

            result = self._api.select_course(slot, course_type)

            if result.success:
                success_msg = f"Selection successful: {course.name}"
                logger.info(success_msg)
                self._notifier.send("Selection Success", success_msg)
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

    def _wait_random(self, stop: StopToken) -> bool:
        """Wait for a random interval within configured bounds."""
        interval = random.uniform(
            self._settings.poll_interval_min,
            self._settings.poll_interval_max,
        )
        return self._wait_with_stop(interval, stop)

    def _wait_with_stop(self, delay: float, stop: StopToken) -> bool:
        """Block for a delay unless stop is requested first.

        Returns:
            True if the full delay elapsed, False when interrupted by stop.
        """
        return stop.wait(delay)
