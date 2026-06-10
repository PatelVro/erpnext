# Draft Delivery Note creation for SELF orders (Phase 12).
# Explicitly operator-invoked — there is NO automation here: no doc_events,
# no scheduler, no auto-submit (T-PIPE-1, docs/STOCK-FLOW.md §3). The draft
# stays docstatus=0 and is NOT a stock deduction (INV-8); stock moves only
# when a human submits it. FBA/WFS orders are refused (INV-7).

import frappe
from frappe import _


@frappe.whitelist()
def create_draft_delivery_note(sales_order):
	so = frappe.get_doc("Sales Order", sales_order)

	if so.co_fulfillment_type != "SELF":
		# INV-7: SELF is the only fulfillment type that may touch local stock.
		frappe.throw(
			_("Delivery Notes are only created for SELF orders; {0} is {1} (INV-7)").format(
				so.name, so.co_fulfillment_type or "blank"
			)
		)

	if so.docstatus != 1:
		# ERPNext requires a submitted Sales Order behind a Delivery Note;
		# submission is a human review step (docs/STOCK-FLOW.md §3).
		frappe.throw(_("Sales Order {0} must be submitted before staging a Delivery Note").format(so.name))

	# Idempotent: one open draft per Sales Order. Submitted DNs are partial
	# deliveries handled by ERPNext's own per-qty validation.
	existing_draft = frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": so.name, "docstatus": 0},
		pluck="parent",
		limit=1,
	)
	if existing_draft:
		return existing_draft[0]

	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	dn = make_delivery_note(so.name)
	dn.insert()  # draft only — submission is a human action (INV-8)
	return dn.name


def create_delivery_for_shipment(sales_order, item_qtys):
	"""C2 (FLOW-DECISIONS D5/D7): create AND SUBMIT a partial Delivery Note
	for exactly one shipment's quantities — the hold→deduction conversion,
	box by box. Quantities are capped at the order's undelivered remainder
	(channel-reported over-shipments are logged by the caller, never deducted
	past the order). Returns the DN name, or None when nothing remains to
	deliver. SELF-only is enforced by the caller; INV-8 holds: the submitted
	Delivery Note is the stock document."""
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	so = frappe.get_doc("Sales Order", sales_order)
	if so.co_fulfillment_type != "SELF" or so.docstatus != 1:
		return None

	dn = make_delivery_note(so.name)
	rows = []
	for row in dn.items:
		wanted = item_qtys.get(row.item_code, 0)
		if wanted <= 0:
			continue
		# row.qty from the mapper is the undelivered remainder — the cap.
		take = min(wanted, row.qty)
		if take <= 0:
			continue
		row.qty = take
		item_qtys[row.item_code] = wanted - take
		rows.append(row)

	if not rows:
		return None

	dn.items = []
	for index, row in enumerate(rows, start=1):
		row.idx = index
		dn.append("items", row)
	dn.insert(ignore_permissions=True)
	dn.submit()  # the deduction (INV-8), exactly this shipment's quantities
	return dn.name
