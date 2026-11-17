"""Fuzz tests: parsers must never raise and must emit only valid events."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from collectors.dpkg import parse_dpkg_line
from collectors.logs import parse_auth_line
from core.events import validate_event

_TEXT = st.one_of(
    st.text(max_size=2000),
    st.just("A" * 10_000),
    st.just("\x00" * 100),
    st.just("Failed password for invalid用户 from 203.0.113.45\x00"),
)


@settings(max_examples=200, deadline=None)
@given(line=_TEXT)
def test_parse_auth_line_never_raises_and_validates(line: str) -> None:
    event = parse_auth_line(line, year=2026)
    if event is not None:
        assert validate_event(event) is True


@settings(max_examples=200, deadline=None)
@given(line=_TEXT)
def test_parse_dpkg_line_never_raises_and_validates(line: str) -> None:
    event = parse_dpkg_line(line)
    if event is not None:
        assert validate_event(event) is True
