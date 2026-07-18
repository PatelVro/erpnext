# C3 tests — quarantine intake (FLOW-DECISIONS D3, BUILD-CHANGE-PLAN C3).
# Unclear fulfillment imports as a REAL order — visible, searchable — but
# quarantined: a draft that holds no stock, cannot ship, cannot invoice,
# until a human classifies it. UNKNOWN still never becomes SELF silently.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-C3"


def _reserved(item_code, warehouse):
	return frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "reserved_qty"
	) or 0


class TestC3Quarantine(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "MFN", "SELF")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 0)

	def _import_unclear(self, order_id, qty=2):
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		return import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": qty, "rate": 10}],
				evidence={"fulfillment_channel": "SOMETHING-NEW"},
			)
		)

	def test_unclear_order_imports_quarantined_and_holds_nothing(self):
		default_company = frappe.defaults.get_global_default("company")
		warehouse = frappe.db.get_value("Warehouse", {"company": default_company, "is_group": 0})
		reserved_before = _reserved(utils.TEST_ITEM, warehouse)

		result = self._import_unclear("ORD-C3A")
		self.assertEqual(result.outcome, "Created")
		self.assertTrue(result.quarantined)

		so = frappe.get_doc("Sales Order", result.sales_order)
		self.assertEqual(so.docstatus, 0)  # draft: cannot ship, cannot invoice
		self.assertEqual(so.co_quarantined, 1)
		self.assertFalse(so.co_fulfillment_type)  # blank is legal ONLY here (INV-6)
		self.assertEqual(_reserved(utils.TEST_ITEM, warehouse), reserved_before)  # no hold
		# No Integration Exception — quarantine IS the review state (D3).
		self.assertEqual(utils.get_exceptions(CHANNEL, "ORD-C3A"), [])

	def test_unknown_never_becomes_self_silently(self):
		self._import_unclear("ORD-C3B")
		self.assertEqual(
			frappe.get_all(
				"Sales Order",
				filters={"co_sales_channel": CHANNEL, "co_channel_order_id": "ORD-C3B",
					"co_fulfillment_type": "SELF"},
			),
			[],
		)

	def test_classify_as_self_releases_with_hold(self):
		from canadian_outlet.co_orders.quarantine import classify_quarantined_order

		result = self._import_unclear("ORD-C3C", qty=3)
		classify_quarantined_order(result.sales_order, "SELF")

		so = frappe.get_doc("Sales Order", result.sales_order)
		self.assertEqual(so.docstatus, 1)
		self.assertEqual(so.co_fulfillment_type, "SELF")
		self.assertEqual(so.co_quarantined, 0)
		self.assertTrue(so.items[0].warehouse)
		self.assertEqual(_reserved(utils.TEST_ITEM, so.items[0].warehouse), 3)

	def test_classify_as_fba_releases_as_drop_ship(self):
		from canadian_outlet.co_orders.quarantine import classify_quarantined_order

		result = self._import_unclear("ORD-C3D")
		classify_quarantined_order(result.sales_order, "FBA")

		so = frappe.get_doc("Sales Order", result.sales_order)
		self.assertEqual(so.docstatus, 1)
		self.assertEqual(so.co_fulfillment_type, "FBA")
		self.assertEqual(so.items[0].delivered_by_supplier, 1)  # INV-7

	def test_classify_rejects_garbage_and_non_quarantined(self):
		from canadian_outlet.co_orders.quarantine import classify_quarantined_order

		result = self._import_unclear("ORD-C3E")
		self.assertRaises(
			frappe.ValidationError, classify_quarantined_order, result.sales_order, "UNKNOWN"
		)

		classify_quarantined_order(result.sales_order, "SELF")
		# Already released: classifying again must refuse.
		self.assertRaises(
			frappe.ValidationError, classify_quarantined_order, result.sales_order, "FBA"
		)

	def test_quarantined_order_cannot_get_delivery_note(self):
		from canadian_outlet.co_inventory.delivery_note_service import create_draft_delivery_note

		result = self._import_unclear("ORD-C3F")
		self.assertRaises(frappe.ValidationError, create_draft_delivery_note, result.sales_order)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
