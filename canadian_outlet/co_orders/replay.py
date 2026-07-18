# Operator-invoked replay of Integration Exceptions (docs/ORDER-FLOW.md §3).
# Replay reconstructs the minimal order from replay_payload_minimal and
# re-enters the ONE pipeline at step 1 (INV-9) — idempotent by construction
# (INV-11). No scheduler, no automation: a human triggers this after fixing
# the cause. Status semantics per docs/DATA-MODEL.md §5.

import json

import frappe
from frappe import _

from canadian_outlet.co_orders.import_service import import_order


@frappe.whitelist()
def replay_exception(exception_name):
	exc = frappe.get_doc("Integration Exception", exception_name)

	if exc.status == "Ignored":
		# Ignored = deliberate human decision not to import (DATA-MODEL §5).
		frappe.throw(_("{0} is Ignored and must not be replayed").format(exc.name))

	if not exc.replay_payload_minimal:
		frappe.throw(
			_("{0} has no replay payload (purged per retention policy?). "
			"Re-fetch via external_payload_reference: {1}").format(
				exc.name, exc.external_payload_reference or "-"
			)
		)

	order = json.loads(exc.replay_payload_minimal)
	result = import_order(order)

	if result.outcome in ("Created", "Duplicate") and exc.status != "Resolved":
		# The order is in; the cause is evidently fixed. The exception record
		# reflects that (proof of import remains the Order Import Log).
		exc.reload()
		exc.status = "Resolved"
		exc.save(ignore_permissions=True)

	return {
		"outcome": result.outcome,
		"sales_order": result.sales_order,
		"integration_exception": result.integration_exception,
	}
