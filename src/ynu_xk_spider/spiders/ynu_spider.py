"""YNU course selection spider implementation."""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from ..browser.captcha import DdddocrSolver
from ..browser.manager import BrowserManager
from ..domain.models import MonitorOutcome
from ..domain.services.course_api import CourseApiClient
from ..domain.services.course_selector import CourseSelector
from ..domain.services.login import LoginService
from ..domain.services.notification import AsyncNotifier, ServerChanNotifier
from ..exceptions import LoginError, StopRequestedError
from ..http.client import HttpClient
from .base import BaseSpider

if TYPE_CHECKING:
    from ..config import AppSettings, CourseItem
    from ..domain.models import CourseTarget, CourseType, SessionData

logger = logging.getLogger(__name__)


class YnuCourseSpider(BaseSpider):
    """Concrete spider for YNU course selection.

    Orchestrates the complete workflow:
    1. Login via Selenium
    2. Initialize HTTP client with session
    3. Spawn monitoring threads for each course
    4. Handle session expiration and re-login

    Attributes:
        _settings: Application settings.
        _browser: Browser manager instance.
        _http: HTTP client instance.
        _max_workers: Maximum concurrent monitoring threads.
    """

    MAX_CONSECUTIVE_LOGIN_FAILURES = 5

    def __init__(self, settings: AppSettings, max_workers: int | None = None) -> None:
        """Initialize spider.

        Args:
            settings: Application settings.
            max_workers: Optional upper bound for monitor threads.
        """
        super().__init__()
        self._settings = settings
        self._browser = BrowserManager(settings)
        self._http = HttpClient(settings, stop=self.stop_token)
        self._solver = DdddocrSolver()
        self._notifier = AsyncNotifier(ServerChanNotifier(settings.server_chan_key))
        self._max_workers = max_workers

    def run_loop(self) -> None:
        """Main execution loop with auto-reconnect."""
        login_failures = 0

        while not self.is_stopped():
            try:
                logger.info("Attempting login...")
                session = self._perform_login()
                login_failures = 0

                self._http.set_auth(session.token, session.cookies)

                api = CourseApiClient(
                    http=self._http,
                    base_url=self._settings.base_url,
                    student_code=self._settings.student_code,
                    batch_code=session.batch_code,
                    campus=self._settings.campus,
                )

                selector = CourseSelector(api, self._settings, notifier=self._notifier)

                monitoring_result = self._run_monitoring(selector)
                if monitoring_result is MonitorOutcome.STOPPED:
                    logger.info("Monitoring stopped by request")
                    break
                if monitoring_result in (
                    MonitorOutcome.SESSION_EXPIRED,
                    MonitorOutcome.FAILED,
                ):
                    logger.info("Session expired or error, re-logging...")

            except StopRequestedError:
                logger.info("Stop requested during login")
                break
            except LoginError as exc:
                login_failures += 1
                logger.error(
                    "Login error (%d/%d): %s",
                    login_failures,
                    self.MAX_CONSECUTIVE_LOGIN_FAILURES,
                    exc,
                )
                if login_failures >= self.MAX_CONSECUTIVE_LOGIN_FAILURES:
                    logger.error("Too many consecutive login failures, stopping spider")
                    self.stop()
                    break
                if not self._wait_or_stop(10):
                    break

            except Exception as exc:
                logger.error("Unexpected error: %s", exc)
                if not self._wait_or_stop(5):
                    break

            if not self.is_stopped():
                if not self._wait_or_stop(2):
                    break

    def _wait_or_stop(self, delay: float) -> bool:
        """Wait for a delay unless a stop request arrives first."""
        return self.stop_token.wait(delay)

    def _perform_login(self) -> SessionData:
        """Perform login and return session data.

        The browser is only needed while logging in; it is closed on every
        exit path once the attempt finishes (the HTTP client takes over).

        Returns:
            SessionData if login succeeds.
        """
        login_service = LoginService(
            self._settings,
            self._browser,
            self._solver,
            stop=self.stop_token,
        )

        try:
            return login_service.login()
        except StopRequestedError:
            raise
        except LoginError:
            raise
        except Exception as exc:
            logger.error("Login failed: %s", exc)
            raise LoginError(f"Login failed: {exc}") from exc
        finally:
            self._browser.shutdown()

    def _resolve_worker_count(self, total_courses: int) -> int:
        """Compute worker count for the thread pool."""
        if self._max_workers is None:
            return total_courses

        configured = max(1, self._max_workers)
        return min(configured, total_courses)

    def _run_monitoring(self, selector: CourseSelector) -> MonitorOutcome:
        """Run course monitoring with thread pool.

        Args:
            selector: Course selector instance.

        Returns:
            Aggregate monitoring outcome for the current batch.
        """
        courses = self._settings.courses.all_courses

        if not courses:
            logger.warning("No courses configured")
            return MonitorOutcome.SUCCESS

        grouped_courses = self._group_course_targets(courses)
        futures: list[Future[MonitorOutcome]] = []
        future_targets: dict[Future[MonitorOutcome], list[CourseItem]] = {}
        batch_stop = self.stop_token.child()
        success_count = 0
        total_targets = len(courses)
        worker_count = self._resolve_worker_count(len(grouped_courses))

        try:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                for course_name, course_type, targets in grouped_courses:
                    future = executor.submit(
                        selector.run_group_monitoring_loop,
                        course_name,
                        course_type,
                        targets,
                        batch_stop,
                    )
                    futures.append(future)
                    future_targets[future] = targets

                logger.info(
                    "Started %d monitoring threads for %d course groups covering %d targets",
                    len(futures),
                    len(grouped_courses),
                    total_targets,
                )

                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result is MonitorOutcome.STOPPED:
                            if self.is_stopped():
                                logger.info("Monitoring stopped")
                                return MonitorOutcome.STOPPED
                            logger.warning("Monitoring group stopped unexpectedly")
                            batch_stop.set()
                            return MonitorOutcome.FAILED
                        if result in (
                            MonitorOutcome.SESSION_EXPIRED,
                            MonitorOutcome.FAILED,
                        ):
                            logger.info("Monitoring group ended with %s", result.value)
                            batch_stop.set()
                            return result
                        if result is MonitorOutcome.SUCCESS:
                            success_count += len(future_targets[future])
                            logger.info(
                                "Course selection successful (%d/%d)",
                                success_count,
                                total_targets,
                            )
                            # Check if all courses are completed
                            if success_count >= total_targets:
                                logger.info(
                                    "All %d courses selected successfully, stopping spider",
                                    total_targets,
                                )
                                self.stop()
                                return MonitorOutcome.SUCCESS
                            else:
                                logger.info(
                                    "Continue monitoring remaining %d courses",
                                    total_targets - success_count,
                                )
                    except Exception as exc:
                        logger.error("Thread error: %s", exc)
                        batch_stop.set()
                        return MonitorOutcome.FAILED

            return MonitorOutcome.SUCCESS
        finally:
            self._notifier.flush()

    def on_stop(self) -> None:
        """Cleanup on spider stop."""
        self._http.close()
        self._browser.shutdown()

    def _group_course_targets(
        self,
        courses: list[CourseTarget],
    ) -> list[tuple[str, CourseType, list[CourseItem]]]:
        """Group targets by (course type, course name) to avoid duplicate queries."""
        grouped: dict[tuple[CourseType, str], list[CourseItem]] = {}
        for target in courses:
            key = (target.course_type, target.item.name)
            grouped.setdefault(key, []).append(target.item)

        return [
            (course_name, course_type, targets)
            for (course_type, course_name), targets in grouped.items()
        ]
