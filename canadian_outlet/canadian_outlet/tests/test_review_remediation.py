# External-review remediation tests: race-safe idempotency (DB unique index),
# malformed payloads fail closed, adapter pagination, webhook channel
# isolation, auto-submit failure path.

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Remediation"


class TestRaceSafeIdempotency(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def test_unique_index_exists(self):
		from canadian_outlet.install import UNIQUE_CONSTRAINT

		indexes = frappe.db.sql(
			"SHOW INDEX FROM `tabSales Order` WHERE Key_name = %s", UNIQUE_CONSTRAINT
		)
		self.assertTrue(indexes, "DB unique index on (co_sales_channel, co_channel_order_id) missing")

	def test_simulated_race_yields_duplicate_not_double_insert(self):
		# Simulate the TOCTOU window: the pre-check sees nothing (as if a
		# concurrent import had not yet committed), but the unique index
		# rejects the second insert. Outcome must be Duplicate, exactly one
		# Sales Order, no Integration Exception.
		from canadian_outlet.co_orders import import_service
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-RACE")
		order = utils.make_order(
			CHANNEL, "ORD-RACE", lines=[{"external_identity": "EXT-SKU-RACE", "qty": 1, "rate": 5}]
		)
		first = import_order(order)
		self.assertEqual(first.outcome, "Created")

		with patch.object(import_service, "_find_existing_sales_order",
				side_effect=[None, first.sales_order]):
			second = import_order(order)

		self.assertEqual(second.outcome, "Duplicate")
		self.assertEqual(second.sales_order, first.sales_order)
		self.assertEqual(len(utils.get_sales_orders(CHANNEL, "ORD-RACE")), 1)
		self.assertEqual(utils.get_exceptions(CHANNEL, "ORD-RACE"), [])


class TestMalformedPayloads(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()
		utils.make_listing(CHANNEL, "EXT-SKU-MAL")

	def _expect_blocked(self, order_id, lines, **overrides):
		from canadian_outlet.co_orders.import_service import import_order

		item_count = frappe.db.count("Item")
		order = utils.make_order(CHANNEL, order_id, lines=lines, **overrides)
		result = import_order(order)
		self.assertEqual(result.outcome, "Exception")
		self.assertEqual(utils.get_sales_orders(CHANNEL, str(order_id)), [])
		self.assertEqual(frappe.db.count("Item"), item_count)

	def test_missing_and_empty_order_id_fail_closed(self):
		from canadian_outlet.co_orders.import_service import import_order

		for bad_id in ("", None, "None"):
			order = utils.make_order(
				CHANNEL, bad_id, lines=[{"external_identity": "EXT-SKU-MAL", "qty": 1, "rate": 5}]
			)
			result = import_order(order)
			self.assertEqual(result.outcome, "Exception", f"order id {bad_id!r}")

	def test_zero_and_negative_qty_fail_closed(self):
		self._expect_blocked("ORD-MAL-Q0", [{"external_identity": "EXT-SKU-MAL", "qty": 0, "rate": 5}])
		self._expect_blocked("ORD-MAL-QN", [{"external_identity": "EXT-SKU-MAL", "qty": -2, "rate": 5}])
		self._expect_blocked("ORD-MAL-QM", [{"external_identity": "EXT-SKU-MAL", "rate": 5}])

	def test_missing_and_negative_rate_fail_closed(self):
		self._expect_blocked("ORD-MAL-R1", [{"external_identity": "EXT-SKU-MAL", "qty": 1}])
		self._expect_blocked("ORD-MAL-R2", [{"external_identity": "EXT-SKU-MAL", "qty": 1, "rate": -3}])


class TestAdapterPagination(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()
		utils.make_listing(CHANNEL, "WOO-SKU-1")

	def test_woocommerce_imports_all_pages(self):
		from canadian_outlet.co_orders.adapters.woocommerce import import_woocommerce_orders

		def page(order_id):
			return {
				"id": order_id, "status": "processing", "currency": utils.default_currency(),
				"date_created_gmt": "2026-01-07T00:00:00",
				"line_items": [{"sku": "WOO-SKU-1", "quantity": 1, "price": 5}],
			}

		pages = [[page(9201), page(9202)], [page(9203)], []]
		with patch(
			"canadian_outlet.co_orders.adapters.woocommerce.fetch_orders", side_effect=pages
		) as fetched:
			summary = import_woocommerce_orders(CHANNEL)

		self.assertEqual(summary["created"], 3)
		self.assertEqual(fetched.call_count, 3)  # followed until the empty page

	def test_amazon_follows_next_token(self):
		from canadian_outlet.co_orders.adapters import amazon

		amz = "CO-Test-Remediation-AMZ"
		utils.make_channel(amz, "Amazon")
		utils.make_rule(amz, "fulfillment_channel", "MFN", "SELF")
		utils.make_listing(amz, "AMZ-SKU-1")

		def order(oid):
			return {
				"AmazonOrderId": oid, "OrderStatus": "Unshipped",
				"PurchaseDate": "2026-01-07T00:00:00Z", "FulfillmentChannel": "MFN",
				"OrderTotal": {"Amount": "10.00", "CurrencyCode": utils.default_currency()},
			}

		items = [{"SellerSKU": "AMZ-SKU-1", "QuantityOrdered": 1, "ItemPrice": {"Amount": "10.00"}}]
		with patch.object(amazon, "get_access_token", return_value="tok"), patch.object(
			amazon, "fetch_orders",
			side_effect=[([order("901-P1-1")], "TOKEN-2"), ([order("901-P2-1")], None)],
		), patch.object(amazon, "fetch_order_items", return_value=items):
			summary = amazon.import_amazon_orders(amz, created_after="2026-01-05")

		self.assertEqual(summary["created"], 2)

	def test_walmart_follows_next_cursor(self):
		from canadian_outlet.co_orders.adapters import walmart
		from canadian_outlet.tests.test_walmart_adapter import synthetic_walmart_order

		wmt = "CO-Test-Remediation-WMT"
		utils.make_channel(wmt, "Walmart")
		utils.make_rule(wmt, "ship_node_type", "SellerFulfilled", "SELF")
		utils.make_listing(wmt, "WMT-SKU-1")

		currency = utils.default_currency()
		with patch.object(walmart, "get_access_token", return_value="tok"), patch.object(
			walmart, "fetch_orders",
			side_effect=[
				([synthetic_walmart_order("WM-P1-1", "SellerFulfilled", currency)], "CURSOR-2"),
				([synthetic_walmart_order("WM-P2-1", "SellerFulfilled", currency)], None),
			],
		):
			summary = walmart.import_walmart_orders(wmt, created_start_date="2026-01-05")

		self.assertEqual(summary["created"], 2)


class TestWebhookChannelIsolation(FrappeTestCase):
	def test_valid_signature_cannot_target_non_woo_channel(self):
		import base64
		import hashlib
		import hmac
		import json

		from canadian_outlet.co_orders.adapters.woocommerce import handle_webhook

		amz = "CO-Test-Remediation-AMZ2"
		utils.make_channel(amz, "Amazon")
		utils.enable_imports()

		saved = frappe.conf.get("co_woocommerce_webhook_secret")
		frappe.conf["co_woocommerce_webhook_secret"] = "isolation-secret"
		try:
			body = json.dumps({"id": 9301, "line_items": []}).encode()
			signature = base64.b64encode(
				hmac.new(b"isolation-secret", body, hashlib.sha256).digest()
			).decode()
			self.assertRaises(frappe.PermissionError, handle_webhook, amz, body, signature)
			self.assertEqual(utils.get_sales_orders(amz, "9301"), [])
		finally:
			if saved is None:
				frappe.conf.pop("co_woocommerce_webhook_secret", None)
			else:
				frappe.conf["co_woocommerce_webhook_secret"] = saved


class TestDeductionFailurePath(FrappeTestCase):
	def test_failed_deduction_is_logged_and_nothing_moves(self):
		# C2: shipped event arrives with switch ③ ON, but the deduction fails
		# mid-flight — the failure is logged, nothing is deducted, and the
		# event is recorded WITHOUT a delivery_note link so the operator can
		# retry it from the human queue.
		from canadian_outlet.co_orders.import_service import import_order
		from canadian_outlet.co_shipping import shipstation

		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)

		utils.make_listing(CHANNEL, "EXT-SKU-FAILSUB")
		import_order(
			utils.make_order(
				CHANNEL, "ORD-FAILSUB",
				lines=[{"external_identity": "EXT-SKU-FAILSUB", "qty": 1, "rate": 5}],
			)
		)

		error_logs_before = frappe.db.count("Error Log")
		dn_before = frappe.db.count("Delivery Note")
		with patch(
			"canadian_outlet.co_inventory.delivery_note_service.create_delivery_for_shipment",
			side_effect=frappe.ValidationError("synthetic deduction failure"),
		):
			event_name = shipstation.record_shipment_event(
				shipstation.translate_shipment(CHANNEL, {
					"orderNumber": "ORD-FAILSUB", "carrierCode": "canada_post",
					"trackingNumber": "TRACK-FAILSUB", "shipDate": "2026-01-08", "voided": False,
					"shipmentItems": [{"sku": "EXT-SKU-FAILSUB", "quantity": 1}],
				})
			)

		self.assertTrue(frappe.db.exists("Shipment Status Event", event_name))
		self.assertFalse(
			frappe.db.get_value("Shipment Status Event", event_name, "delivery_note")
		)
		self.assertEqual(frappe.db.count("Delivery Note"), dn_before)
		self.assertGreater(frappe.db.count("Error Log"), error_logs_before)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
