# Sales Invoice creation for SELF orders (Phase 17, order-to-cash).
# Operator-invoked: a human creates the draft invoice from a SUBMITTED
# Delivery Note (goods actually left the building), reviews, and submits it.
# No automation, no scheduler. Idempotent per Delivery Note. FBA/WFS orders
# settle through their marketplaces and have no Delivery Notes (INV-7), so
# they never reach this path; the guard makes that explicit.

import frappe
from frappe import _


@frappe.whitelist()
def create_invoice_for_delivery(delivery_note):
	from canadian_outlet.co_core.safe_mode import assert_not_safe_mode

	assert_not_safe_mode("invoicing")
	dn = frappe.get_doc("Delivery Note", delivery_note)

	if dn.docstatus != 1:
		frappe.throw(
			_("Delivery Note {0} must be submitted before invoicing — invoice what shipped, "
			"not what was staged (INV-8)").format(dn.name)
		)

	for item in dn.items:
		if item.against_sales_order:
			fulfillment_type = frappe.db.get_value(
				"Sales Order", item.against_sales_order, "co_fulfillment_type"
			)
			if fulfillment_type and fulfillment_type != "SELF":
				frappe.throw(
					_("{0} is a {1} order — marketplace-settled, not invoiced here (INV-7)").format(
						item.against_sales_order, fulfillment_type
					)
				)

	# Idempotent: one non-cancelled invoice per Delivery Note.
	existing = frappe.get_all(
		"Sales Invoice Item",
		filters={"delivery_note": dn.name, "docstatus": ("<", 2)},
		pluck="parent",
		limit=1,
	)
	if existing:
		return existing[0]

	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	invoice = make_sales_invoice(dn.name)
	invoice.insert()  # draft — a human reviews and submits
	return invoice.name
