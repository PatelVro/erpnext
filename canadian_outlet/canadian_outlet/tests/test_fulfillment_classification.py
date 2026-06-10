# T-FUL-1..4 (docs/TEST-PLAN.md) — INV-5, INV-6, INV-10.
# Written before implementation (Phase 7); exercises the Phase 9 classifier and
# the Phase 10/11 import pipeline.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

WOO = "CO-Test-Woo-Classify"
AMZ = "CO-Test-Amazon-Classify"
WMT = "CO-Test-Walmart-Classify"


class TestFulfillmentClassification(FrappeTestCase):
	def setUp(self):
		utils.make_channel(WOO, "WooCommerce")
		utils.make_channel(AMZ, "Amazon")
		utils.make_channel(WMT, "Walmart")
		utils.make_rule(WOO, "channel_source", "woocommerce", "SELF")
		utils.make_rule(AMZ, "fulfillment_channel", "AFN", "FBA")
		utils.make_rule(AMZ, "fulfillment_channel", "MFN", "SELF")
		utils.make_rule(WMT, "ship_node_type", "WFSFulfilled", "WFS")
		utils.make_rule(WMT, "ship_node_type", "SellerFulfilled", "SELF")
		utils.enable_imports()

	def test_t_ful_1_mapped_evidence_classifies_correctly(self):
		# T-FUL-1 (INV-5): the five baseline rules.
		from canadian_outlet.co_orders.classification import classify_fulfillment

		self.assertEqual(classify_fulfillment(WOO, utils.WOO_EVIDENCE), "SELF")
		self.assertEqual(classify_fulfillment(AMZ, utils.AMAZON_AFN_EVIDENCE), "FBA")
		self.assertEqual(classify_fulfillment(AMZ, utils.AMAZON_MFN_EVIDENCE), "SELF")
		self.assertEqual(classify_fulfillment(WMT, utils.WALMART_WFS_EVIDENCE), "WFS")
		self.assertEqual(classify_fulfillment(WMT, utils.WALMART_SELLER_EVIDENCE), "SELF")

	def test_t_ful_2_unmapped_evidence_blocks_import(self):
		# T-FUL-2 (INV-5, INV-6, INV-10)
		from canadian_outlet.co_orders.classification import classify_fulfillment
		from canadian_outlet.co_orders.import_service import import_order

		self.assertEqual(
			classify_fulfillment(AMZ, {"fulfillment_channel": "SOMETHING-NEW"}), "UNKNOWN"
		)
		self.assertEqual(classify_fulfillment(AMZ, {}), "UNKNOWN")

		utils.make_listing(AMZ, "EXT-SKU-FUL2")
		order = utils.make_order(
			AMZ,
			"ORD-FUL2",
			lines=[{"external_identity": "EXT-SKU-FUL2", "qty": 1, "rate": 5}],
			evidence={"fulfillment_channel": "SOMETHING-NEW"},
		)
		result = import_order(order)
		# C3 (FLOW-DECISIONS D3): unclear fulfillment imports QUARANTINED —
		# a real draft order that holds nothing — instead of being blocked.
		self.assertEqual(result.outcome, "Created")
		self.assertTrue(result.quarantined)
		sales_orders = utils.get_sales_orders(AMZ, "ORD-FUL2")
		self.assertEqual(sales_orders[0].docstatus, 0)
		self.assertFalse(sales_orders[0].co_fulfillment_type)

	def test_t_ful_2b_contradictory_evidence_is_unknown(self):
		# INV-5: contradictory matches fail closed, exactly like no match.
		# Two evidence keys each match a rule, but the rules disagree.
		from canadian_outlet.co_orders.classification import classify_fulfillment

		utils.make_rule(AMZ, "secondary_flag", "ALSO-WFS", "WFS")
		evidence = {"fulfillment_channel": "AFN", "secondary_flag": "ALSO-WFS"}
		self.assertEqual(classify_fulfillment(AMZ, evidence), "UNKNOWN")

	def test_t_ful_3_unknown_never_becomes_self(self):
		# T-FUL-3 (INV-5, INV-6)
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(AMZ, "EXT-SKU-FUL3")
		order = utils.make_order(
			AMZ,
			"ORD-FUL3",
			lines=[{"external_identity": "EXT-SKU-FUL3", "qty": 1, "rate": 5}],
			evidence={},
		)
		import_order(order)
		self_orders = frappe.get_all(
			"Sales Order",
			filters={
				"co_sales_channel": AMZ,
				"co_channel_order_id": "ORD-FUL3",
				"co_fulfillment_type": "SELF",
			},
		)
		self.assertEqual(self_orders, [])

	def test_t_ful_4_no_import_path_produces_blank_fulfillment(self):
		# T-FUL-4 (INV-6)
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(WOO, "EXT-SKU-FUL4")
		order = utils.make_order(
			WOO, "ORD-FUL4", lines=[{"external_identity": "EXT-SKU-FUL4", "qty": 1, "rate": 5}]
		)
		result = import_order(order)
		self.assertEqual(result.outcome, "Created")
		sales_orders = utils.get_sales_orders(WOO, "ORD-FUL4")
		self.assertEqual(len(sales_orders), 1)
		self.assertIn(sales_orders[0].co_fulfillment_type, ("SELF", "FBA", "WFS"))

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
