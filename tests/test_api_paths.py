"""Guard against API paths drifting from the FastAPI router prefix (Phase 18 fix)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_health_api_callers_use_the_api_prefix() -> None:
    """`/health` is the dashboard page; the health API lives at `/api/health`."""
    offenders: list[str] = []
    for path in (ROOT / "web").rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
            continue
        if "node_modules" in path.parts or ".next" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?:GET|POST|PUT|PATCH|DELETE)\(\s*[\"']([^\"']+)[\"']", text):
            route = match.group(1)
            if route == "/health":
                offenders.append(f"{path.relative_to(ROOT)}: {route}")
    assert offenders == []


def test_health_api_docs_use_the_api_prefix() -> None:
    text = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
    assert "GET /health`" not in text
    assert "GET /api/health`" in text
