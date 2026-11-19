"""Notification delivery with fake/real transports and failure isolation."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import smtplib
import ssl
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.notifications.models import Channel, Notification, Transport
from core.notifications.render import render_message
from core.notifications.throttle import should_send
from core.timeutil import utc_now
from storage.notification_repository import (
    list_channels,
    list_notifications,
    log_notification,
    record_change,
)
from storage.repositories import get_setting
from storage.risk_repository import get_assessment

__all__ = ["WebhookTransport", "deliver", "dispatch", "run_notifier"]

logger = logging.getLogger(__name__)


class WebhookTransport(Transport):
    """JSON POST with an HMAC signature; the secret is read from the env var NAME."""

    def __init__(self, secret_env: str, url: str = "", allowed_hosts: tuple[str, ...] = ()) -> None:
        self.secret_env = secret_env
        self.url = url
        self.allowed_hosts = allowed_hosts

    def send(self, notification: Notification) -> bool:
        from urllib.parse import urlparse

        import httpx

        secret = os.environ.get(self.secret_env, "")
        if not self.secret_env or not secret:
            return False
        parsed = urlparse(self.url)
        if parsed.username or parsed.password:
            return False
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        allowed = bool(self.allowed_hosts) and parsed.hostname in self.allowed_hosts
        if not (loopback and parsed.scheme == "http") and not (
            parsed.scheme == "https" and allowed
        ):
            return False
        message = render_message(notification)
        body = json.dumps(message, sort_keys=True).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        url = self.url
        response = httpx.post(
            url,
            content=body,
            headers={"Content-Type": "application/json", "X-Sentinel-Signature": signature},
            timeout=5.0,
        )
        return 200 <= response.status_code < 300


class EmailTransport(Transport):
    """SMTP transport requiring STARTTLS unless explicitly disabled."""

    def __init__(
        self, host: str, port: int, sender: str, recipient: str, allow_insecure: bool = False
    ) -> None:
        self.host, self.port = host, port
        self.sender, self.recipient = sender, recipient
        self.allow_insecure = allow_insecure

    def send(self, notification: Notification) -> bool:
        message = render_message(notification)
        with smtplib.SMTP(self.host, self.port, timeout=5) as client:
            client.ehlo()
            if not self.allow_insecure:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            text = f"Subject: {message['subject']}\n\n{message['body']}"
            client.sendmail(self.sender, [self.recipient], text)
        return True


class TelegramTransport(Transport):
    """Bot API transport; token comes from the env var NAME in channel config."""

    def __init__(self, token_env: str, chat_id: str) -> None:
        self.token_env, self.chat_id = token_env, chat_id

    def send(self, notification: Notification) -> bool:
        import httpx

        token = os.environ.get(self.token_env, "")
        if not self.token_env or not token or not self.chat_id:
            return False
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": self.chat_id, "text": render_message(notification)["body"]},
            timeout=5.0,
        )
        return 200 <= response.status_code < 300


def deliver(
    transport: Transport,
    notification: Notification,
    *,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> bool:
    for attempt in range(attempts):
        try:
            if transport.send(notification):
                return True
        except Exception as exc:  # noqa: BLE001 - delivery failure never breaks the cycle
            logger.warning("notification delivery attempt failed: %s", type(exc).__name__)
            continue
        if attempt + 1 < attempts and backoff_seconds:
            time.sleep(backoff_seconds * (2**attempt))
    return False


def dispatch(
    channels: list[Channel],
    notification: Notification,
    transport: Transport,
    now: datetime,
    *,
    global_enabled: bool = True,
) -> int:
    if not global_enabled:
        return 0
    sent = 0
    for channel in channels:
        if channel.kind not in {"webhook", "email", "telegram"}:
            raise ValueError(f"unknown notification channel kind: {channel.kind}")
        if not should_send(channel, notification, [], now):
            continue
        if deliver(transport, notification, attempts=1, backoff_seconds=0):
            sent += 1
    return sent


def _transport(channel: Channel) -> Transport | None:
    if channel.kind == "webhook":
        secret_env = str(channel.config.get("secret_env", ""))
        url = str(channel.config.get("url", ""))
        hosts = tuple(channel.config.get("allowed_hosts", ()))
        return WebhookTransport(secret_env, url, hosts) if secret_env and url else None
    if channel.kind == "email":
        return EmailTransport(
            str(channel.config.get("host", "127.0.0.1")),
            int(channel.config.get("port", 25)),
            str(channel.config.get("sender", "")),
            str(channel.config.get("recipient", "")),
            bool(channel.config.get("allow_insecure", False)),
        )
    if channel.kind == "telegram":
        token_env = str(channel.config.get("token_env", ""))
        chat_id = str(channel.config.get("chat_id", ""))
        return TelegramTransport(token_env, chat_id) if token_env and chat_id else None
    return None


def run_notifier(
    db_path: str | Path | None = None,
    now: datetime | None = None,
    settings: Any = None,
) -> dict[str, Any]:
    reference = now or utc_now()
    db_enabled = get_setting("notifications.enabled", db_path) is True
    static_enabled = settings is None or settings.notifications.enabled
    if not (db_enabled and static_enabled):
        return {"skipped": True, "sent": 0}
    from storage.incident_repository import list_incidents

    logs = list_notifications(db_path)
    already = {
        (row["channel_id"], row["incident_id"], row["detail"])
        for row in logs
        if row["status"] == "sent"
    }
    channels = [channel for channel in list_channels(db_path) if channel.enabled]
    sent = 0

    def candidates() -> list[tuple[int, str, str, str]]:
        items: list[tuple[int, str, str, str]] = []
        for incident in list_incidents(db_path=db_path):
            if incident.get("status") in {"false_positive", "closed", "merged"}:
                continue
            items.append(
                (
                    int(incident["id"]),
                    str(incident.get("severity", "low")),
                    str(incident.get("title", "Incident")),
                    "created",
                )
            )
        for change in _pending_changes(db_path):
            items.append(
                (
                    int(change["target_id"]),
                    str(change["to_severity"]),
                    f"Incident {change['target_id']} severity changed",
                    "escalated",
                )
            )
        return items

    for channel in channels:
        transport = _transport(channel)
        if transport is None:
            continue
        history = []
        for row in logs:
            if row["channel_id"] == channel.id:
                try:
                    history.append(datetime.fromisoformat(row["sent_at"]))
                except ValueError:
                    continue
        for incident_id, severity, title, trigger in candidates():
            key = (channel.id, incident_id, trigger)
            if key in already:
                continue
            assessment = get_assessment("incident", incident_id, db_path)
            notification = Notification(
                kind=f"incident.{trigger}",
                incident_id=incident_id,
                severity=severity,
                title=title,
                score=float(assessment["score"]) if assessment else 0.0,
                reasons=[
                    str(item.get("explanation", ""))
                    for item in (assessment or {}).get("reasons", [])
                ],
                target=str(channel.config.get("base_url", "")),
            )
            if should_send(channel, notification, history, reference) and deliver(
                transport, notification, attempts=3, backoff_seconds=0
            ):
                log_notification(channel.id, incident_id, "sent", trigger, db_path)
                record_change("notification.sent", incident_id, db_path)
                already.add(key)
                sent += 1
            else:
                log_notification(
                    channel.id, incident_id, "failed", f"{trigger} delivery failed", db_path
                )
    return {"skipped": False, "sent": sent}


def _pending_changes(db_path: str | Path | None) -> list[dict[str, Any]]:
    from contextlib import closing

    from storage.database import get_connection

    with closing(get_connection(db_path)) as connection:
        rows = connection.execute("SELECT * FROM risk_changes ORDER BY id DESC LIMIT 50").fetchall()
    return [dict(row) for row in rows]
