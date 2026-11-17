---
name: sentinel-docs-writing
description: Style and accuracy rules for Sentinel's documentation - README, architecture, rules guide, security, limitations, operations, demo, decisions, audit report. Load when writing or updating any file under docs/ or README.md.
---

# Documentation

- Write for an administrator/engineer who has not seen the code. Short sentences, concrete commands, copy-pasteable blocks that were actually run.
- **Accuracy over polish**: every statement must match the code; a test checks that each seeded rule id and each API route is documented. If unsure, say "unverified" and list it in `DECISIONS.md`.
- Required docs: `README.md` (what/why, 6-command quick start to the demo, features, screenshots-free), `docs/ARCHITECTURE.md` (layers, data flow Mermaid diagram, tables, module responsibilities), `docs/RULES.md` (every kind with JSON + UI walkthrough incl. the 5/20 failed-login example), `docs/RISK_RULES.md` (generated), `docs/API.md`, `docs/SECURITY.md` (threat model, trust boundaries, data stored/never stored), `docs/LIMITATIONS.md`, `docs/OPERATIONS.md`, `docs/DEMO.md`, `docs/DECISIONS.md` (dated entries: decision, reason, alternatives), `docs/AUDIT_REPORT.md`.
- Always state limits honestly: polling gaps, psutil snapshot limits, single host, no remediation, heuristic thresholds uncalibrated, SQLite scale, indicative MITRE mapping.
- Terminology: "possible/suspicious/consistent with"; never claim confirmed compromise. Use the same names as the code (event types, rule ids, endpoints).
- Mermaid for diagrams; tables for catalogues; no marketing language.
