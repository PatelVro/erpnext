# Phase 21 tests — returns and credit notes for SELF orders. Drafts only;
# stock comes back only on human submit (INV-8 symmetric).

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils


class TestReturns(FrappeTestCase):
	def _submitted_delivery_note(self, qty=2):
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
		)

	def test_return_is_draft_then_submit_restores_stock(self):
		from canadian_outlet.co_billing.return_service import create_return_for_delivery

		dn = self._submitted_delivery_note(qty=2)
		return_name = create_return_for_delivery(dn.name)
		return_dn = frappe.get_doc("Delivery Note", return_name)

		self.assertEqual(return_dn.docstatus, 0)  # draft: no stock impact yet
		self.assertEqual(return_dn.is_return, 1)
		self.assertEqual(return_dn.items[0].qty, -2)
		self.assertEqual(
			frappe.get_all(
				"Stock Ledger Entry",
				filters={"voucher_type": "Delivery Note", "voucher_no": return_name, "is_cancelled": 0},
			),
			[],
		)

		return_dn.submit()  # the human action
		entries = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_type": "Delivery Note", "voucher_no": return_name, "is_cancelled": 0},
			fields=["actual_qty"],
		)
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].actual_qty, 2)  # stock came back

	def test_credit_note_is_draft_against_invoice(self):
		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery
		from canadian_outlet.co_billing.return_service import create_credit_note_for_invoice

		dn = self._submitted_delivery_note(qty=1)
		invoice = frappe.get_doc("Sales Invoice", create_invoice_for_delivery(dn.name))
		invoice.submit()

		credit_name = create_credit_note_for_invoice(invoice.name)
		credit = frappe.get_doc("Sales Invoice", credit_name)
		self.assertEqual(credit.docstatus, 0)  # draft — human submits
		self.assertEqual(credit.is_return, 1)
		self.assertEqual(credit.return_against, invoice.name)
		self.assertEqual(credit.items[0].qty, -1)

	def test_draft_documents_are_refused(self):
		from erpnext.stock.doctype.delivery_note.test_delivery_note import create_delivery_note
		from canadian_outlet.co_billing.return_service import (
			create_credit_note_for_invoice,
			create_return_for_delivery,
		)

		draft_dn = create_delivery_note(
			item_code=utils.TEST_ITEM,
			warehouse=utils.TEST_WAREHOUSE,
			qty=1,
			rate=10,
			currency=utils.company_currency(),
			do_not_submit=True,
		)
		self.assertRaises(frappe.ValidationError, create_return_for_delivery, draft_dn.name)

		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery

		dn = self._submitted_delivery_note(qty=1)
		draft_invoice = create_invoice_for_delivery(dn.name)  # stays draft
		self.assertRaises(frappe.ValidationError, create_credit_note_for_invoice, draft_invoice)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
