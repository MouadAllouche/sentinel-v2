---
name: sentinel-correlation-incidents
description: How Sentinel links events into incidents - link kinds and strengths, anchors, components, determinism, merge/extend/reopen, timeline, status workflow, notes, MITRE tagging. Load when writing or testing correlation, incidents, timeline, or incident-related API/UI.
---

# Correlation and incidents

- **Links** (each with `relation_reason` text and `strength`): strong = shared `source_ip`, shared username on auth events, rule evidence (`rule_triggered` ↔ its evidence events), same rule group key; weak = login→follow-up by same user, host-level event after existing evidence (time proximity), shared process. Weak links can extend a component but never create one.
- **Anchors** (a component needs ≥1): failed_login, invalid_user, rule_triggered, config_drift (≥ medium), anomaly, suspicious_process, user_created, group_member_added. Never create incidents from plain network/process/system/package events or a lone successful login. Incidents exist only if a finding with `create_incident=true` or an anchor ≥ medium is present.
- Do not link on `username=root` alone; honor `ignore_ips`; allowlist-suppressed events are excluded.
- Windows: default 15 min; component span capped (default 24 h) and split beyond.
- **Determinism**: input-order independent; identity = earliest anchor event hash (`correlation_key`). Property-test: shuffle input → identical plan; run twice → no changes.
- **Plan actions**: Create / Extend / Merge (older keeps id; absorbed → `status=merged`, `merged_into`) / reopen closed incidents as new after `reopen_after_hours`.
- **Timeline**: `observed` entries (from events) vs `inferred` entries (Sentinel statements with cited evidence); each entry shows relation reason and strength to the previous one.
- **Workflow**: open → investigating → resolved | false_positive | closed (+ system `merged`); enforced transition matrix; reason required for resolved/false_positive; append-only notes; status history; all audited. False positive never deletes evidence; it may offer an allowlist entry.
- **MITRE**: static table; union over contributing rules; labelled "indicative mapping"; verify IDs against attack.mitre.org.
- **Always include caveats**: grouping is by shared attributes and time, not proof of a single actor.
