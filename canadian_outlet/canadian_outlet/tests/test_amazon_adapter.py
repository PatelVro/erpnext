# Phase 15 tests — Amazon adapter. AFN -> FBA, MFN -> SELF, unknown
# fulfillment never SELF (INV-5/6/10); FBA creates no stock documents
# (INV-7). Synthetic payloads only; no network.

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Amazon"

SYNTHETIC_AMAZON_ORDER = {
	"AmazonOrderId": "111-0000001-0000001",
	"OrderStatus": "Unshipped",
	"PurchaseDate": "2026-01-04T05:06:07Z",
	"FulfillmentChannel": "AFN",
	"OrderTotal": {"Amount": "30.00", "CurrencyCode": "USD"},
	"BuyerInfo": {"BuyerEmail": "synthetic.amz@example.invalid", "BuyerName": "Synthetic Buyer"},
	"ShippingAddress": {"AddressLine1": "789 Synthetic Test Road", "City": "Testville"},
}
SYNTHETIC_ORDER_ITEMS = [
	{"SellerSKU": "AMZ-SKU-1", "QuantityOrdered": 2, "ItemPrice": {"Amount": "30.00"}}
]


class TestAmazonAdapter(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.enable_imports()

	def _translated(self, **order_overrides):
		from canadian_outlet.co_orders.adapters.amazon import translate_order

		payload = dict(SYNTHETIC_AMAZON_ORDER, **order_overrides)
		payload["OrderTotal"] = dict(payload["OrderTotal"], CurrencyCode=utils.default_currency())
		return translate_order(CHANNEL, payload, SYNTHETIC_ORDER_ITEMS)

	def test_setup_creates_both_rules_as_data(self):
		from canadian_outlet.co_orders.adapters.amazon import setup_amazon_channel

		setup_amazon_channel(CHANNEL)
		for value, expected in (("AFN", "FBA"), ("MFN", "SELF")):
			self.assertEqual(
				frappe.db.get_value(
					"Channel Fulfillment Map",
					{"channel": CHANNEL, "evidence_key": "fulfillment_channel", "evidence_value": value},
					"fulfillment_type",
				),
				expected,
			)
		setup_amazon_channel(CHANNEL)  # idempotent

	def test_translation_carries_no_buyer_pii(self):
		order = self._translated()
		self.assertEqual(order["channel_order_id"], "111-0000001-0000001")
		self.assertEqual(order["evidence"], {"fulfillment_channel": "AFN"})
		self.assertEqual(order["lines"], [{"external_identity": "AMZ-SKU-1", "qty": 2.0, "rate": 15.0}])
		order_text = json.dumps(order)
		for pii in ("synthetic.amz@example.invalid", "Synthetic Buyer", "789 Synthetic Test Road"):
			self.assertNotIn(pii, order_text)

	def test_afn_imports_as_fba_with_no_stock_documents(self):
		from canadian_outlet.co_orders.adapters.amazon import setup_amazon_channel
		from canadian_outlet.co_orders.import_service import import_order

		setup_amazon_channel(CHANNEL)
		utils.make_listing(CHANNEL, "AMZ-SKU-1")
		dn_before = frappe.db.count("Delivery Note")

		result = import_order(self._translated())
		self.assertEqual(result.outcome, "Created")
		sales_orders = utils.get_sales_orders(CHANNEL, "111-0000001-0000001")
		self.assertEqual(sales_orders[0].co_fulfillment_type, "FBA")
		self.assertEqual(frappe.db.count("Delivery Note"), dn_before)

	def test_mfn_imports_as_self(self):
		from canadian_outlet.co_orders.adapters.amazon import setup_amazon_channel
		from canadian_outlet.co_orders.import_service import import_order

		setup_amazon_channel(CHANNEL)
		utils.make_listing(CHANNEL, "AMZ-SKU-1")
		result = import_order(
			self._translated(AmazonOrderId="111-0000002-0000002", FulfillmentChannel="MFN")
		)
		self.assertEqual(result.outcome, "Created")
		self.assertEqual(
			utils.get_sales_orders(CHANNEL, "111-0000002-0000002")[0].co_fulfillment_type, "SELF"
		)

	def test_unknown_fulfillment_channel_fails_closed_never_self(self):
		from canadian_outlet.co_orders.adapters.amazon import setup_amazon_channel
		from canadian_outlet.co_orders.import_service import import_order

		setup_amazon_channel(CHANNEL)
		utils.make_listing(CHANNEL, "AMZ-SKU-1")
		result = import_order(
			self._translated(AmazonOrderId="111-0000003-0000003", FulfillmentChannel="SOMETHING-NEW")
		)
		self.assertEqual(result.outcome, "Exception")
		self.assertEqual(utils.get_sales_orders(CHANNEL, "111-0000003-0000003"), [])
		exceptions = utils.get_exceptions(
			CHANNEL, "111-0000003-0000003", failure_stage="Classification"
		)
		self.assertEqual(len(exceptions), 1)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
