---
description: Execute one phase of the Sentinel build plan (usage: /phase 5)
---
Execute **Phase $ARGUMENTS** and nothing else.

1. Read `AGENTS.md`, then the spec file `specs/` whose name starts with the zero-padded phase number (e.g. `specs/05-*.md`), and the relevant parts of `SENTINEL_MASTER_PROMPT.md`. Load the `sentinel-*` skills named at the top of the spec.
2. State your plan and the tests you will write.
3. Write tests first, see them fail for the right reason, implement, make them pass. Run the **entire** test suite (and web tests once `web/` exists) plus `make lint`.
4. Run `/review $ARGUMENTS` (the `reviewer` subagent; also `security-auditor` for phases 11, 12, 13, 16, 17, 19) and fix every blocker.
5. Update `PROGRESS.md` and `docs/DECISIONS.md`; commit as `phase-$ARGUMENTS: <summary>`.
6. Report exactly: Done (files) · Tests (paste summary lines) · Reviewer findings and fixes · Decisions/deviations · Risks/open issues · Next (first three actions). Then stop and wait for "continue".

Follow every rule in `AGENTS.md`. No stubs, no unrequested features or dependencies.
