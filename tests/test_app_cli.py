from __future__ import annotations

from pathlib import Path

from ynu_xk_spider.app import parse_args


def test_parse_args_accepts_explicit_argv() -> None:
    args = parse_args(["--headless", "--log-level", "DEBUG", "-c", "custom.json"])

    assert args.headless is True
    assert args.log_level == "DEBUG"
    assert args.config == Path("custom.json")


def test_parse_args_defaults_are_isolated_from_process_argv() -> None:
    args = parse_args([])

    assert args.headless is False
    assert args.log_level is None
    assert args.config == Path("config.json")
