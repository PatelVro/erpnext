# C2 tests — per-shipment deduction at shipped status (FLOW-DECISIONS D5/D7,
# BUILD-CHANGE-PLAN C2). A shipped event converts the hold into a real
# deduction for exactly that shipment's quantities, via a created-and-
# submitted partial Delivery Note (INV-8: submitted stock document). Behind
# switch ③ deduct_on_shipped_event, OFF by default — manual-first (D10).

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-C2"


def _shipment(order_id, items, tracking="TRACK-C2-1", voided=False):
	return {
		"shipmentId": 92001,
		"orderNumber": order_id,
		"carrierCode": "canada_post",
		"trackingNumber": tracking,
		"shipDate": "2026-01-09",
		"voided": voided,
		"shipmentItems": [{"sku": sku, "quantity": qty} for sku, qty in items],
	}


def _ledger(dn_name):
	return frappe.get_all(
		"Stock Ledger Entry",
		filters={"voucher_type": "Delivery Note", "voucher_no": dn_name, "is_cancelled": 0},
		fields=["actual_qty"],
	)


def _delivered_qty(so_name):
	return frappe.db.get_value("Sales Order Item", {"parent": so_name}, "delivered_qty") or 0


class TestC2Deduction(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "MFN", "SELF")
		utils.make_rule(CHANNEL, "fulfillment_channel", "AFN", "FBA")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 0)

	def _self_order(self, order_id, qty=5, evidence=None):
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		result = import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": qty, "rate": 10}],
				evidence=evidence or dict(utils.AMAZON_MFN_EVIDENCE),
			)
		)
		so = frappe.get_doc("Sales Order", result.sales_order)
		if so.items[0].warehouse:
			make_stock_entry(
				item_code=utils.TEST_ITEM, target=so.items[0].warehouse,
				qty=qty + 10, basic_rate=1, company=so.company,
			)
		return so

	def _record(self, order_id, items, **kwargs):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		return record_shipment_event(
			translate_shipment(CHANNEL, _shipment(order_id, items, **kwargs))
		)

	def test_switch_off_records_only(self):
		# D10 manual-first: with switch ③ OFF the event is recorded, nothing moves.
		so = self._self_order("ORD-C2A")
		dn_before = frappe.db.count("Delivery Note")
		event = self._record("ORD-C2A", [("EXT-SKU-ORD-C2A", 3)])

		self.assertTrue(frappe.db.exists("Shipment Status Event", event))
		self.assertEqual(frappe.db.count("Delivery Note"), dn_before)
		self.assertEqual(_delivered_qty(so.name), 0)

	def test_operator_processes_event_one_click(self):
		# Manual-first conversion: same logic, human trigger.
		from canadian_outlet.co_shipping.shipstation import process_shipment_event

		so = self._self_order("ORD-C2B")
		event = self._record("ORD-C2B", [("EXT-SKU-ORD-C2B", 3)])
		dn_name = process_shipment_event(event)

		self.assertEqual(frappe.db.get_value("Delivery Note", dn_name, "docstatus"), 1)
		entries = _ledger(dn_name)
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].actual_qty, -3)
		self.assertEqual(_delivered_qty(so.name), 3)
		# Processing again is a no-op (event already deducted).
		self.assertIsNone(process_shipment_event(event))
		self.assertEqual(_delivered_qty(so.name), 3)

	def test_switch_on_deducts_per_shipment_box_by_box(self):
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		so = self._self_order("ORD-C2C", qty=5)

		self._record("ORD-C2C", [("EXT-SKU-ORD-C2C", 3)], tracking="TRACK-BOX-1")
		self.assertEqual(_delivered_qty(so.name), 3)

		# Duplicate of box 1: event-hash dedup, nothing more deducts.
		self._record("ORD-C2C", [("EXT-SKU-ORD-C2C", 3)], tracking="TRACK-BOX-1")
		self.assertEqual(_delivered_qty(so.name), 3)

		# Box 2 ships the remaining 2.
		self._record("ORD-C2C", [("EXT-SKU-ORD-C2C", 2)], tracking="TRACK-BOX-2")
		self.assertEqual(_delivered_qty(so.name), 5)

	def test_voided_event_is_inert(self):
		# D7/1B: voids never touch the books.
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		so = self._self_order("ORD-C2D")
		self._record("ORD-C2D", [("EXT-SKU-ORD-C2D", 2)], voided=True)
		self.assertEqual(_delivered_qty(so.name), 0)

	def test_fba_event_deducts_nothing(self):
		# INV-7: marketplace-fulfilled orders never touch the shelf.
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		so = self._self_order("ORD-C2E", evidence=dict(utils.AMAZON_AFN_EVIDENCE))
		dn_before = frappe.db.count("Delivery Note")
		self._record("ORD-C2E", [("EXT-SKU-ORD-C2E", 2)])
		self.assertEqual(frappe.db.count("Delivery Note"), dn_before)
		self.assertEqual(_delivered_qty(so.name), 0)

	def test_over_shipment_is_capped_at_ordered_qty(self):
		# Channel says 10, order says 2: deduct what the order can carry; the
		# discrepancy is logged for the human queue, never a negative surprise.
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		so = self._self_order("ORD-C2F", qty=2)
		self._record("ORD-C2F", [("EXT-SKU-ORD-C2F", 10)])
		self.assertEqual(_delivered_qty(so.name), 2)

	def test_unknown_shipment_sku_fails_closed(self):
		# INV-2/INV-10: shipment items resolve through Channel Listing like
		# everything else; unknown SKU → no deduction, event kept for review.
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		so = self._self_order("ORD-C2G")
		dn_before = frappe.db.count("Delivery Note")
		event = self._record("ORD-C2G", [("NEVER-MAPPED-SKU", 1)])

		self.assertTrue(frappe.db.exists("Shipment Status Event", event))
		self.assertEqual(frappe.db.count("Delivery Note"), dn_before)
		self.assertEqual(_delivered_qty(so.name), 0)

	def test_event_without_items_fails_closed(self):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		so = self._self_order("ORD-C2H")
		payload = _shipment("ORD-C2H", [])
		payload.pop("shipmentItems")
		record_shipment_event(translate_shipment(CHANNEL, payload))
		self.assertEqual(_delivered_qty(so.name), 0)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
