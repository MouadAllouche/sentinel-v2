"""Tests for static configuration loading and validation (Phase 0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import load_settings


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_without_a_file(tmp_path: Path) -> None:
    settings = load_settings(config_path=tmp_path / "missing.toml", root=tmp_path, env={})
    assert settings.paths.database == tmp_path / "sentinel.db"
    assert settings.paths.auth_log == Path("/var/log/auth.log")
    assert settings.paths.dpkg_log == Path("/var/log/dpkg.log")
    assert settings.paths.log_dir == tmp_path / "logs"
    assert settings.time.naive_timezone == "local"
    assert settings.collectors.auth_source == "auth_log"
    assert settings.collectors.journald_unit == "ssh"
    assert settings.collectors.max_process_events_per_run == 200
    assert settings.engine.collect_interval_seconds == 60
    assert settings.engine.analyze_interval_seconds == 60
    assert settings.engine.retention_interval_hours == 24
    assert settings.api.host == "127.0.0.1"
    assert settings.api.port == 8000
    assert settings.api.session_idle_minutes == 120
    assert settings.api.session_absolute_hours == 12
    assert settings.notifications.enabled is False
    assert settings.api.session_key is None


def test_file_overrides_merge_over_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path, "[api]\nport = 9000\n[notifications]\nenabled = true\n")
    settings = load_settings(config_path=path, root=tmp_path, env={})
    assert settings.api.port == 9000
    assert settings.notifications.enabled is True
    assert settings.api.host == "127.0.0.1"


def test_unknown_sections_and_keys_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "[api]\nport = 8000\n[api.bogus]\nx = 1\n")
    with pytest.raises(ValueError, match="unknown"):
        load_settings(config_path=path, root=tmp_path, env={})
    path = _write(tmp_path, '[collectors]\nauth_source = "auth_log"\nnope = 1\n')
    with pytest.raises(ValueError, match="nope"):
        load_settings(config_path=path, root=tmp_path, env={})


def test_env_overrides_paths_and_session_key(tmp_path: Path) -> None:
    path = _write(tmp_path, '[paths]\ndatabase = "from-file.db"\n')
    env = {"SENTINEL_DB_PATH": str(tmp_path / "env.db"), "SENTINEL_SESSION_KEY": "test-key"}
    settings = load_settings(config_path=path, root=tmp_path, env=env)
    assert settings.paths.database == tmp_path / "env.db"
    assert settings.api.session_key == "test-key"
    without_env = load_settings(config_path=path, root=tmp_path, env={})
    assert without_env.paths.database == tmp_path / "from-file.db"


def test_config_path_read_from_environment(tmp_path: Path) -> None:
    path = _write(tmp_path, "[api]\nport = 7777\n")
    settings = load_settings(root=tmp_path, env={"SENTINEL_CONFIG": str(path)})
    assert settings.api.port == 7777


def test_relative_and_home_paths_are_anchored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    path = _write(
        tmp_path,
        '[paths]\ndatabase = "data/sentinel.db"\nauth_log = "~/logs/auth.log"\n'
        'log_dir = "my-logs"\n',
    )
    settings = load_settings(config_path=path, root=tmp_path, env={})
    assert settings.paths.database == tmp_path / "data" / "sentinel.db"
    assert settings.paths.auth_log == home / "logs" / "auth.log"
    assert settings.paths.log_dir == tmp_path / "my-logs"


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("api", "port", 0),
        ("api", "port", 70000),
        ("engine", "collect_interval_seconds", 0),
        ("engine", "retention_interval_hours", -1),
        ("collectors", "max_process_events_per_run", -1),
    ],
)
def test_numeric_ranges_validated(tmp_path: Path, section: str, key: str, value: int) -> None:
    path = _write(tmp_path, f"[{section}]\n{key} = {value}\n")
    with pytest.raises(ValueError, match=key):
        load_settings(config_path=path, root=tmp_path, env={})


def test_enum_and_type_validation(tmp_path: Path) -> None:
    path = _write(tmp_path, '[collectors]\nauth_source = "nope"\n')
    with pytest.raises(ValueError, match="auth_source"):
        load_settings(config_path=path, root=tmp_path, env={})
    path = _write(tmp_path, '[api]\nport = "8000"\n')
    with pytest.raises(ValueError, match="port"):
        load_settings(config_path=path, root=tmp_path, env={})
    path = _write(tmp_path, '[notifications]\nenabled = "yes"\n')
    with pytest.raises(ValueError, match="enabled"):
        load_settings(config_path=path, root=tmp_path, env={})


def test_naive_timezone_validation_and_normalisation(tmp_path: Path) -> None:
    path = _write(tmp_path, '[time]\nnaive_timezone = "utc"\n')
    assert load_settings(config_path=path, root=tmp_path, env={}).time.naive_timezone == "UTC"
    path = _write(tmp_path, '[time]\nnaive_timezone = "Mars"\n')
    with pytest.raises(ValueError, match="naive_timezone"):
        load_settings(config_path=path, root=tmp_path, env={})


def test_session_key_value_never_in_repr(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    settings = load_settings(
        config_path=path, root=tmp_path, env={"SENTINEL_SESSION_KEY": "supersecret-value"}
    )
    assert "supersecret-value" not in repr(settings)
