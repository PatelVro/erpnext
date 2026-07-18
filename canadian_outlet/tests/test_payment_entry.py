# Phase 19 tests — Payment Entry for invoiced deliveries (order-to-cash).
# Operator-invoked, draft-only, no duplicate drafts.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

TEST_BANK = "_Test Bank - _TC"


class TestPaymentEntry(FrappeTestCase):
	def _submitted_invoice(self):
		from erpnext.stock.doctype.delivery_note.test_delivery_note import create_delivery_note
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery

		make_stock_entry(item_code=utils.TEST_ITEM, target=utils.TEST_WAREHOUSE, qty=11, basic_rate=1)
		dn = create_delivery_note(
			item_code=utils.TEST_ITEM,
			warehouse=utils.TEST_WAREHOUSE,
			qty=1,
			rate=10,
			currency=utils.company_currency(),
		)
		invoice = frappe.get_doc("Sales Invoice", create_invoice_for_delivery(dn.name))
		invoice.submit()
		return invoice

	def test_submitted_invoice_gets_draft_payment(self):
		from canadian_outlet.co_billing.payment_service import record_payment_for_invoice

		invoice = self._submitted_invoice()
		payment_name = record_payment_for_invoice(invoice.name, bank_account=TEST_BANK)
		payment = frappe.get_doc("Payment Entry", payment_name)

		self.assertEqual(payment.docstatus, 0)  # draft — human submits
		self.assertEqual(payment.references[0].reference_name, invoice.name)
		self.assertEqual(payment.paid_amount, invoice.outstanding_amount)

		# Human submits; invoice settles.
		payment.submit()
		invoice.reload()
		self.assertEqual(invoice.outstanding_amount, 0)

	def test_no_duplicate_drafts(self):
		from canadian_outlet.co_billing.payment_service import record_payment_for_invoice

		invoice = self._submitted_invoice()
		first = record_payment_for_invoice(invoice.name, bank_account=TEST_BANK)
		second = record_payment_for_invoice(invoice.name, bank_account=TEST_BANK)
		self.assertEqual(first, second)

	def test_draft_invoice_is_refused(self):
		from erpnext.stock.doctype.delivery_note.test_delivery_note import create_delivery_note
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery
		from canadian_outlet.co_billing.payment_service import record_payment_for_invoice

		make_stock_entry(item_code=utils.TEST_ITEM, target=utils.TEST_WAREHOUSE, qty=11, basic_rate=1)
		dn = create_delivery_note(
			item_code=utils.TEST_ITEM,
			warehouse=utils.TEST_WAREHOUSE,
			qty=1,
			rate=10,
			currency=utils.company_currency(),
		)
		draft_invoice = create_invoice_for_delivery(dn.name)
		self.assertRaises(
			frappe.ValidationError, record_payment_for_invoice, draft_invoice, TEST_BANK
		)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
