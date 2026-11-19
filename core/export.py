"""Incident and event exports. No secrets, contents or command arguments."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

__all__ = ["export_events_csv", "incident_report", "render_incident"]

VERSION = "sentinel-2"
MAX_CSV_ROWS = 100_000


def incident_report(
    incident: dict[str, Any],
    *,
    timeline: list[dict[str, Any]] | None = None,
    reasons: list[dict[str, Any]] | None = None,
    notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "version": VERSION,
        "id": incident.get("id"),
        "title": incident.get("title", ""),
        "severity": incident.get("severity", "low"),
        "score": incident.get("risk_score", 0),
        "summary": incident.get("summary", ""),
        "first_seen": incident.get("first_seen", ""),
        "last_seen": incident.get("last_seen", ""),
        "mitre": incident.get("mitre", []),
        "timeline": timeline or [],
        "reasons": reasons or [],
        "notes": notes or [],
        "caveat": "Grouping is inferred from shared attributes and time proximity, not proof.",
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['title']}",
        f"Generated: {report['generated_at']} — {VERSION}",
        f"Severity: {report['severity']} — Risk score: {report['score']}",
        f"Summary: {report['summary']}",
        "",
        "## Timeline",
    ]
    for entry in report["timeline"]:
        lines.append(
            f"- {entry.get('timestamp')} [{str(entry.get('kind', 'observed')).capitalize()}] "
            f"{entry.get('event_type', '')}: {entry.get('summary', '')}"
        )
    lines.append("")
    lines.append("## Why this score")
    for reason in report["reasons"]:
        lines.append(
            f"- +{reason.get('points', 0)} {reason.get('tier_label', '')} "
            f"({reason.get('rule_id', '')})"
        )
    lines.extend(["", "## MITRE"])
    for item in report["mitre"]:
        lines.append(f"- {item.get('id')} {item.get('name', '')} (indicative mapping)")
    lines.extend(["", "## Notes"])
    for note in report["notes"]:
        lines.append(f"- {note.get('author', '')}: {note.get('body', '')}")
    lines.extend(["", f"Caveat: {report['caveat']}"])
    return "\n".join(lines)


def render_incident(report: dict[str, Any], fmt: str) -> str | bytes:
    if fmt == "json":
        return json.dumps(report, sort_keys=True, default=str)
    if fmt == "md":
        return _markdown(report)
    if fmt == "pdf":
        from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.setPageCompression(0)
        pdf.setTitle(f"Sentinel incident {report['id']}")
        pdf.drawString(50, 800, f"Sentinel incident {report['id']}: {report['title']}")
        pdf.drawString(50, 780, f"Severity {report['severity']} / score {report['score']}")
        text = pdf.beginText(50, 750)
        for line in _markdown(report).splitlines()[:40]:
            text.textLine(line[:100])
        pdf.drawText(text)
        pdf.save()
        return buffer.getvalue()
    raise ValueError(f"unsupported export format: {fmt}")


def export_events_csv(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "description", "source_ip"])
    for row in rows[:MAX_CSV_ROWS]:
        writer.writerow(
            [
                _safe(value)
                for value in (
                    row.get("timestamp", ""),
                    row.get("description", ""),
                    row.get("source_ip", ""),
                )
            ]
        )
    return output.getvalue()


def _safe(value: Any) -> str:
    text = str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text
