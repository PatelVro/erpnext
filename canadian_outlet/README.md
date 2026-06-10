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

Order spine complete and verified (49+ tests green on a v15 bench): planning
docs, 7 custom DocTypes, Sales Order custom fields, item resolution,
fulfillment classification, the shared Order Import Service, operator-invoked
draft Delivery Notes (SELF only), WooCommerce/Amazon/Walmart importers,
ShipStation status sync, exception replay, and the retention purge.

Still gated until explicitly scoped: scheduled jobs of any kind, webhook
transports, automatic stock posting (docs/STOCK-FLOW.md §5), payment
reconciliation, frontend pages. See docs/OPERATIONS.md for the runbook.

## License

Proprietary — see license.txt
