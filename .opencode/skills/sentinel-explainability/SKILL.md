---
name: sentinel-explainability
description: How Sentinel words and structures explanations - facts vs inference, grouping reasons, anomaly text, drift descriptions, rule findings, risk reasons, caveats. Load when writing any user-facing explanation text, API explanation payloads, timeline/score reasons, notifications, exports or dashboard explanation components.
---

# Explainability

## Facts vs inference
- **Observed**: taken directly from stored events. **Inferred**: grouping, suspicion, risk, anomalies. Carry `kind: "observed"|"inferred"` in data; show `Observed`/`Inferred` badges in the UI.
- Language: "possible", "suspicious", "consistent with", "unusual". Never "attack confirmed" or "compromised" without explicit evidence. An anomaly is unusual, not necessarily malicious.

## Required explanation shapes
- **Finding**: `"20 failed_login/invalid_user events from source_ip=203.0.113.45 within 10 minutes (threshold: ≥20 in 10 min → high). First 10:00:03, last 10:06:20."`
- **Link**: `"Same source IP 203.0.113.45; 3m 12s after the previous event"`; weak: `"Weak: config_drift 4m after sudo_command by admin; no shared IP or user, time proximity only"`.
- **Anomaly**: metric, subject, observed, baseline mean/std/samples/window, how far above (`20.9 standard deviations`), and the caveat. Immature baseline → `insufficient_baseline`, never "normal".
- **Drift**: exact: `"/etc/ssh/sshd_config permissions changed from 0644 to 0777"`; never show contents; keys as fingerprints.
- **Risk reasons**: `[{rule_id, rule_name, tier_label, points, severity, explanation, evidence_event_ids}]` + summary `{raw_score, score, capped, severity_basis}`; sum of reason points == raw_score (tested). Show which of "score band" or "rule floor" set the severity.
- **Severity source** on events: `default`, `override:<id>`, `rule:<id>`, `fallback`; UI explains it.

## Always present
A caveat banner on incidents: grouping is by shared attributes and time proximity, not proof of a single actor. Weak links are listed explicitly. Allowlisted evidence is visible and labelled.

## Style
Plain language, short sentences, concrete numbers and times (UTC with relative gap), no jargon without a tooltip, no color-only meaning (always text labels).
