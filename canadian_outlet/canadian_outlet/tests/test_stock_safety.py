# T-STK-1..4 (docs/TEST-PLAN.md) — INV-7, INV-8 and the V1 scope rule that the
# import pipeline never touches stock (docs/STOCK-FLOW.md). T-STK-1/2 verify
# the stock model against standard ERPNext behavior and are green on a bench
# today; T-STK-3/4 exercise the Phase 10/11 pipeline.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Stock"


def _stock_ledger_entries(voucher_type, voucher_no):
	return frappe.get_all(
		"Stock Ledger Entry",
		filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
		fields=["name", "actual_qty"],
	)


def _stock_documents_for_order(sales_order_name):
	delivery_notes = frappe.get_all(
		"Delivery Note Item", filters={"against_sales_order": sales_order_name}, pluck="parent"
	)
	return delivery_notes


class TestStockSafety(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "AFN", "FBA")
		utils.make_rule(CHANNEL, "fulfillment_channel", "MFN", "SELF")
		utils.enable_imports()

	def _make_delivery_note(self, qty=1):
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry

		make_stock_entry(
			item_code=utils.TEST_ITEM, target=utils.TEST_WAREHOUSE, qty=qty + 10, basic_rate=1
		)
		return frappe.get_doc(
			{
				"doctype": "Delivery Note",
				"customer": utils.TEST_CUSTOMER,
				"company": utils.TEST_COMPANY,
				"items": [
					{
						"item_code": utils.TEST_ITEM,
						"qty": qty,
						"rate": 10,
						"warehouse": utils.TEST_WAREHOUSE,
					}
				],
			}
		).insert()

	def test_t_stk_1_draft_delivery_note_moves_no_stock(self):
		# T-STK-1 (INV-8): draft DN -> zero stock ledger entries; any
		# "deduction exists?" logic must count docstatus = 1 only.
		dn = self._make_delivery_note()
		self.assertEqual(dn.docstatus, 0)
		self.assertEqual(_stock_ledger_entries("Delivery Note", dn.name), [])

	def test_t_stk_2_submitted_delivery_note_deducts_exactly_once(self):
		# T-STK-2 (INV-7, INV-8)
		dn = self._make_delivery_note(qty=2)
		dn.submit()
		entries = _stock_ledger_entries("Delivery Note", dn.name)
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].actual_qty, -2)
		# A submitted document cannot submit twice (exactly-once by model).
		self.assertRaises(Exception, dn.submit)

	def test_t_stk_3_fba_import_creates_no_stock_documents(self):
		# T-STK-3 (INV-7): FBA/WFS orders never touch local stock.
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-STK3")
		order = utils.make_order(
			CHANNEL,
			"ORD-STK3",
			lines=[{"external_identity": "EXT-SKU-STK3", "qty": 1, "rate": 5}],
			evidence=dict(utils.AMAZON_AFN_EVIDENCE),
		)
		result = import_order(order)
		self.assertEqual(result.outcome, "Created")

		sales_orders = utils.get_sales_orders(CHANNEL, "ORD-STK3")
		self.assertEqual(sales_orders[0].co_fulfillment_type, "FBA")
		self.assertEqual(_stock_documents_for_order(sales_orders[0].name), [])

	def test_t_stk_4_pipeline_creates_no_stock_documents_for_self(self):
		# T-STK-4 (INV-8, V1 scope): even SELF imports create no Delivery Note
		# in V1 (docs/ORDER-FLOW.md §6 — draft DN auto-creation not scoped).
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-STK4")
		stock_entry_count_before = frappe.db.count("Stock Entry")
		delivery_note_count_before = frappe.db.count("Delivery Note")

		order = utils.make_order(
			CHANNEL,
			"ORD-STK4",
			lines=[{"external_identity": "EXT-SKU-STK4", "qty": 1, "rate": 5}],
			evidence=dict(utils.AMAZON_MFN_EVIDENCE),
		)
		result = import_order(order)
		self.assertEqual(result.outcome, "Created")

		sales_orders = utils.get_sales_orders(CHANNEL, "ORD-STK4")
		self.assertEqual(sales_orders[0].co_fulfillment_type, "SELF")
		self.assertEqual(sales_orders[0].docstatus, 0)
		self.assertEqual(_stock_documents_for_order(sales_orders[0].name), [])
		self.assertEqual(frappe.db.count("Stock Entry"), stock_entry_count_before)
		self.assertEqual(frappe.db.count("Delivery Note"), delivery_note_count_before)
