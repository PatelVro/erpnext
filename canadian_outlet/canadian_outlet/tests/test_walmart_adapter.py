# Phase 16 tests — Walmart adapter. WFS -> WFS, seller-fulfilled -> SELF,
# unknown ship node never SELF (INV-5/6/10); WFS creates no stock documents
# (INV-7). Synthetic payloads only; no network.

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Walmart"


def synthetic_walmart_order(purchase_order_id, ship_node_type, currency):
	return {
		"purchaseOrderId": purchase_order_id,
		"orderDate": 1767456000000,
		"shipNode": {"type": ship_node_type},
		"shippingInfo": {
			"postalAddress": {"address1": "321 Synthetic Test Blvd", "name": "Synthetic W. Buyer"},
			"phone": "+1-555-0177-TEST",
		},
		"orderLines": {
			"orderLine": [
				{
					"item": {"sku": "WMT-SKU-1", "productName": "Synthetic Product"},
					"orderLineQuantity": {"amount": "1"},
					"charges": {
						"charge": [
							{"chargeType": "PRODUCT", "chargeAmount": {"amount": 19.99, "currency": currency}}
						]
					},
					"orderLineStatuses": {"orderLineStatus": [{"status": "Created"}]},
				}
			]
		},
	}


class TestWalmartAdapter(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Walmart")
		utils.enable_imports()

	def test_setup_creates_both_rules_as_data(self):
		from canadian_outlet.co_orders.adapters.walmart import setup_walmart_channel

		setup_walmart_channel(CHANNEL)
		for value, expected in (("WFSFulfilled", "WFS"), ("SellerFulfilled", "SELF")):
			self.assertEqual(
				frappe.db.get_value(
					"Channel Fulfillment Map",
					{"channel": CHANNEL, "evidence_key": "ship_node_type", "evidence_value": value},
					"fulfillment_type",
				),
				expected,
			)
		setup_walmart_channel(CHANNEL)  # idempotent

	def test_translation_carries_no_buyer_pii(self):
		from canadian_outlet.co_orders.adapters.walmart import translate_order

		payload = synthetic_walmart_order("WM-1001", "WFSFulfilled", utils.default_currency())
		order = translate_order(CHANNEL, payload)

		self.assertEqual(order["channel_order_id"], "WM-1001")
		self.assertEqual(order["evidence"], {"ship_node_type": "WFSFulfilled"})
		self.assertEqual(order["lines"], [{"external_identity": "WMT-SKU-1", "qty": 1.0, "rate": 19.99}])
		order_text = json.dumps(order)
		for pii in ("321 Synthetic Test Blvd", "Synthetic W. Buyer", "+1-555-0177-TEST"):
			self.assertNotIn(pii, order_text)

	def test_wfs_imports_as_wfs_with_no_stock_documents(self):
		from canadian_outlet.co_orders.adapters.walmart import setup_walmart_channel, translate_order
		from canadian_outlet.co_orders.import_service import import_order

		setup_walmart_channel(CHANNEL)
		utils.make_listing(CHANNEL, "WMT-SKU-1")
		dn_before = frappe.db.count("Delivery Note")
		se_before = frappe.db.count("Stock Entry")

		payload = synthetic_walmart_order("WM-1002", "WFSFulfilled", utils.default_currency())
		result = import_order(translate_order(CHANNEL, payload))

		self.assertEqual(result.outcome, "Created")
		sales_orders = utils.get_sales_orders(CHANNEL, "WM-1002")
		self.assertEqual(sales_orders[0].co_fulfillment_type, "WFS")
		self.assertEqual(frappe.db.count("Delivery Note"), dn_before)
		self.assertEqual(frappe.db.count("Stock Entry"), se_before)

	def test_seller_fulfilled_imports_as_self(self):
		from canadian_outlet.co_orders.adapters.walmart import setup_walmart_channel, translate_order
		from canadian_outlet.co_orders.import_service import import_order

		setup_walmart_channel(CHANNEL)
		utils.make_listing(CHANNEL, "WMT-SKU-1")
		payload = synthetic_walmart_order("WM-1003", "SellerFulfilled", utils.default_currency())
		result = import_order(translate_order(CHANNEL, payload))

		self.assertEqual(result.outcome, "Created")
		self.assertEqual(utils.get_sales_orders(CHANNEL, "WM-1003")[0].co_fulfillment_type, "SELF")

	def test_unknown_ship_node_fails_closed_never_self(self):
		from canadian_outlet.co_orders.adapters.walmart import setup_walmart_channel, translate_order
		from canadian_outlet.co_orders.import_service import import_order

		setup_walmart_channel(CHANNEL)
		utils.make_listing(CHANNEL, "WMT-SKU-1")
		payload = synthetic_walmart_order("WM-1004", "3PLFulfilled", utils.default_currency())
		result = import_order(translate_order(CHANNEL, payload))

		# C3: quarantined draft, never SELF, holds nothing.
		self.assertEqual(result.outcome, "Created")
		self.assertTrue(result.quarantined)
		sales_orders = utils.get_sales_orders(CHANNEL, "WM-1004")
		self.assertEqual(sales_orders[0].docstatus, 0)
		self.assertFalse(sales_orders[0].co_fulfillment_type)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
