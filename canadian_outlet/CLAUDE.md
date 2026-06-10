# CLAUDE.md

Claude Code must read and follow **AGENTS.md** in this repository root.

AGENTS.md is binding for every session: repository boundaries, scope gates
(integrations, frontend, scheduled jobs, stock automation), business-rule
guardrails, and working discipline (list files before writing, show
`git diff --stat` after, no commits without explicit approval).

The business rules themselves are defined in `docs/ERP-INVARIANTS.md`
(INV-1 … INV-11) and the other planning documents under `docs/`. When code
and docs disagree, the docs win until a human changes them.
