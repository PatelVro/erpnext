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

Full suite verified (94 tests green on a v15 bench; phases 0-27): planning
docs, 7 custom DocTypes, Sales Order custom fields, item resolution,
fulfillment classification, the shared Order Import Service, operator-invoked
draft Delivery Notes (SELF only), WooCommerce/Amazon/Walmart importers,
ShipStation status sync, exception replay, and the retention purge.

Also live, each explicitly approved and kill-switched/pinned by tests:
WooCommerce webhooks, shipped-event Delivery Note submission (STOCK-FLOW §5),
exactly two scheduled jobs (daily sync, weekly purge), order-to-cash with
returns, operations role, reports + workspace, and read-only Amazon
settlement matching. Still gated: settlement GL postings (accounting
policy), purchasing automation, custom frontend pages. See
docs/OPERATIONS.md for the runbook.

## License

Proprietary — see license.txt
