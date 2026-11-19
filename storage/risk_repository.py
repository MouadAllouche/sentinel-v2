"""Risk assessment persistence and human-readable explanations (Phase 10)."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

from core.risk_scoring import RiskAssessment
from core.timeutil import utc_now
from storage.database import get_connection

__all__ = [
    "apply_assessment",
    "explain_score",
    "get_assessment",
    "list_severity_changes",
    "record_severity_change",
    "upsert_risk_assessment",
]


def upsert_risk_assessment(
    target_type: str,
    target_id: int,
    assessment: dict[str, Any] | RiskAssessment,
    db_path: str | Path | None = None,
) -> None:
    data = (
        assessment
        if isinstance(assessment, dict)
        else {
            "score": assessment.score,
            "raw_score": assessment.raw_score,
            "capped": assessment.capped,
            "severity": assessment.severity,
            "reasons": assessment.reasons,
            "computed_at": assessment.computed_at,
        }
    )
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO risk_assessments(target_type, target_id, score, severity, "
            "reasons_json, computed_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(target_type, target_id) DO UPDATE SET score = excluded.score, "
            "severity = excluded.severity, reasons_json = excluded.reasons_json, "
            "computed_at = excluded.computed_at",
            (
                target_type,
                target_id,
                data["score"],
                data["severity"],
                json.dumps(data["reasons"], sort_keys=True, default=str),
                data.get("computed_at") or utc_now().isoformat(),
            ),
        )


def apply_assessment(
    target_type: str,
    target_id: int,
    assessment: dict[str, Any] | RiskAssessment,
    *,
    incident_update: dict[str, Any] | None = None,
    severity_change: tuple[str | None, str] | None = None,
    db_path: str | Path | None = None,
) -> None:
    """Persist assessment, incident propagation and change record in ONE transaction."""
    data = (
        assessment
        if isinstance(assessment, dict)
        else {
            "score": assessment.score,
            "raw_score": assessment.raw_score,
            "capped": assessment.capped,
            "severity": assessment.severity,
            "reasons": assessment.reasons,
            "computed_at": assessment.computed_at,
        }
    )
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO risk_assessments(target_type, target_id, score, severity, "
            "reasons_json, computed_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(target_type, target_id) DO UPDATE SET score = excluded.score, "
            "severity = excluded.severity, reasons_json = excluded.reasons_json, "
            "computed_at = excluded.computed_at",
            (
                target_type,
                target_id,
                data["score"],
                data["severity"],
                json.dumps(data["reasons"], sort_keys=True, default=str),
                data.get("computed_at") or utc_now().isoformat(),
            ),
        )
        if incident_update is not None:
            connection.execute(
                "UPDATE incidents SET risk_score = ?, severity = ?, updated_at = ? WHERE id = ?",
                (
                    incident_update["score"],
                    incident_update["severity"],
                    incident_update["computed_at"],
                    target_id,
                ),
            )
        if severity_change is not None:
            connection.execute(
                "INSERT INTO risk_changes(target_type, target_id, from_severity, to_severity, at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    target_type,
                    target_id,
                    severity_change[0],
                    severity_change[1],
                    utc_now().isoformat(),
                ),
            )


def get_assessment(
    target_type: str, target_id: int, db_path: str | Path | None = None
) -> dict[str, Any] | None:
    with closing(get_connection(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM risk_assessments WHERE target_type = ? AND target_id = ?",
            (target_type, target_id),
        ).fetchone()
    if row is None:
        return None
    return {
        "score": row["score"],
        "severity": row["severity"],
        "reasons": json.loads(row["reasons_json"]),
        "computed_at": row["computed_at"],
    }


def explain_score(target_type: str, target_id: int, db_path: str | Path | None = None) -> list[str]:
    assessment = get_assessment(target_type, target_id, db_path)
    if assessment is None:
        return []
    lines: list[str] = []
    for reason in assessment["reasons"]:
        if reason.get("kind") == "rule":
            lines.append(
                f"+{reason.get('points')} {reason.get('tier_label')} — "
                f"{reason.get('explanation')} (rule {reason.get('rule_id')})"
            )
        elif reason.get("kind") == "meta":
            lines.append(
                f"+{reason.get('points')} {reason.get('rule_name')} — "
                f"{reason.get('explanation')} (meta rule)"
            )
        else:
            lines.append(str(reason.get("explanation", "")))
    return [line for line in lines if line]


def record_severity_change(
    target_type: str,
    target_id: int,
    from_severity: str | None,
    to_severity: str,
    db_path: str | Path | None = None,
) -> None:
    with closing(get_connection(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO risk_changes(target_type, target_id, from_severity, to_severity, at) "
            "VALUES (?, ?, ?, ?, ?)",
            (target_type, target_id, from_severity, to_severity, utc_now().isoformat()),
        )


def list_severity_changes(
    target_id: int, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    with closing(get_connection(db_path)) as connection:
        rows = connection.execute(
            "SELECT * FROM risk_changes WHERE target_id = ? ORDER BY id", (target_id,)
        ).fetchall()
    return [dict(row) for row in rows]
