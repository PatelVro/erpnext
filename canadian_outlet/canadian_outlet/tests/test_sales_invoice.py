# Phase 17 tests — Sales Invoice for SELF deliveries (order-to-cash).
# Operator-invoked, draft-only, idempotent per Delivery Note.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils


class TestSalesInvoice(FrappeTestCase):
	def _submitted_delivery_note(self, qty=1):
		from erpnext.stock.doctype.delivery_note.test_delivery_note import create_delivery_note
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry

		make_stock_entry(
			item_code=utils.TEST_ITEM, target=utils.TEST_WAREHOUSE, qty=qty + 10, basic_rate=1
		)
		return create_delivery_note(
			item_code=utils.TEST_ITEM,
			warehouse=utils.TEST_WAREHOUSE,
			qty=qty,
			rate=10,
			currency=utils.company_currency(),
		)  # helper submits by default

	def test_submitted_delivery_gets_draft_invoice(self):
		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery

		dn = self._submitted_delivery_note()
		invoice_name = create_invoice_for_delivery(dn.name)
		invoice = frappe.get_doc("Sales Invoice", invoice_name)

		self.assertEqual(invoice.docstatus, 0)  # draft — human submits
		self.assertEqual(invoice.items[0].delivery_note, dn.name)
		self.assertEqual(invoice.items[0].qty, 1)

	def test_second_call_is_idempotent(self):
		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery

		dn = self._submitted_delivery_note()
		first = create_invoice_for_delivery(dn.name)
		second = create_invoice_for_delivery(dn.name)
		self.assertEqual(first, second)
		self.assertEqual(
			frappe.db.count("Sales Invoice Item", {"delivery_note": dn.name, "docstatus": 0}), 1
		)

	def test_draft_delivery_note_is_refused(self):
		from erpnext.stock.doctype.delivery_note.test_delivery_note import create_delivery_note
		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery

		dn = create_delivery_note(
			item_code=utils.TEST_ITEM,
			warehouse=utils.TEST_WAREHOUSE,
			qty=1,
			rate=10,
			currency=utils.company_currency(),
			do_not_submit=True,
		)
		self.assertRaises(frappe.ValidationError, create_invoice_for_delivery, dn.name)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
