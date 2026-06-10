# Returns and credit notes for SELF orders (Phase 21). Operator-invoked
# drafts via ERPNext's standard return mappers: the return Delivery Note
# brings stock back ONLY when a human submits it (INV-8 applies to returns
# exactly as to outbound), and the credit note reverses the invoice the same
# way. FBA/WFS returns are marketplace-managed and refused here (INV-7).

import frappe
from frappe import _


def _assert_self_only(doc, doctype_label):
	for item in doc.items:
		so_name = getattr(item, "against_sales_order", None) or getattr(item, "sales_order", None)
		if so_name:
			fulfillment_type = frappe.db.get_value("Sales Order", so_name, "co_fulfillment_type")
			if fulfillment_type and fulfillment_type != "SELF":
				frappe.throw(
					_("{0} belongs to a {1} order — returns are marketplace-managed, "
					"not local (INV-7)").format(doctype_label, fulfillment_type)
				)


@frappe.whitelist()
def create_return_for_delivery(delivery_note):
	dn = frappe.get_doc("Delivery Note", delivery_note)
	if dn.docstatus != 1:
		frappe.throw(_("Delivery Note {0} must be submitted to create a return against it").format(dn.name))
	_assert_self_only(dn, _("Delivery Note"))

	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	return_dn = make_return_doc("Delivery Note", dn.name)
	return_dn.insert()  # draft — stock returns only when a human submits (INV-8)
	return return_dn.name


@frappe.whitelist()
def create_credit_note_for_invoice(sales_invoice):
	invoice = frappe.get_doc("Sales Invoice", sales_invoice)
	if invoice.docstatus != 1:
		frappe.throw(_("Sales Invoice {0} must be submitted to credit it").format(invoice.name))
	_assert_self_only(invoice, _("Sales Invoice"))

	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	credit_note = make_return_doc("Sales Invoice", invoice.name)
	credit_note.insert()  # draft — a human reviews and submits
	return credit_note.name
