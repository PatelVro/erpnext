# STOCK-FLOW §5 upgrade tests — shipped event auto-submits the EXISTING
# draft Delivery Note, behind a default-off kill switch, SELF only,
# exactly-once. The human review path stays the backstop.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-AutoSubmit"


def _shipment(order_id, tracking="TRACK-AUTO-1"):
	return {
		"shipmentId": 91001,
		"orderNumber": order_id,
		"carrierCode": "canada_post",
		"trackingNumber": tracking,
		"shipDate": "2026-01-06",
		"voided": False,
	}


class TestAutoSubmitDeliveryNote(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()
		# Kill switch defaults OFF; tests turn it on explicitly.
		frappe.db.set_single_value(
			"Canadian Outlet Settings", "auto_submit_delivery_note_on_shipped", 0
		)

	def _self_order_with_draft_dn(self, order_id):
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_inventory.delivery_note_service import create_draft_delivery_note
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		result = import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": 1, "rate": 5}],
			)
		)
		so = frappe.get_doc("Sales Order", result.sales_order)
		warehouse = so.items[0].warehouse
		self.assertTrue(warehouse)  # SELF orders inherit Settings.default_warehouse
		make_stock_entry(item_code=utils.TEST_ITEM, target=warehouse, qty=20, basic_rate=1,
			company=so.company)
		so.submit()
		dn_name = create_draft_delivery_note(so.name)
		return so, dn_name

	def _record_shipped(self, order_id, tracking="TRACK-AUTO-1"):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		return record_shipment_event(translate_shipment(CHANNEL, _shipment(order_id, tracking)))

	def test_kill_switch_off_keeps_draft(self):
		_, dn_name = self._self_order_with_draft_dn("ORD-AUTO1")
		self._record_shipped("ORD-AUTO1")
		self.assertEqual(frappe.db.get_value("Delivery Note", dn_name, "docstatus"), 0)

	def test_shipped_event_submits_existing_draft_exactly_once(self):
		frappe.db.set_single_value(
			"Canadian Outlet Settings", "auto_submit_delivery_note_on_shipped", 1
		)
		_, dn_name = self._self_order_with_draft_dn("ORD-AUTO2")
		dn_count_before = frappe.db.count("Delivery Note")

		self._record_shipped("ORD-AUTO2")
		self.assertEqual(frappe.db.get_value("Delivery Note", dn_name, "docstatus"), 1)
		entries = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_type": "Delivery Note", "voucher_no": dn_name, "is_cancelled": 0},
		)
		self.assertEqual(len(entries), 1)

		# Duplicate event: deduped, nothing further happens.
		self._record_shipped("ORD-AUTO2")
		# A second DISTINCT shipped event finds no draft: no-op, no new document.
		self._record_shipped("ORD-AUTO2", tracking="TRACK-AUTO-2")
		self.assertEqual(
			len(
				frappe.get_all(
					"Stock Ledger Entry",
					filters={"voucher_type": "Delivery Note", "voucher_no": dn_name, "is_cancelled": 0},
				)
			),
			1,
		)
		self.assertEqual(frappe.db.count("Delivery Note"), dn_count_before)

	def test_never_creates_a_delivery_note(self):
		from canadian_outlet.co_orders.import_service import import_order

		frappe.db.set_single_value(
			"Canadian Outlet Settings", "auto_submit_delivery_note_on_shipped", 1
		)
		# SELF order with NO draft DN staged.
		utils.make_listing(CHANNEL, "EXT-SKU-ORD-AUTO3")
		import_order(
			utils.make_order(
				CHANNEL, "ORD-AUTO3",
				lines=[{"external_identity": "EXT-SKU-ORD-AUTO3", "qty": 1, "rate": 5}],
			)
		)
		dn_count_before = frappe.db.count("Delivery Note")
		self._record_shipped("ORD-AUTO3")
		self.assertEqual(frappe.db.count("Delivery Note"), dn_count_before)

	def test_voided_event_keeps_draft(self):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		frappe.db.set_single_value(
			"Canadian Outlet Settings", "auto_submit_delivery_note_on_shipped", 1
		)
		_, dn_name = self._self_order_with_draft_dn("ORD-AUTO4")
		payload = dict(_shipment("ORD-AUTO4", tracking="TRACK-AUTO-4"), voided=True)
		record_shipment_event(translate_shipment(CHANNEL, payload))
		self.assertEqual(frappe.db.get_value("Delivery Note", dn_name, "docstatus"), 0)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
