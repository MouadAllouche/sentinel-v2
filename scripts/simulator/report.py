"""Deterministic console, Markdown and JSON reports for the simulator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.simulator.evaluate import aggregate, evaluate
from scripts.simulator.runner import ScenarioResult

DISCLAIMER = "Synthetic scenarios test rule behaviour, not real-world detection performance"
NOT_MODELLED = (
    "Not modelled: encrypted traffic, memory-only malware, kernel rootkits, zero-days, "
    "and anything outside logs, connections, processes and files."
)


def _payload(results: list[ScenarioResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        evaluation = evaluate(result)
        rows.append(
            {
                "scenario_id": result.scenario_id,
                "seed": result.seed,
                "outcome": evaluation.outcome,
                "detected": evaluation.detected,
                "matched_rules": evaluation.matched_rules,
                "highest_severity": evaluation.highest_severity,
                "incident_id": evaluation.incident_id,
                "score": evaluation.score,
                "time_to_detect": evaluation.time_to_detect,
                "false_positives": evaluation.false_positives,
                "suppressed_events": result.suppressed_count,
                "findings": [
                    {
                        key: item.get(key)
                        for key in (
                            "rule_id",
                            "tier_label",
                            "severity",
                            "window_start",
                            "window_end",
                        )
                    }
                    for item in result.findings
                ],
                "incidents": [
                    {key: item.get(key) for key in ("id", "severity", "score", "title")}
                    for item in result.incidents
                ],
                "anomalies": [item.get("description") for item in result.anomalies],
                "explanation": result.explanation,
                "note": evaluation.note,
            }
        )
    return rows


def render_json(results: list[ScenarioResult]) -> str:
    return (
        json.dumps(
            {
                "disclaimer": DISCLAIMER,
                "not_modelled": NOT_MODELLED,
                "summary": aggregate([evaluate(item) for item in results]),
                "scenarios": _payload(results),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def render_table(results: list[ScenarioResult], summary: dict[str, Any] | None = None) -> str:
    summary = summary or aggregate([evaluate(item) for item in results])
    lines = [
        f"Synthetic scenarios: detected {summary['detected']} of {summary['scenarios']} scenarios",
        DISCLAIMER,
        "",
        f"{'scenario':32} {'outcome':22} {'severity':8} {'ttd(s)':>8} rules",
        "-" * 92,
    ]
    for result in results:
        item = evaluate(result)
        ttd = "—" if item.time_to_detect is None else f"{item.time_to_detect:.0f}"
        lines.append(
            f"{item.scenario_id:32} {item.outcome:22} {item.highest_severity:8} "
            f"{ttd:>8} {','.join(item.matched_rules)}"
        )
    lines += [
        "",
        f"attack detection rate: {summary['detection_rate']:.0%}",
        f"benign false positives: {summary['false_positive_count']}",
        f"severity distribution: {json.dumps(summary['severity_distribution'], sort_keys=True)}",
        "MITRE coverage (scenarios/detected): "
        + ", ".join(
            f"{key} {value['detected']}/{value['scenarios']}"
            for key, value in summary["mitre_coverage"].items()
        ),
        NOT_MODELLED,
    ]
    return "\n".join(lines) + "\n"


def render_markdown(results: list[ScenarioResult], summary: dict[str, Any]) -> str:
    lines = [
        "# Threat simulator detection report",
        "",
        DISCLAIMER,
        "",
        f"Detected {summary['detected']} of {summary['scenarios']} simulated scenarios.",
        "",
        "## Summary",
        "",
        f"- Attack detection rate: {summary['detection_rate']:.0%}",
        f"- False positives on benign scenarios: {summary['false_positive_count']}",
        f"- Median time to detect: {summary['median_time_to_detect']} simulated seconds",
        f"- Severity distribution: {json.dumps(summary['severity_distribution'], sort_keys=True)}",
        "",
        "## Outcome matrix",
        "",
        "| Scenario | Outcome | Severity | Rules | Time to detect (s) |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        item = evaluate(result)
        ttd = "—" if item.time_to_detect is None else f"{item.time_to_detect:.0f}"
        lines.append(
            f"| {item.scenario_id} | {item.outcome} | {item.highest_severity} | "
            f"{', '.join(item.matched_rules) or '—'} | {ttd} |"
        )
    lines += [
        "",
        "## MITRE technique coverage",
        "",
        "| Technique | Scenarios | Detected |",
        "|---|---:|---:|",
    ]
    for technique, row in summary["mitre_coverage"].items():
        lines.append(f"| {technique} | {row['scenarios']} | {row['detected']} |")
    lines += ["", "## Per-scenario explanations", ""]
    for result in results:
        item = evaluate(result)
        lines += [
            f"### {result.scenario_id} — {item.outcome}",
            "",
            result.explanation,
            "",
            f"Note: {item.note}",
            "",
        ]
    evaluations = [evaluate(item) for item in results]
    blind = [item for item in evaluations if item.outcome in {"KNOWN_BLIND_SPOT", "FALSE_NEGATIVE"}]
    lines += ["## Blind spots and misses", ""]
    if blind:
        for item in blind:
            lines.append(f"- **{item.scenario_id}** ({item.outcome}): {item.note}")
    else:
        lines.append("- None in this run.")
    lines += ["", NOT_MODELLED, ""]
    return "\n".join(lines)


def write_report(
    results: list[ScenarioResult],
    *,
    fmt: str,
    out_dir: str | Path,
) -> Path:
    from scripts.simulator.runner import safe_workdir

    target = safe_workdir(out_dir)
    summary = aggregate([evaluate(item) for item in results])
    if fmt == "json":
        path = target / "report.json"
        path.write_text(render_json(results), encoding="utf-8")
    elif fmt == "md":
        path = target / "report.md"
        path.write_text(render_markdown(results, summary), encoding="utf-8")
    elif fmt == "table":
        path = target / "report.txt"
        path.write_text(render_table(results, summary), encoding="utf-8")
    else:
        raise ValueError(f"unknown report format: {fmt}")
    return path
