"""YNU course selection spider implementation."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from ..browser.captcha import DdddocrSolver
from ..browser.manager import BrowserManager
from ..domain.services.course_api import CourseApiClient
from ..domain.services.course_selector import CourseSelector
from ..domain.services.login import LoginService
from ..exceptions import LoginError
from ..http.client import HttpClient
from .base import BaseSpider

if TYPE_CHECKING:
    from ..config import AppSettings
    from ..domain.models import SessionData

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
        self._browser = BrowserManager.instance(settings)
        self._http = HttpClient(settings)
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

                selector = CourseSelector(api, self._settings)

                if not self._run_monitoring(selector):
                    logger.info("Session expired or error, re-logging...")

            except LoginError as exc:
                login_failures += 1
                logger.error(
                    "Login error (%d/%d): %s",
                    login_failures,
                    self.MAX_CONSECUTIVE_LOGIN_FAILURES,
                    exc,
                )
                self._browser.shutdown()
                if login_failures >= self.MAX_CONSECUTIVE_LOGIN_FAILURES:
                    logger.error("Too many consecutive login failures, stopping spider")
                    self.stop()
                    break
                time.sleep(10)

            except Exception as exc:
                logger.error("Unexpected error: %s", exc)
                self._browser.shutdown()
                time.sleep(5)

            if not self.is_stopped():
                time.sleep(2)

    def _perform_login(self) -> SessionData:
        """Perform login and return session data.

        Returns:
            SessionData if login succeeds.
        """
        solver = DdddocrSolver()
        login_service = LoginService(self._settings, self._browser, solver)

        try:
            return login_service.login()
        except LoginError:
            raise
        except Exception as exc:
            logger.error("Login failed: %s", exc)
            raise LoginError(f"Login failed: {exc}") from exc

    def _resolve_worker_count(self, total_courses: int) -> int:
        """Compute worker count for the thread pool."""
        if self._max_workers is None:
            return total_courses

        configured = max(1, self._max_workers)
        return min(configured, total_courses)

    def _run_monitoring(self, selector: CourseSelector) -> bool:
        """Run course monitoring with thread pool.

        Args:
            selector: Course selector instance.

        Returns:
            True if all tasks completed successfully, False if session expired.
        """
        courses = self._settings.courses.all_courses

        if not courses:
            logger.warning("No courses configured")
            return True

        futures: list[Future[bool]] = []
        batch_stop_event = threading.Event()
        success_count = 0
        total_courses = len(courses)
        worker_count = self._resolve_worker_count(total_courses)

        def should_stop() -> bool:
            return self.is_stopped() or batch_stop_event.is_set()

        try:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                for course, course_type in courses:
                    future = executor.submit(
                        selector.run_monitoring_loop,
                        course,
                        course_type,
                        should_stop,
                    )
                    futures.append(future)

                logger.info(
                    "Started %d monitoring threads for %d courses",
                    len(futures),
                    total_courses,
                )

                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result is False:
                            logger.info("Thread signaled session expired")
                            batch_stop_event.set()
                            return False
                        elif result is True:
                            success_count += 1
                            logger.info(
                                "Course selection successful (%d/%d)",
                                success_count,
                                total_courses,
                            )
                            # Check if all courses are completed
                            if success_count >= total_courses:
                                logger.info(
                                    "All %d courses selected successfully, stopping spider",
                                    total_courses,
                                )
                                self.stop()
                                return True
                            else:
                                logger.info(
                                    "Continue monitoring remaining %d courses",
                                    total_courses - success_count,
                                )
                    except Exception as exc:
                        logger.error("Thread error: %s", exc)
                        batch_stop_event.set()
                        return False

            return True
        finally:
            selector.wait_for_notifications()

    def on_stop(self) -> None:
        """Cleanup on spider stop."""
        self._http.close()
        self._browser.shutdown()
