# CLAUDE.md

Claude Code must read and follow **AGENTS.md** in this repository root.

AGENTS.md is binding for every session: repository boundaries, scope gates
(integrations, frontend, scheduled jobs, stock automation), business-rule
guardrails, and working discipline (list files before writing, show
`git diff --stat` after, no commits without explicit approval).

The business rules themselves are defined in `docs/ERP-INVARIANTS.md`
(INV-1 … INV-11) and the other planning documents under `docs/`. When code
and docs disagree, the docs win until a human changes them.

For full machine-readable context — what this system is, every decision and
invariant, the behavior map, install/test recipes, and the hard-won internal
gotchas — read **AI-HANDOFF.md** at the repository root before doing anything.
