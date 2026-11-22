"""Tests for Phase 20 metrics math, determinism and report consistency."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.metrics import aggregate_detection, classification_counts

ROOT = Path(__file__).resolve().parents[1]


def _outcomes(values: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "outcome": value,
            "category": "attack" if value in {"TRUE_POSITIVE", "FALSE_NEGATIVE"} else "benign",
        }
        for value in values
    ]


def test_classification_counts_and_perfect_case() -> None:
    counts = classification_counts(
        _outcomes(["TRUE_POSITIVE", "TRUE_POSITIVE", "TRUE_NEGATIVE", "TRUE_NEGATIVE"])
    )
    assert (counts["tp"], counts["fn"], counts["tn"], counts["fp"]) == (2, 0, 2, 0)
    assert counts["precision"] == 1.0
    assert counts["recall"] == 1.0
    assert counts["f1"] == 1.0


def test_classification_counts_mixed_case() -> None:
    counts = classification_counts(
        _outcomes(
            [
                "TRUE_POSITIVE",
                "FALSE_NEGATIVE",
                "TRUE_NEGATIVE",
                "FALSE_POSITIVE",
            ]
        )
    )
    assert (counts["tp"], counts["fn"], counts["tn"], counts["fp"]) == (1, 1, 1, 1)
    assert counts["precision"] == 0.5
    assert counts["recall"] == 0.5
    assert counts["f1"] == 0.5


@pytest.mark.parametrize(
    ("values", "precision", "recall", "f1"),
    [
        ([], None, None, None),
        (["TRUE_NEGATIVE"], None, None, None),  # no positives predicted and none actual
        (["FALSE_POSITIVE"], 0.0, None, None),  # no actual positives
        (["FALSE_NEGATIVE"], None, 0.0, None),  # no predicted positives
    ],
)
def test_classification_zero_denominators(
    values: list[str], precision: float | None, recall: float | None, f1: float | None
) -> None:
    counts = classification_counts(_outcomes(values))
    assert counts["precision"] == precision
    assert counts["recall"] == recall
    assert counts["f1"] == f1


def test_aggregate_detection_reports_range_and_identity() -> None:
    first = {
        "tp": 8,
        "fn": 2,
        "tn": 3,
        "fp": 0,
        "precision": 1.0,
        "recall": 0.8,
        "f1": 0.888888888888889,
        "benign_fp_count": 0,
        "outcomes": {"ssh": "TRUE_POSITIVE"},
    }
    second = {
        **first,
        "tp": 7,
        "fn": 3,
        "recall": 0.7,
        "f1": 0.8235294117647058,
        "outcomes": {"ssh": "FALSE_NEGATIVE"},
    }
    result = aggregate_detection([first, second])
    assert result["seeds"] == 2
    assert result["identical_outcomes"] is False
    assert result["tp"]["mean"] == 7.5
    assert result["tp"]["min"] == 7
    assert result["tp"]["max"] == 8
    assert result["precision"]["min"] == 1.0
    assert result["recall"]["min"] == 0.7


def test_detection_is_deterministic_for_a_fixed_seed(sim_workdir: Path) -> None:
    from scripts.metrics import collect_detection

    ids = ["ssh-bruteforce-single-ip", "benign-admin-day"]
    first = collect_detection(seeds=[7], workdir=sim_workdir / "a", scenarios=ids)
    second = collect_detection(seeds=[7], workdir=sim_workdir / "b", scenarios=ids)
    assert first == second


def test_metrics_json_matches_documented_numbers() -> None:
    data = json.loads((ROOT / "metrics.json").read_text(encoding="utf-8"))
    text = (ROOT / "docs" / "METRICS.md").read_text(encoding="utf-8")
    assert "## Methodology" in text
    assert "## Slide-ready numbers" in text
    for key in (
        "slide_ready",
        "methodology",
        "detection",
        "timing",
        "prioritisation",
        "baseline_comparison",
        "performance",
    ):
        assert key in data
    for item in data["slide_ready"]:
        assert item["number"] in text, item
