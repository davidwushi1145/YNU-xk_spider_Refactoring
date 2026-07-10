from __future__ import annotations

import gc
import threading
import time
import weakref

import pytest

from ynu_xk_spider.exceptions import StopRequestedError
from ynu_xk_spider.utils.stop import StopToken


def test_wait_returns_true_when_delay_elapses() -> None:
    token = StopToken()
    assert token.wait(0.01) is True


def test_wait_is_interrupted_by_set() -> None:
    token = StopToken()
    threading.Timer(0.05, token.set).start()

    start = time.perf_counter()
    assert token.wait(5.0) is False
    assert time.perf_counter() - start < 0.5


def test_raise_if_set() -> None:
    token = StopToken()
    token.raise_if_set()

    token.set()
    with pytest.raises(StopRequestedError):
        token.raise_if_set()


def test_child_stops_with_parent_but_not_vice_versa() -> None:
    parent = StopToken()
    child = parent.child()

    child.set()
    assert not parent.is_set()

    sibling = parent.child()
    parent.set()
    assert sibling.is_set()


def test_child_of_already_stopped_parent_is_set() -> None:
    parent = StopToken()
    parent.set()
    assert parent.child().is_set()


def test_unreferenced_child_can_be_garbage_collected() -> None:
    parent = StopToken()
    child = parent.child()
    child_ref = weakref.ref(child)

    del child
    gc.collect()

    assert child_ref() is None


def test_live_descendant_keeps_stop_propagation_chain_alive() -> None:
    parent = StopToken()
    grandchild = parent.child().child()

    gc.collect()
    parent.set()

    assert grandchild.is_set()


def test_stopped_child_releases_its_parent() -> None:
    parent = StopToken()
    child = parent.child()
    parent_ref = weakref.ref(parent)

    child.set()
    del parent
    gc.collect()

    assert parent_ref() is None
