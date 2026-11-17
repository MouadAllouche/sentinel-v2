---
description: Review a finished phase with the read-only reviewer subagent (usage: /review 5)
---
Use the `reviewer` subagent to audit **Phase $ARGUMENTS** against `specs/` (the file starting with that zero-padded number), `AGENTS.md` and the `sentinel-review-checklist` skill. For phases 11, 12, 13, 16, 17 and 19 also use the `security-auditor` subagent. Return their findings verbatim, then list which blockers you will fix and fix them.
