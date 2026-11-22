"""Measured evaluation metrics for the Phase 20 simulator (no estimates)."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from scripts.simulator.evaluate import evaluate
from scripts.simulator.runner import run_scenario
from scripts.simulator.scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
METRICS_JSON = ROOT / "metrics.json"
METRICS_DOC = ROOT / "docs" / "METRICS.md"
NAIVE_RULES = ROOT / "sample_data" / "naive_baseline_rules.json"

_METRIC_KEYS = ("tp", "fn", "tn", "fp", "precision", "recall", "f1", "benign_fp_count")


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def classification_counts(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute scenario-level confusion counts and derived scores.

    Zero denominators produce ``None``, never an invented zero.
    """
    tp = sum(item["outcome"] == "TRUE_POSITIVE" for item in evaluations)
    fn = sum(item["outcome"] == "FALSE_NEGATIVE" for item in evaluations)
    tn = sum(item["outcome"] == "TRUE_NEGATIVE" for item in evaluations)
    fp = sum(item["outcome"] == "FALSE_POSITIVE" for item in evaluations)
    benign_fp = sum(
        item["outcome"] == "FALSE_POSITIVE" and item.get("category") == "benign"
        for item in evaluations
    )
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    return {
        "tp": tp,
        "fn": fn,
        "tn": tn,
        "fp": fp,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "benign_fp_count": benign_fp,
        "outcomes": {
            str(item.get("scenario_id", index)): item["outcome"]
            for index, item in enumerate(evaluations)
        },
    }


def aggregate_detection(per_seed: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean/min/max of each score across seeds, plus outcome identity."""
    result: dict[str, Any] = {"seeds": len(per_seed)}
    for key in _METRIC_KEYS:
        values = [item[key] for item in per_seed if item[key] is not None]
        result[key] = {
            "mean": statistics.fmean(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    outcomes = [item.get("outcomes", {}) for item in per_seed]
    result["identical_outcomes"] = bool(outcomes) and all(item == outcomes[0] for item in outcomes)
    return result


def _details(result: Any, evaluation: Any) -> dict[str, Any]:
    from storage.risk_repository import get_assessment

    reasons = 0
    score = 0
    for incident in result.incidents:
        assessment = get_assessment("incident", int(incident["id"]), db_path=result.database)
        if assessment:
            reasons += sum(
                1 for item in assessment.get("reasons", []) if int(item.get("points") or 0) > 0
            )
            score = max(score, int(assessment.get("score") or 0))
        else:
            score = max(score, int(incident.get("risk_score") or incident.get("score") or 0))
    return {
        "outcome": evaluation.outcome,
        "category": evaluation.category,
        "severity": evaluation.highest_severity,
        "score": score,
        "reasons": reasons,
        "time_to_detect": evaluation.time_to_detect,
        "matched_rules": evaluation.matched_rules,
        "events": len(result.events),
        "findings": len(result.findings),
        "incidents": len(result.incidents),
        "anomalies": len(result.anomalies),
        "drift_events": len(result.drift_events),
    }


def collect_detection(
    *,
    seeds: list[int],
    workdir: Path,
    scenarios: list[str] | None = None,
    overrides: list[dict[str, Any]] | None = None,
    replace_rules: bool = False,
) -> dict[str, Any]:
    """Run every scenario for every seed against real storage/pipeline code."""
    ids = scenarios or [scenario.id for scenario in SCENARIOS]
    per_seed: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    for seed in seeds:
        evaluations: list[dict[str, Any]] = []
        for scenario_id in ids:
            result = run_scenario(
                scenario_id,
                seed=seed,
                workdir=workdir / f"seed-{seed}",
                overrides=overrides,
                replace_rules=replace_rules,
            )
            evaluation = evaluate(result)
            evaluations.append(
                {
                    "scenario_id": scenario_id,
                    "category": evaluation.category,
                    "outcome": evaluation.outcome,
                }
            )
            details[f"{seed}:{scenario_id}"] = _details(result, evaluation)
        per_seed.append(classification_counts(evaluations))
    return {
        "seeds": seeds,
        "scenarios": ids,
        "per_seed": per_seed,
        "aggregate": aggregate_detection(per_seed),
        "details": details,
    }


def _diagnosis(detail: dict[str, Any]) -> str:
    if detail["events"] == 0:
        return "simulator realism: no events generated"
    if detail["findings"] == 0 and detail["anomalies"] == 0:
        return "rule gap or threshold: no finding fired on stored events"
    if detail["incidents"] == 0:
        return "correlation: findings did not form an incident"
    return "prioritisation: incident severity below the pre-registered expectation"


def collect_methodology(
    detection: dict[str, Any], *, seeds: list[int], builtin_rules: list[dict[str, Any]]
) -> dict[str, Any]:
    kinds = {"attack", "benign", "evasion", "combined"}
    categories = {kind: sum(scenario.category == kind for scenario in SCENARIOS) for kind in kinds}
    techniques = sorted({tag for scenario in SCENARIOS for tag in scenario.mitre})
    matched: set[str] = set()
    for detail in detection["details"].values():
        matched.update(detail["matched_rules"])
    rule_kind = {str(rule["id"]): str(rule["kind"]) for rule in builtin_rules}
    exercised = sorted(matched & set(rule_kind))
    return {
        "total_scenarios": len(SCENARIOS),
        "categories": categories,
        "distinct_mitre_techniques": len(techniques),
        "mitre_techniques": techniques,
        "builtin_rules_total": len(builtin_rules),
        "builtin_rules_exercised": len(exercised),
        "rule_kinds_exercised_count": len({rule_kind[identifier] for identifier in exercised}),
        "rule_kinds_exercised": sorted({rule_kind[identifier] for identifier in exercised}),
        "seeds_run": len(seeds),
        "seeds": seeds,
    }


def collect_timing(detection: dict[str, Any], *, seeds: list[int]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for scenario in SCENARIOS:
        if scenario.category != "attack":
            continue
        values = [detection["details"][f"{seed}:{scenario.id}"]["time_to_detect"] for seed in seeds]
        present = [float(value) for value in values if value is not None]
        result[scenario.id] = {
            "detections": len(present),
            "runs": len(values),
            "median": statistics.median(present) if present else None,
            "min": min(present) if present else None,
            "max": max(present) if present else None,
        }
    return result


def collect_prioritisation(detection: dict[str, Any], *, baseline_seed: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for scenario in SCENARIOS:
        if scenario.category != "attack":
            continue
        detail = detection["details"][f"{baseline_seed}:{scenario.id}"]
        result[scenario.id] = {
            "severity": detail["severity"],
            "score": detail["score"],
            "rule_reasons": detail["reasons"],
        }
    return result


def _label(value: str) -> str:
    return {
        "TRUE_POSITIVE": "detected",
        "FALSE_NEGATIVE": "missed",
        "TRUE_NEGATIVE": "not detected (expected)",
        "FALSE_POSITIVE": "false positive",
        "KNOWN_BLIND_SPOT": "missed (known blind spot)",
        "UNEXPECTED_DETECTION": "detected (unexpected)",
    }.get(value, value)


def collect_baseline(
    default: dict[str, Any], naive: dict[str, Any], *, seed: int
) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    totals = {
        "sentinel_detected": 0,
        "sentinel_missed": 0,
        "sentinel_false_positive": 0,
        "baseline_detected": 0,
        "baseline_missed": 0,
        "baseline_false_positive": 0,
    }
    for scenario in SCENARIOS:
        d = default["details"][f"{seed}:{scenario.id}"]["outcome"]
        n = naive["details"][f"{seed}:{scenario.id}"]["outcome"]
        rows[scenario.id] = {
            "category": scenario.category,
            "sentinel_default": _label(d),
            "naive_baseline": _label(n),
        }
        for prefix, value in (("sentinel", d), ("baseline", n)):
            if value == "TRUE_POSITIVE":
                totals[f"{prefix}_detected"] += 1
            elif value == "FALSE_NEGATIVE":
                totals[f"{prefix}_missed"] += 1
            elif value == "FALSE_POSITIVE":
                totals[f"{prefix}_false_positive"] += 1
    return {"seed": seed, "rows": rows, "totals": totals}


def _format(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(data: dict[str, Any]) -> str:
    method = data["methodology"]
    aggregate = data["detection"]["aggregate"]
    performance = data["performance"]
    lines = [
        "# Sentinel simulator evaluation metrics",
        "",
        "All numbers below come from measured runs recorded in `metrics.json`. "
        "No value is estimated or tuned.",
        "",
        "## Methodology",
        "",
        f"- Total simulated scenarios: {method['total_scenarios']}",
        f"- Attack: {method['categories']['attack']}; benign: {method['categories']['benign']}; "
        f"evasion: {method['categories']['evasion']}; combined: {method['categories']['combined']}",
        f"- Distinct MITRE techniques covered: {method['distinct_mitre_techniques']}",
        f"- Built-in rules: {method['builtin_rules_total']}; exercised: "
        f"{method['builtin_rules_exercised']} across "
        f"{method['rule_kinds_exercised_count']} rule kinds "
        f"({', '.join(method['rule_kinds_exercised'])})",
        f"- Seeds run: {method['seeds_run']} ({method['seeds'][0]}–{method['seeds'][-1]})",
        f"- Baseline comparison seed: {data['baseline_comparison']['seed']}",
        "",
        "## Results",
        "",
        "Scenario-level counts per seed, then mean/min/max across seeds:",
        "",
        "| Metric | Mean | Min | Max |",
        "|---|---|---|---|",
    ]
    for key in ("tp", "fn", "tn", "fp", "precision", "recall", "f1", "benign_fp_count"):
        item = aggregate[key]
        lines.append(
            f"| {key} | {_format(item['mean'])} | {_format(item['min'])} | {_format(item['max'])} |"
        )
    lines += [
        "",
        f"Outcomes identical across seeds: {aggregate['identical_outcomes']}",
        "False positives on benign scenarios (per seed): mean "
        f"{_format(aggregate['benign_fp_count']['mean'])}, "
        f"min {_format(aggregate['benign_fp_count']['min'])}, "
        f"max {_format(aggregate['benign_fp_count']['max'])}",
        "",
        "Missed or false-positive scenarios (seed "
        f"{data['baseline_comparison']['seed']}), with diagnosis:",
        "",
    ]
    misses = data.get("issues", [])
    if misses:
        for item in misses:
            lines.append(f"- **{item['scenario']}** ({item['outcome']}): {item['diagnosis']}")
    else:
        lines.append("- None.")
    lines += [
        "",
        "## Time to detect",
        "",
        "Simulated seconds from the first malicious event to the first matching finding.",
        "",
        "| Attack scenario | Detections | Median | Min | Max |",
        "|---|---:|---:|---:|---:|",
    ]
    for sid, item in data["timing"].items():
        lines.append(
            f"| {sid} | {item['detections']}/{item['runs']} | {_format(item['median'])} | "
            f"{_format(item['min'])} | {_format(item['max'])} |"
        )
    lines += [
        "",
        "## Prioritisation",
        "",
        f"Final severity, risk score and contributing rule reasons at seed "
        f"{data['baseline_comparison']['seed']}.",
        "",
        "| Attack scenario | Severity | Score | Rule reasons |",
        "|---|---|---:|---:|",
    ]
    for sid, item in data["prioritisation"].items():
        lines.append(f"| {sid} | {item['severity']} | {item['score']} | {item['rule_reasons']} |")
    lines += [
        "",
        "## Comparison with a naive baseline",
        "",
        "The naive baseline is a **simple reference rule set**, not a real product: one rule, "
        '"5 or more failed logins from one IP in 10 minutes → alert". '
        f"Seed {data['baseline_comparison']['seed']}.",
        "",
        "| Scenario | Category | Sentinel default | Naive baseline |",
        "|---|---|---|---|",
    ]
    for sid, item in data["baseline_comparison"]["rows"].items():
        lines.append(
            f"| {sid} | {item['category']} | {item['sentinel_default']} | "
            f"{item['naive_baseline']} |"
        )
    totals = data["baseline_comparison"]["totals"]
    lines += [
        "",
        f"Totals — Sentinel default: detected {totals['sentinel_detected']}, "
        f"missed {totals['sentinel_missed']}, false positives {totals['sentinel_false_positive']}. "
        f"Naive baseline: detected {totals['baseline_detected']}, "
        f"missed {totals['baseline_missed']}, false positives {totals['baseline_false_positive']}.",
        "",
    ]
    lines += [
        "## Performance",
        "",
        f"Machine: {performance['environment']['machine']}",
        f"Python: {performance['environment']['python']}",
        f"CPU: {performance['environment']['cpu']}",
        f"Memory: {performance['environment']['memory']}",
        "",
        "| Measurement | Value |",
        "|---|---|",
    ]
    for key, value in performance["measurements"].items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## Limitations",
        "",
        "- Synthetic scenarios test rule behaviour, not real-world detection performance.",
        "- The simulator models logs, connections, processes and files only; it does not model "
        "encrypted traffic, memory-only malware, kernel rootkits, zero-days, or a real adversary.",
        "- Two red-team scenarios are false negatives with pre-registered expectations; "
        "they are reported, not tuned away.",
        "- Performance figures are for this machine and this SQLite database, "
        "not a capacity guarantee.",
        "",
        "## Slide-ready numbers",
        "",
    ]
    for item in data["slide_ready"]:
        lines.append(f"- **{item['number']}** — {item['meaning']}")
    return "\n".join(lines) + "\n"


def build_metrics(
    *,
    seeds: list[int] | None = None,
    workdir: Path | None = None,
    run_performance: bool = True,
) -> dict[str, Any]:
    from core.rules.defaults import DEFAULT_RULES

    seeds = seeds or list(range(1, 21))
    workdir = workdir or ROOT / "sim_workdir" / "metrics"
    default = collect_detection(seeds=seeds, workdir=workdir / "default")
    naive_rules = json.loads(NAIVE_RULES.read_text(encoding="utf-8"))
    naive = collect_detection(
        seeds=[seeds[0]], workdir=workdir / "naive", overrides=naive_rules, replace_rules=True
    )
    methodology = collect_methodology(default, seeds=seeds, builtin_rules=DEFAULT_RULES)
    aggregate = default["aggregate"]
    issues = []
    for key, detail in default["details"].items():
        seed_text, scenario = key.split(":", 1)
        if int(seed_text) != seeds[0]:
            continue
        if detail["outcome"] in {"FALSE_NEGATIVE", "FALSE_POSITIVE", "UNEXPECTED_DETECTION"}:
            issues.append(
                {
                    "scenario": scenario,
                    "outcome": detail["outcome"],
                    "diagnosis": _diagnosis(detail),
                }
            )
    issues.sort(key=lambda item: item["scenario"])
    data: dict[str, Any] = {
        "methodology": methodology,
        "detection": {"aggregate": aggregate, "per_seed": default["per_seed"]},
        "timing": collect_timing(default, seeds=seeds),
        "prioritisation": collect_prioritisation(default, baseline_seed=seeds[0]),
        "baseline_comparison": collect_baseline(default, naive, seed=seeds[0]),
        "issues": issues,
        "performance": {},
    }
    if run_performance:
        from scripts.benchmark import run_benchmarks

        data["performance"] = run_benchmarks(workdir / "benchmark")
    data["slide_ready"] = _slide_ready(data)
    METRICS_JSON.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    METRICS_DOC.write_text(render_markdown(data), encoding="utf-8")
    return data


def _slide_ready(data: dict[str, Any]) -> list[dict[str, str]]:
    aggregate = data["detection"]["aggregate"]
    method = data["methodology"]
    totals = data["baseline_comparison"]["totals"]
    performance = data["performance"].get("measurements", {})
    items = [
        {"number": str(method["total_scenarios"]), "meaning": "synthetic scenarios measured"},
        {
            "number": str(method["seeds_run"]),
            "meaning": "independent seeds run across every scenario",
        },
        {
            "number": str(method["distinct_mitre_techniques"]),
            "meaning": "distinct MITRE techniques covered",
        },
        {
            "number": _format(aggregate["precision"]["mean"]),
            "meaning": "mean precision across seeds",
        },
        {"number": _format(aggregate["recall"]["mean"]), "meaning": "mean recall across seeds"},
        {"number": _format(aggregate["f1"]["mean"]), "meaning": "mean F1 across seeds"},
        {
            "number": _format(aggregate["benign_fp_count"]["mean"]),
            "meaning": "mean false positives on benign scenarios per seed",
        },
        {
            "number": str(totals["sentinel_detected"]),
            "meaning": "scenarios detected by Sentinel defaults at the baseline seed",
        },
        {
            "number": str(totals["baseline_detected"]),
            "meaning": "scenarios detected by the one-rule naive reference at the baseline seed",
        },
    ]
    for key, meaning in (
        ("ingestion_events_per_second", "measured ingestion rate on this machine"),
        ("rule_evaluation_200k_seconds", "measured rule evaluation time over 200,000 events"),
        ("api_events_median_ms", "median /api/events latency over 100 calls"),
        ("api_incidents_median_ms", "median /api/incidents latency over 100 calls"),
        ("database_bytes_per_100k_events", "SQLite database size per 100,000 events"),
    ):
        if key in performance:
            items.append({"number": str(performance[key]), "meaning": meaning})
    return items
