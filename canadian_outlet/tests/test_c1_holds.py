# C1 tests — stock holds at import (FLOW-DECISIONS D5/D6, BUILD-CHANGE-PLAN C1).
# A SELF order's units are unavailable from the moment of import (INV-12:
# availability honesty) without moving the physical count; cancellation before
# ship releases the hold; after ship it stops for review.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-C1"


def _reserved(item_code, warehouse):
	return frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "reserved_qty"
	) or 0


def _actual(item_code, warehouse):
	return frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
	) or 0


class TestC1Holds(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "MFN", "SELF")
		utils.make_rule(CHANNEL, "fulfillment_channel", "AFN", "FBA")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 0)

	def _import(self, order_id, qty=2, evidence=None, **overrides):
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		return import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": qty, "rate": 10}],
				evidence=evidence or dict(utils.AMAZON_MFN_EVIDENCE),
				**overrides,
			)
		)

	def test_self_import_holds_without_moving_physical_count(self):
		# INV-12: submitted on arrival; availability down, shelf untouched.
		warehouse = utils.shelf_warehouse()
		actual_before = _actual(utils.TEST_ITEM, warehouse)

		result = self._import("ORD-C1A", qty=3)
		so = frappe.get_doc("Sales Order", result.sales_order)

		self.assertEqual(so.docstatus, 1)  # confirmed sale, auto-submitted
		self.assertEqual(so.items[0].warehouse, warehouse)
		self.assertEqual(_reserved(utils.TEST_ITEM, warehouse), 3)
		self.assertEqual(_actual(utils.TEST_ITEM, warehouse), actual_before)
		# No stock ledger entry was created by the import (hold ≠ deduction).
		self.assertEqual(
			frappe.get_all(
				"Stock Ledger Entry",
				filters={"voucher_type": "Sales Order", "voucher_no": so.name},
			),
			[],
		)

	def test_fba_import_holds_nothing(self):
		warehouse = utils.shelf_warehouse()
		reserved_before = _reserved(utils.TEST_ITEM, warehouse)

		result = self._import("ORD-C1B", evidence=dict(utils.AMAZON_AFN_EVIDENCE))
		so = frappe.get_doc("Sales Order", result.sales_order)
		self.assertEqual(so.docstatus, 1)
		# INV-7: marketplace-fulfilled rows are drop-ship — no shelf hold.
		self.assertEqual(so.items[0].delivered_by_supplier, 1)
		self.assertEqual(_reserved(utils.TEST_ITEM, warehouse), reserved_before)

	def test_fba_import_fails_closed_without_fulfillment_supplier(self):
		frappe.db.set_single_value(
			"Canadian Outlet Settings", "marketplace_fulfillment_supplier", None
		)
		result = self._import("ORD-C1F", evidence=dict(utils.AMAZON_AFN_EVIDENCE))
		self.assertEqual(result.outcome, "Exception")
		self.assertEqual(utils.get_sales_orders(CHANNEL, "ORD-C1F"), [])

	def test_cancellation_before_ship_releases_hold(self):
		# D6: SILENT auto-release. The same order arrives again, flagged
		# cancelled by the channel, before anything shipped.
		result = self._import("ORD-C1C", qty=2)
		so = frappe.get_doc("Sales Order", result.sales_order)
		warehouse = so.items[0].warehouse
		self.assertEqual(_reserved(utils.TEST_ITEM, warehouse), 2)

		second = self._import("ORD-C1C", qty=2, cancelled=True)
		self.assertEqual(second.outcome, "Duplicate")
		so.reload()
		self.assertEqual(so.docstatus, 2)  # cancelled
		self.assertEqual(_reserved(utils.TEST_ITEM, warehouse), 0)
		self.assertEqual(utils.get_exceptions(CHANNEL, "ORD-C1C"), [])

	def test_cancellation_after_ship_stops_for_review(self):
		# D6: STOP — goods and money both in motion.
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_inventory.delivery_note_service import create_draft_delivery_note

		result = self._import("ORD-C1D", qty=1)
		so = frappe.get_doc("Sales Order", result.sales_order)
		make_stock_entry(
			item_code=utils.TEST_ITEM, target=so.items[0].warehouse, qty=5, basic_rate=1,
			company=so.company,
		)
		dn = frappe.get_doc("Delivery Note", create_draft_delivery_note(so.name))
		dn.submit()  # shipped

		second = self._import("ORD-C1D", qty=1, cancelled=True)
		exceptions = utils.get_exceptions(CHANNEL, "ORD-C1D", failure_stage="Cancellation")
		self.assertEqual(len(exceptions), 1)
		so.reload()
		self.assertEqual(so.docstatus, 1)  # untouched — human decides
		self.assertEqual(second.outcome, "Duplicate")

	def test_cancelled_on_arrival_exists_but_holds_nothing(self):
		# D1: every order exists per-order — even one already cancelled.
		result = self._import("ORD-C1E", qty=2, cancelled=True)
		self.assertEqual(result.outcome, "Created")
		so = frappe.get_doc("Sales Order", result.sales_order)
		self.assertEqual(so.docstatus, 2)  # record exists, cancelled, no hold
		self.assertEqual(_reserved(utils.TEST_ITEM, so.items[0].warehouse or ""), 0)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
