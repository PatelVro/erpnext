# T-SHIP-1..4 (docs/TEST-PLAN.md) — Phase 14: shipment STATUS sync only.
# Recording events never touches stock or document status (INV-8,
# docs/STOCK-FLOW.md §4). Synthetic payloads only; no network.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Ship"

SYNTHETIC_SHIPMENT = {
	"shipmentId": 90001,
	"orderNumber": "ORD-SHIP1",
	"carrierCode": "canada_post",
	"trackingNumber": "TRACK-SYNTH-0001",
	"shipDate": "2026-01-03",
	"voided": False,
	# ShipStation payloads carry a shipTo block — translate_shipment must drop it.
	"shipTo": {"name": "Synthetic Q. Testbuyer", "street1": "123 Synthetic Test Street"},
}


class TestShipStationStatus(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 0)

	def _import_order(self, order_id):
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		return import_order(
			utils.make_order(
				CHANNEL, order_id, lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": 1, "rate": 5}]
			)
		)

	def test_t_ship_1_event_links_to_sales_order(self):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		result = self._import_order("ORD-SHIP1")
		event_name = record_shipment_event(translate_shipment(CHANNEL, SYNTHETIC_SHIPMENT))
		event = frappe.get_doc("Shipment Status Event", event_name)

		self.assertEqual(event.sales_order, result.sales_order)
		self.assertEqual(event.carrier_status, "shipped")
		# Ship-to PII never persists (PRIVACY-REDACTION §4).
		self.assertNotIn("Synthetic Test Street", frappe.as_json(event.as_dict()))

	def test_t_ship_2_duplicate_event_is_idempotent(self):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		self._import_order("ORD-SHIP1")
		first = record_shipment_event(translate_shipment(CHANNEL, SYNTHETIC_SHIPMENT))
		second = record_shipment_event(translate_shipment(CHANNEL, SYNTHETIC_SHIPMENT))

		self.assertEqual(first, second)
		self.assertEqual(
			frappe.db.count(
				"Shipment Status Event", {"channel": CHANNEL, "channel_order_id": "ORD-SHIP1"}
			),
			1,
		)

	def test_t_ship_3_shipped_event_never_touches_stock(self):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		result = self._import_order("ORD-SHIP1")
		dn_before = frappe.db.count("Delivery Note")
		se_before = frappe.db.count("Stock Entry")
		sle_before = frappe.db.count("Stock Ledger Entry")
		docstatus_before = frappe.db.get_value("Sales Order", result.sales_order, "docstatus")

		record_shipment_event(translate_shipment(CHANNEL, SYNTHETIC_SHIPMENT))

		self.assertEqual(frappe.db.count("Delivery Note"), dn_before)
		self.assertEqual(frappe.db.count("Stock Entry"), se_before)
		self.assertEqual(frappe.db.count("Stock Ledger Entry"), sle_before)
		self.assertEqual(
			frappe.db.get_value("Sales Order", result.sales_order, "docstatus"), docstatus_before
		)

	def test_t_ship_4_unknown_order_records_unlinked_event(self):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		payload = dict(SYNTHETIC_SHIPMENT, orderNumber="ORD-NEVER-IMPORTED", trackingNumber="TRACK-X9")
		event_name = record_shipment_event(translate_shipment(CHANNEL, payload))
		event = frappe.get_doc("Shipment Status Event", event_name)

		self.assertIsNone(event.sales_order)
		self.assertEqual(event.channel_order_id, "ORD-NEVER-IMPORTED")
		# Informational: no Integration Exception is created for status events.
		self.assertEqual(utils.get_exceptions(CHANNEL, "ORD-NEVER-IMPORTED"), [])

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
