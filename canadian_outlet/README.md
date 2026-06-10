# Canadian Outlet

Canadian Outlet business logic as a custom Frappe app on top of ERPNext
(version-15). ERPNext core is upstream and is never modified.

All business rules live in `docs/` (ERP-INVARIANTS.md is the constitution).
Agent rules live in `AGENTS.md`. Read both before changing anything.

## Installation

```bash
cd frappe-bench
bench get-app <this-repo-url>
bench --site <site> install-app canadian_outlet
```

Requires `frappe` and `erpnext` at version-15.

## Status

Phase 2 — bare scaffold. No business logic, no DocTypes, no integrations,
no scheduled jobs, no frontend, no stock automation. Each arrives only in
its explicitly approved phase (see the phase plan in the project docs).

## License

Proprietary — see license.txt
