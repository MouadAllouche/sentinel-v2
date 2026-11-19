"""Tests for notification routing, throttling and rendering (Phase 11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from core.notifications.models import Channel, Notification, Transport
from core.notifications.render import render_message
from core.notifications.throttle import should_send
from engine.notifier import deliver, dispatch

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


class FakeTransport(Transport):
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        return True


def _channel(**changes: Any) -> Channel:
    data: dict[str, Any] = {
        "id": 1,
        "name": "webhook",
        "kind": "webhook",
        "enabled": True,
        "config": {"url": "http://127.0.0.1/hook", "secret_env": "SENTINEL_WEBHOOK_SECRET"},
        "min_severity": "high",
        "filters": {},
        "throttle": {"max_per_hour": 10, "cooldown_minutes": 15},
    }
    data.update(changes)
    return Channel(**data)


def _notification(**changes: Any) -> Notification:
    data: dict[str, Any] = {
        "kind": "incident.created",
        "incident_id": 1,
        "severity": "high",
        "title": "Possible brute force from 203.0.113.45",
        "score": 75,
        "reasons": ["+45 Sustained attack — repeated failures (rule ssh-bruteforce-by-ip)"],
        "first_seen": "2026-11-15T10:00:00+00:00",
        "last_seen": "2026-11-15T10:10:00+00:00",
        "target": "http://127.0.0.1:3000/incidents/1",
    }
    data.update(changes)
    return Notification(**data)


def test_render_contains_required_fields_and_caveat() -> None:
    rendered = render_message(_notification())
    assert "high" in rendered["subject"]
    assert "203.0.113.45" in rendered["body"]
    assert "Automated correlation; verify before acting" in rendered["body"]
    assert "75" in rendered["body"]
    assert "SENTINEL_WEBHOOK_SECRET" not in rendered["body"]


def test_routing_matrix_and_kill_switch() -> None:
    transport = FakeTransport()
    assert dispatch([_channel()], _notification(severity="medium"), transport, NOW) == 0
    assert dispatch([_channel()], _notification(severity="high"), transport, NOW) == 1
    assert dispatch([_channel(enabled=False)], _notification(), transport, NOW) == 0
    with __import__("pytest").raises(ValueError):
        dispatch([_channel(kind="unknown")], _notification(), transport, NOW)


def test_cooldown_rate_limit_and_digest() -> None:
    channel = _channel()
    history = [NOW - timedelta(minutes=5)]
    assert should_send(channel, _notification(), history, NOW) is False
    assert (
        should_send(
            _channel(throttle={"max_per_hour": 1}),
            _notification(),
            [NOW - timedelta(minutes=30)],
            NOW,
        )
        is False
    )
    assert should_send(_channel(throttle={"digest_minutes": 60}), _notification(), [], NOW) is True


def test_quiet_hours_and_suppression() -> None:
    channel = _channel(filters={"quiet_hours": {"start": 22, "end": 6}})
    assert (
        should_send(channel, _notification(), [], datetime(2026, 11, 15, 23, tzinfo=UTC)) is False
    )
    assert (
        should_send(
            _channel(filters={"statuses": ["false_positive"]}),
            _notification(kind="incident.status"),
            [],
            NOW,
        )
        is False
    )


def test_webhook_hmac_signature_and_url_validation(monkeypatch: Any) -> None:
    import hashlib
    import hmac
    import json
    from types import SimpleNamespace

    from engine.notifier import WebhookTransport

    monkeypatch.setenv("SENTINEL_WEBHOOK_SECRET", "a-secret-value")
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> Any:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["body"] = kwargs["content"]
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr("httpx.post", fake_post)
    transport = WebhookTransport("SENTINEL_WEBHOOK_SECRET", "http://127.0.0.1/hook")
    assert transport.send(_notification()) is True
    expected = hmac.new(b"a-secret-value", captured["body"], hashlib.sha256).hexdigest()
    assert captured["headers"]["X-Sentinel-Signature"] == expected
    assert json.loads(captured["body"])["subject"]
    bad = WebhookTransport("SENTINEL_WEBHOOK_SECRET", "http://127.0.0.1.attacker.tld/hook")
    assert bad.send(_notification()) is False
    missing = WebhookTransport("MISSING_SECRET", "http://127.0.0.1/hook")
    assert missing.send(_notification()) is False


def test_run_notifier_global_kill_switch(tmp_path: Any, monkeypatch: Any) -> None:
    from engine.notifier import run_notifier

    monkeypatch.setattr("engine.notifier.get_setting", lambda *args: False)
    assert run_notifier(tmp_path)["skipped"] is True


def test_transport_failure_is_isolated_and_retries() -> None:
    class Failing(Transport):
        def __init__(self) -> None:
            self.attempts = 0

        def send(self, notification: Notification) -> bool:
            self.attempts += 1
            return self.attempts >= 3

    failing = Failing()
    assert deliver(failing, _notification(), attempts=3, backoff_seconds=0) is True
    assert failing.attempts == 3
