# Payment Entry creation for invoiced SELF orders (Phase 19, order-to-cash).
# Operator-invoked: a human records the payment against a SUBMITTED Sales
# Invoice, reviews the draft Payment Entry, and submits it. No reconciliation
# automation, no scheduler — marketplace settlement matching is a later,
# explicitly scoped phase.

import frappe
from frappe import _


@frappe.whitelist()
def record_payment_for_invoice(sales_invoice, bank_account=None, reference_no=None,
		reference_date=None):
	invoice = frappe.get_doc("Sales Invoice", sales_invoice)

	if invoice.docstatus != 1:
		frappe.throw(_("Sales Invoice {0} must be submitted before recording payment").format(invoice.name))
	if not invoice.outstanding_amount:
		frappe.throw(_("Sales Invoice {0} has no outstanding amount").format(invoice.name))

	# One open draft per invoice: avoid stacking duplicate drafts. Partial
	# payments are still possible — submit the draft, then call again.
	existing_draft = frappe.get_all(
		"Payment Entry Reference",
		filters={"reference_doctype": "Sales Invoice", "reference_name": invoice.name,
			"docstatus": 0},
		pluck="parent",
		limit=1,
	)
	if existing_draft:
		return existing_draft[0]

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	payment = get_payment_entry("Sales Invoice", invoice.name, bank_account=bank_account)
	payment.reference_no = reference_no or invoice.name
	payment.reference_date = reference_date or frappe.utils.nowdate()
	payment.insert()  # draft — a human reviews and submits
	return payment.name
