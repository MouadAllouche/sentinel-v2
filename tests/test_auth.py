"""Tests for password hashing and auth persistence (Phase 12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.auth import (
    dummy_hash,
    hash_password,
    validate_password,
    verify_password,
)
from storage.auth_repository import (
    create_user,
    get_user_by_name,
    list_users,
    record_failed_login,
    set_password,
    set_user_disabled,
)

PASSWORD = "a-long-test-password"


def test_hash_format_and_verification() -> None:
    encoded = hash_password(PASSWORD)
    assert encoded.startswith("scrypt$32768$8$1$")
    assert verify_password(PASSWORD, encoded) is True
    assert verify_password("wrong-password", encoded) is False
    assert verify_password(PASSWORD, dummy_hash()) is False


def test_password_policy() -> None:
    validate_password(PASSWORD)
    with pytest.raises(ValueError):
        validate_password("short")
    with pytest.raises(ValueError):
        validate_password("password123456")


def test_user_crud_and_lockout(tmp_initialised_db: Path) -> None:
    identifier = create_user("alice", PASSWORD, "admin", tmp_initialised_db)
    user = get_user_by_name("alice", tmp_initialised_db)
    assert user is not None and user["role"] == "admin"
    assert user["password_hash"] != PASSWORD
    assert len(list_users(tmp_initialised_db)) == 1
    set_user_disabled(identifier, True, tmp_initialised_db)
    assert get_user_by_name("alice", tmp_initialised_db)["disabled"] == 1
    set_user_disabled(identifier, False, tmp_initialised_db)
    set_password(identifier, "another-long-password", tmp_initialised_db)
    assert verify_password(
        "another-long-password", get_user_by_name("alice", tmp_initialised_db)["password_hash"]
    )
    record_failed_login("alice", "127.0.0.1", tmp_initialised_db)
    assert get_user_by_name("alice", tmp_initialised_db)["failed_logins"] == 1
