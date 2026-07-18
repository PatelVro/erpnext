# Agent Rules — Canadian Outlet ERP

These rules bind every AI agent (Claude Code or otherwise) working in this
repository. They are not suggestions. If a task appears to require breaking a
rule, stop and ask the human instead.

## Boundaries

- Do not modify ERPNext core.
- Do not write outside this repository.
- Do not inspect or modify old `CO - ERP` folders unless explicitly instructed.
- Do not use subagents unless explicitly approved.

## Scope gates (each requires its own explicit scoping before any work)

- Do not create integrations unless specifically scoped.
- Do not create frontend pages unless specifically scoped.
- Do not add scheduled jobs unless specifically scoped.
- Do not add stock deduction automation unless specifically scoped.

## Business-rule guardrails (see docs/ERP-INVARIANTS.md)

- Do not create Items from marketplace orders when Channel Listing is missing.
- Do not default unknown fulfillment to SELF.
- Do not treat draft Delivery Notes as stock deductions.

## Working discipline

- Every implementation must cite the invariant it implements
  (INV-1 … INV-11 in docs/ERP-INVARIANTS.md).
- Before writing files, list the exact files to be created or modified.
- After writing files, show `git diff --stat`.
- Do not commit unless the human explicitly approves.
- When something is ambiguous, make the safest conservative assumption and
  flag it — never guess silently.
