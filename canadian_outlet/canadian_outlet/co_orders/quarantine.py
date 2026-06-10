# Quarantine release (C3, FLOW-DECISIONS D3). A quarantined order is a DRAFT
# Sales Order with co_quarantined set: real and visible, but a draft holds no
# stock, cannot ship, and cannot invoice. Releasing it is a HUMAN judgment —
# the classifier never guesses (INV-5); blank fulfillment is legal only while
# quarantined (INV-6 as rewritten by C3).

import frappe
from frappe import _

from canadian_outlet.co_orders.classification import VALID_FULFILLMENT_TYPES


@frappe.whitelist()
def classify_quarantined_order(sales_order, fulfillment_type):
	if fulfillment_type not in VALID_FULFILLMENT_TYPES:
		frappe.throw(_("Fulfillment type must be one of {0}").format(
			", ".join(VALID_FULFILLMENT_TYPES)))

	from canadian_outlet.co_core.safe_mode import assert_not_safe_mode

	assert_not_safe_mode("releasing quarantined orders")
	so = frappe.get_doc("Sales Order", sales_order)
	if not so.co_quarantined or so.docstatus != 0:
		frappe.throw(_("{0} is not a quarantined order").format(so.name))

	if fulfillment_type == "SELF":
		warehouse = frappe.db.get_single_value("Canadian Outlet Settings", "default_warehouse")
		for line in so.items:
			line.warehouse = warehouse
			line.delivered_by_supplier = 0
			line.supplier = None
	else:
		# INV-7: marketplace-fulfilled rows are drop-ship — no shelf hold.
		supplier = frappe.db.get_single_value(
			"Canadian Outlet Settings", "marketplace_fulfillment_supplier"
		)
		if not supplier:
			frappe.throw(_(
				"Canadian Outlet Settings: marketplace_fulfillment_supplier is not set "
				"— required to classify as FBA/WFS (INV-7)"
			))
		for line in so.items:
			line.warehouse = None
			line.delivered_by_supplier = 1
			line.supplier = supplier

	so.co_fulfillment_type = fulfillment_type
	so.co_quarantined = 0
	so.save(ignore_permissions=True)
	so.submit()  # the hold starts now (INV-12) — or drop-ship, holding nothing
	return so.name
