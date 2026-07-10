from __future__ import annotations

import threading
import time
from typing import Any

import pytest
import requests

from ynu_xk_spider.config import AppSettings
from ynu_xk_spider.exceptions import NetworkError
from ynu_xk_spider.http.client import HttpClient
from ynu_xk_spider.utils.stop import StopToken


class _FakeCookies:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def update(self, values: dict[str, str]) -> None:
        self.values.update(values)


class _FakeSession:
    def __init__(self, should_fail: bool = False) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = _FakeCookies()
        self.should_fail = should_fail
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self.should_fail:
            raise requests.RequestException("boom")
        raise AssertionError("No real request expected in this test")

    def get(self, url: str, **kwargs: Any) -> Any:
        raise AssertionError("Client must go through Session.request")

    def post(self, url: str, **kwargs: Any) -> Any:
        raise AssertionError("Client must go through Session.request")

    def close(self) -> None:
        self.closed = True


def test_http_client_uses_thread_local_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    created_sessions: list[_FakeSession] = []

    def _build_session() -> _FakeSession:
        session = _FakeSession()
        created_sessions.append(session)
        return session

    monkeypatch.setattr("ynu_xk_spider.http.client.requests.Session", _build_session)

    client = HttpClient(AppSettings(student_code="20230001", password="secret"))
    client.set_auth("token-1", {"SESSION": "abc"})

    main_session = client._get_session()
    other_thread_session: dict[str, _FakeSession] = {}

    def _worker() -> None:
        other_thread_session["session"] = client._get_session()

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()

    refreshed_session = None
    client.set_auth("token-2", {"SESSION": "xyz"})
    refreshed_session = client._get_session()

    assert main_session is not other_thread_session["session"]
    assert refreshed_session is not main_session
    assert refreshed_session.headers["Token"] == "token-2"
    assert refreshed_session.cookies.values["SESSION"] == "xyz"
    assert len(created_sessions) == 3
    assert main_session.closed is True
    assert main_session not in client._sessions
    assert len(client._sessions) == 2


def test_http_client_retry_backoff_is_interruptible(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = StopToken()

    def _build_session() -> _FakeSession:
        return _FakeSession(should_fail=True)

    monkeypatch.setattr("ynu_xk_spider.http.client.requests.Session", _build_session)

    client = HttpClient(
        AppSettings(
            student_code="20230001",
            password="secret",
            max_retries=3,
            retry_backoff=1.0,
            retry_factor=1.0,
        ),
        stop=stop,
    )
    client.set_auth("token", {"SESSION": "abc"})

    def _trigger_stop() -> None:
        time.sleep(0.05)
        stop.set()

    stopper = threading.Thread(target=_trigger_stop)
    stopper.start()

    start = time.perf_counter()
    with pytest.raises(NetworkError):
        client.get("https://example.invalid")
    elapsed = time.perf_counter() - start

    stopper.join()
    assert elapsed < 0.5
