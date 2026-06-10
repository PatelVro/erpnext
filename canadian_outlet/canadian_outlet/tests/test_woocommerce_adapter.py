# Phase 13 tests — WooCommerce adapter. Translation and end-to-end through
# the shared Order Import Service with synthetic payloads only; no network.
# WooCommerce -> SELF (INV-5), unknown SKU -> Integration Exception (INV-4),
# no Woo-specific Sales Order path (INV-9).

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Woo-Adapter"

SYNTHETIC_WOO_PAYLOAD = {
	"id": 7001,
	"status": "processing",
	"currency": "CAD",
	"total": "25.00",
	"total_tax": "3.25",
	"date_created_gmt": "2026-01-02T03:04:05",
	"billing": {
		"first_name": "Synthetic",
		"last_name": "Testbuyer",
		"email": "synthetic.woo@example.invalid",
		"phone": "+1-555-0199-TEST",
		"address_1": "456 Synthetic Test Avenue",
	},
	"shipping": {"address_1": "456 Synthetic Test Avenue", "city": "Testville"},
	"line_items": [
		{"sku": "WOO-SKU-1", "quantity": 2, "price": 12.5, "name": "Synthetic Product"}
	],
}


class TestWooCommerceAdapter(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.enable_imports()

	def test_setup_creates_self_rule_as_data(self):
		from canadian_outlet.co_orders.adapters.woocommerce import setup_woocommerce_channel

		setup_woocommerce_channel(CHANNEL)
		fulfillment_type = frappe.db.get_value(
			"Channel Fulfillment Map",
			{"channel": CHANNEL, "evidence_key": "channel_source", "evidence_value": "woocommerce"},
			"fulfillment_type",
		)
		self.assertEqual(fulfillment_type, "SELF")
		setup_woocommerce_channel(CHANNEL)  # idempotent

	def test_translation_carries_no_buyer_pii(self):
		from canadian_outlet.co_orders.adapters.woocommerce import translate_order

		order = translate_order(CHANNEL, SYNTHETIC_WOO_PAYLOAD)
		self.assertEqual(order["channel_order_id"], "7001")
		self.assertEqual(order["evidence"], {"channel_source": "woocommerce"})
		self.assertEqual(
			order["lines"], [{"external_identity": "WOO-SKU-1", "qty": 2.0, "rate": 12.5}]
		)
		order_text = json.dumps(order)
		for pii in ("Testbuyer", "synthetic.woo@example.invalid", "+1-555-0199-TEST",
				"456 Synthetic Test Avenue"):
			self.assertNotIn(pii, order_text)

	def test_end_to_end_known_sku_creates_self_sales_order(self):
		from canadian_outlet.co_orders.adapters.woocommerce import (
			setup_woocommerce_channel,
			translate_order,
		)
		from canadian_outlet.co_orders.import_service import import_order

		setup_woocommerce_channel(CHANNEL)
		utils.make_listing(CHANNEL, "WOO-SKU-1")
		result = import_order(translate_order(CHANNEL, SYNTHETIC_WOO_PAYLOAD))

		self.assertEqual(result.outcome, "Created")
		sales_orders = utils.get_sales_orders(CHANNEL, "7001")
		self.assertEqual(len(sales_orders), 1)
		self.assertEqual(sales_orders[0].co_fulfillment_type, "SELF")
		self.assertEqual(sales_orders[0].docstatus, 0)

	def test_end_to_end_unknown_sku_fails_closed(self):
		from canadian_outlet.co_orders.adapters.woocommerce import (
			setup_woocommerce_channel,
			translate_order,
		)
		from canadian_outlet.co_orders.import_service import import_order

		setup_woocommerce_channel(CHANNEL)
		payload = dict(SYNTHETIC_WOO_PAYLOAD, id=7002,
			line_items=[{"sku": "WOO-SKU-UNMAPPED", "quantity": 1, "price": 5}])
		result = import_order(translate_order(CHANNEL, payload))

		self.assertEqual(result.outcome, "Exception")
		self.assertEqual(utils.get_sales_orders(CHANNEL, "7002"), [])
		self.assertFalse(frappe.db.exists("Item", "WOO-SKU-UNMAPPED"))

	def test_empty_sku_fails_closed_not_guessed(self):
		from canadian_outlet.co_orders.adapters.woocommerce import (
			setup_woocommerce_channel,
			translate_order,
		)
		from canadian_outlet.co_orders.import_service import import_order

		setup_woocommerce_channel(CHANNEL)
		payload = dict(SYNTHETIC_WOO_PAYLOAD, id=7003,
			line_items=[{"sku": "", "quantity": 1, "price": 5, "name": "Nameless Product"}])
		result = import_order(translate_order(CHANNEL, payload))

		self.assertEqual(result.outcome, "Exception")
		self.assertEqual(utils.get_sales_orders(CHANNEL, "7003"), [])

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
