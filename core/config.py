"""Static/bootstrap configuration loading.

The editable, user-facing configuration lives in the database (Phases 4+).
This module handles only static settings: file paths, collector toggles,
intervals, API bind details and the global notification kill switch.

The built-in defaults below mirror ``config/settings.toml``. Loading the TOML
file is the single deliberate filesystem exception in ``core/``; all parsing,
merging and validation lives in the pure ``Settings.from_dict`` path.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ApiSettings",
    "CollectorSettings",
    "EngineSettings",
    "NotificationSettings",
    "PathsSettings",
    "Settings",
    "TimeSettings",
    "default_settings_dict",
    "load_settings",
]


def default_settings_dict() -> dict[str, dict[str, Any]]:
    """Return a fresh copy of the built-in static defaults."""
    return {
        "paths": {
            "database": "sentinel.db",
            "auth_log": "/var/log/auth.log",
            "dpkg_log": "/var/log/dpkg.log",
            "log_dir": "logs",
        },
        "time": {"naive_timezone": "local"},
        "collectors": {
            "auth_source": "auth_log",
            "journald_unit": "ssh",
            "network": True,
            "listening": True,
            "processes": True,
            "filesystem": True,
            "dpkg": True,
            "system": True,
            "max_process_events_per_run": 200,
        },
        "engine": {
            "collect_interval_seconds": 60,
            "analyze_interval_seconds": 60,
            "retention_interval_hours": 24,
        },
        "api": {
            "host": "127.0.0.1",
            "port": 8000,
            "session_idle_minutes": 120,
            "session_absolute_hours": 12,
        },
        "notifications": {"enabled": False},
        "drift": {"allow_custom_paths": False},
    }


@dataclass(frozen=True)
class PathsSettings:
    database: Path
    auth_log: Path
    dpkg_log: Path
    log_dir: Path


@dataclass(frozen=True)
class TimeSettings:
    naive_timezone: str


@dataclass(frozen=True)
class CollectorSettings:
    auth_source: str
    journald_unit: str
    network: bool
    listening: bool
    processes: bool
    filesystem: bool
    dpkg: bool
    system: bool
    max_process_events_per_run: int


@dataclass(frozen=True)
class EngineSettings:
    collect_interval_seconds: int
    analyze_interval_seconds: int
    retention_interval_hours: int


@dataclass(frozen=True)
class ApiSettings:
    host: str
    port: int
    session_idle_minutes: int
    session_absolute_hours: int
    session_key: str | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class NotificationSettings:
    enabled: bool


@dataclass(frozen=True)
class DriftSettings:
    allow_custom_paths: bool


@dataclass(frozen=True)
class Settings:
    paths: PathsSettings
    time: TimeSettings
    collectors: CollectorSettings
    engine: EngineSettings
    api: ApiSettings
    notifications: NotificationSettings
    drift: DriftSettings


def _check_keys(data: dict[str, Any], allowed: dict[str, Any], section: str) -> None:
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ValueError(f"unknown config key(s) in [{section}]: {', '.join(unknown)}")


def _as_str(section: str, key: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{section}.{key} must be a non-empty string")
    return value.strip()


def _as_int(section: str, key: str, value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{section}.{key} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{section}.{key} must be between {minimum} and {maximum}")
    return value


def _as_bool(section: str, key: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{section}.{key} must be a boolean")
    return value


def _as_path(section: str, key: str, value: Any, root: Path) -> Path:
    text = os.path.expanduser(_as_str(section, key, value))
    path = Path(text)
    return path if path.is_absolute() else root / path


def _merged_sections(
    file_data: dict[str, Any], env: Mapping[str, str], root: Path
) -> dict[str, dict[str, Any]]:
    defaults = default_settings_dict()
    unknown_sections = sorted(set(file_data) - set(defaults))
    if unknown_sections:
        raise ValueError(f"unknown config section(s): {', '.join(unknown_sections)}")
    merged: dict[str, dict[str, Any]] = {}
    for section, allowed in defaults.items():
        supplied = file_data.get(section, {})
        if not isinstance(supplied, dict):
            raise ValueError(f"config section [{section}] must be a table")
        _check_keys(supplied, allowed, section)
        merged[section] = {**allowed, **supplied}
    if "SENTINEL_DB_PATH" in env:
        merged["paths"]["database"] = env["SENTINEL_DB_PATH"]
    return merged


def _build_settings(
    merged: dict[str, dict[str, Any]], env: Mapping[str, str], root: Path
) -> Settings:
    paths = merged["paths"]
    time_section = merged["time"]
    collectors = merged["collectors"]
    engine = merged["engine"]
    api = merged["api"]
    notifications = merged["notifications"]
    drift = merged["drift"]

    naive_timezone = _as_str("time", "naive_timezone", time_section["naive_timezone"])
    if naive_timezone.lower() == "utc":
        naive_timezone = "UTC"
    elif naive_timezone.lower() != "local":
        raise ValueError("time.naive_timezone must be 'local' or 'UTC'")

    auth_source = _as_str("collectors", "auth_source", collectors["auth_source"])
    if auth_source not in {"auth_log", "journald", "both"}:
        raise ValueError("collectors.auth_source must be 'auth_log', 'journald' or 'both'")

    return Settings(
        paths=PathsSettings(
            database=_as_path("paths", "database", paths["database"], root),
            auth_log=_as_path("paths", "auth_log", paths["auth_log"], root),
            dpkg_log=_as_path("paths", "dpkg_log", paths["dpkg_log"], root),
            log_dir=_as_path("paths", "log_dir", paths["log_dir"], root),
        ),
        time=TimeSettings(naive_timezone=naive_timezone),
        collectors=CollectorSettings(
            auth_source=auth_source,
            journald_unit=_as_str("collectors", "journald_unit", collectors["journald_unit"]),
            network=_as_bool("collectors", "network", collectors["network"]),
            listening=_as_bool("collectors", "listening", collectors["listening"]),
            processes=_as_bool("collectors", "processes", collectors["processes"]),
            filesystem=_as_bool("collectors", "filesystem", collectors["filesystem"]),
            dpkg=_as_bool("collectors", "dpkg", collectors["dpkg"]),
            system=_as_bool("collectors", "system", collectors["system"]),
            max_process_events_per_run=_as_int(
                "collectors",
                "max_process_events_per_run",
                collectors["max_process_events_per_run"],
                minimum=1,
                maximum=100_000,
            ),
        ),
        engine=EngineSettings(
            collect_interval_seconds=_as_int(
                "engine",
                "collect_interval_seconds",
                engine["collect_interval_seconds"],
                minimum=1,
                maximum=86_400,
            ),
            analyze_interval_seconds=_as_int(
                "engine",
                "analyze_interval_seconds",
                engine["analyze_interval_seconds"],
                minimum=1,
                maximum=86_400,
            ),
            retention_interval_hours=_as_int(
                "engine",
                "retention_interval_hours",
                engine["retention_interval_hours"],
                minimum=1,
                maximum=8_760,
            ),
        ),
        api=ApiSettings(
            host=_as_str("api", "host", api["host"]),
            port=_as_int("api", "port", api["port"], minimum=1, maximum=65_535),
            session_idle_minutes=_as_int(
                "api",
                "session_idle_minutes",
                api["session_idle_minutes"],
                minimum=1,
                maximum=10_080,
            ),
            session_absolute_hours=_as_int(
                "api",
                "session_absolute_hours",
                api["session_absolute_hours"],
                minimum=1,
                maximum=720,
            ),
            session_key=env.get("SENTINEL_SESSION_KEY"),
        ),
        notifications=NotificationSettings(
            enabled=_as_bool("notifications", "enabled", notifications["enabled"])
        ),
        drift=DriftSettings(
            allow_custom_paths=_as_bool("drift", "allow_custom_paths", drift["allow_custom_paths"])
        ),
    )


def load_settings(
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    root: str | Path | None = None,
) -> Settings:
    """Load defaults, overlay an optional TOML file, then apply env overrides.

    ``env`` and ``root`` are injectable so tests never read the process
    environment or the real project root.
    """
    environment: Mapping[str, str] = os.environ if env is None else env
    root_path = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    selected = config_path if config_path is not None else environment.get("SENTINEL_CONFIG")
    file_data: dict[str, Any] = {}
    if selected:
        path = Path(os.path.expanduser(str(selected)))
        if not path.is_absolute():
            path = root_path / path
        if path.exists():
            with path.open("rb") as handle:
                loaded = tomllib.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError("config file must contain a TOML table")
            file_data = loaded
    merged = _merged_sections(file_data, environment, root_path)
    return _build_settings(merged, environment, root_path)
