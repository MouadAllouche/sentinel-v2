"""Password policy and scrypt hashing. Pure: no DB, clock or I/O."""

from __future__ import annotations

import hashlib
import hmac
import secrets

__all__ = [
    "dummy_hash",
    "hash_password",
    "hash_parameters",
    "needs_rehash",
    "new_session_token",
    "validate_password",
    "verify_password",
]

N, R, P = 2**15, 8, 1
_COMMON = frozenset(
    {
        "password123456",
        "123456789012",
        "letmein123456",
        "qwerty1234567",
        "adminpassword1",
        "welcome123456",
        "passwordpassword",
    }
)


def validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    if password.lower() in _COMMON:
        raise ValueError("password is too common")


def hash_password(password: str) -> str:
    """Return ``scrypt$n$r$p$salt$hash`` with hex-encoded salt and key."""
    validate_password(password)
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=N,
        r=R,
        p=P,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    )
    return f"scrypt${N}${R}${P}${salt.hex()}${key.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification against a stored scrypt hash."""
    try:
        scheme, n_text, r_text, p_text, salt_hex, hash_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_text),
            r=int(r_text),
            p=int(p_text),
            dklen=len(expected),
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password("dummy-password-for-timing-1234")


def hash_parameters(encoded: str) -> tuple[int, int, int] | None:
    try:
        scheme, n_text, r_text, p_text, _salt, _key = encoded.split("$")
        if scheme != "scrypt":
            return None
        return int(n_text), int(r_text), int(p_text)
    except (ValueError, TypeError):
        return None


def needs_rehash(encoded: str) -> bool:
    return hash_parameters(encoded) != (N, R, P)


def dummy_hash() -> str:
    """A valid hash used to equalise timing for unknown usernames."""
    return _DUMMY_HASH


def new_session_token() -> str:
    """Return a 256-bit random session token (hex encoded)."""
    return secrets.token_hex(32)
