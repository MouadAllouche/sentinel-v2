"""Documentation accuracy checks (Phase 18)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/RULES.md",
    "docs/RISK_RULES.md",
    "docs/API.md",
    "docs/SECURITY.md",
    "docs/LIMITATIONS.md",
    "docs/OPERATIONS.md",
    "docs/DEMO.md",
    "docs/DECISIONS.md",
]


def test_all_required_docs_exist() -> None:
    missing = [name for name in DOCS if not (ROOT / name).exists()]
    assert missing == []


def test_every_api_path_is_documented() -> None:
    spec = json.loads((ROOT / "web" / "openapi.json").read_text(encoding="utf-8"))
    text = "\n".join(
        (ROOT / name).read_text(encoding="utf-8") for name in DOCS if (ROOT / name).exists()
    )
    missing = [path for path in spec["paths"] if path not in text]
    assert missing == []


def test_every_seeded_rule_id_is_documented() -> None:
    from core.rules.defaults import DEFAULT_RULES

    text = (ROOT / "docs" / "RULES.md").read_text(encoding="utf-8")
    missing = [rule["id"] for rule in DEFAULT_RULES if rule["id"] not in text]
    assert missing == []
