"""Startup guard for forwarded-header trust on non-loopback binds."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

import pytest

from api.main import _assert_runtime_guard
from core.config import Settings, load_settings


@pytest.fixture(autouse=True)
def _session_key(monkeypatch: Any) -> None:
    monkeypatch.setenv("SENTINEL_SESSION_KEY", "a-test-session-key-with-at-least-32-chars")


def _settings(host: str, *, allow_remote: bool, trusted_proxy: str) -> Settings:
    base = load_settings(config_path=None)
    return replace(
        base,
        api=replace(
            base.api,
            host=host,
            allow_remote=allow_remote,
            trusted_proxy=trusted_proxy,
        ),
    )


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_bind_is_always_allowed(host: str, caplog: Any) -> None:
    with caplog.at_level(logging.WARNING):
        _assert_runtime_guard(_settings(host, allow_remote=False, trusted_proxy=""))
    assert "X-Forwarded" not in caplog.text


@pytest.mark.parametrize(
    ("allow_remote", "trusted_proxy"),
    [(False, ""), (True, ""), (False, "nginx")],
)
def test_non_loopback_without_both_opt_ins_still_refuses(
    allow_remote: bool, trusted_proxy: str
) -> None:
    with pytest.raises(RuntimeError, match="non-loopback"):
        _assert_runtime_guard(
            _settings(
                "0.0.0.0",  # noqa: S104 - test config value, never bound
                allow_remote=allow_remote,
                trusted_proxy=trusted_proxy,
            )
        )


def test_non_loopback_with_forwarded_header_trust_warns_at_startup(caplog: Any) -> None:
    settings = _settings("0.0.0.0", allow_remote=True, trusted_proxy="nginx")  # noqa: S104
    with caplog.at_level(logging.WARNING):
        _assert_runtime_guard(settings)
    assert "X-Forwarded" in caplog.text
    assert "loopback" in caplog.text.lower()
    assert "a-test-session-key-with-at-least-32-chars" not in caplog.text
