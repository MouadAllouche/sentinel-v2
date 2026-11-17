---
name: sentinel-review-checklist
description: Per-phase self-audit and review checklist for Sentinel - spec conformance, safety rules, purity, idempotence, tests, security, UI accessibility. Load before reporting a phase as done and whenever acting as the reviewer or security-auditor subagent.
---

# Review checklist (answer each with evidence: file:line or test name)

**Spec**: every bullet of `specs/NN-*.md` implemented? Named tests present? Deviations recorded in `DECISIONS.md`?
**Safety**: no sudo/remediation; no writes outside project or to monitored paths; no secrets/contents/cmdline/args stored or logged; `/etc/shadow` metadata-only enforced and tested; no `shell=True/eval/exec`; SQL parameterised; no outbound network by default.
**Architecture**: `core/` pure (no DB/fs/clock/env/network imports); I/O only in `storage/collectors/engine/api`; routers thin; web has no security logic; every storage fn takes `db_path`.
**Correctness**: timestamps UTC-aware; event hash excludes severity/severity_source/enrichment; idempotent re-runs; order-independence property tests exist; boundaries tested; no double counting in scoring; reasons sum to raw score.
**User control**: edits are validated, versioned, audited, resettable; defaults seeded without overwriting user edits.
**API/Security**: RBAC matrix, CSRF, cookie flags, uniform login errors, lockout, size/limit bounds, headers, audit rows, no secret values in responses.
**Frontend**: typed client only; URL-synced filters; loading/empty/error states; role-aware controls; text labels with colors; keyboard operable; sanitised markdown; no file contents displayed.
**Quality**: no stubs/TODOs; types/docstrings; lint+mypy clean; coverage reported; tests not weakened; docs match code.
**Output format**: Blockers (must fix) · Majors · Minors · Questions · "Verified OK" list. Blockers prevent the phase from being reported done.
