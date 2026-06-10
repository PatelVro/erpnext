# Phase 22 tests — the three operational reports. Reports are read-only data
# functions; tests call execute() directly (no UI involved).

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Reports"


class TestReports(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def _import(self, order_id, known=True):
		from canadian_outlet.co_orders.import_service import import_order

		if known:
			utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		return import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": 1, "rate": 5}],
			)
		)

	def test_channel_sales_summary(self):
		from canadian_outlet.canadian_outlet.report.channel_sales_summary.channel_sales_summary import execute

		self._import("ORD-REP1")
		self._import("ORD-REP2")
		columns, rows = execute({"channel": CHANNEL})
		self.assertTrue(columns)
		match = [r for r in rows if r.channel == CHANNEL and r.fulfillment_type == "SELF"]
		self.assertEqual(len(match), 1)
		self.assertEqual(match[0].orders, 2)

	def test_integration_exception_aging(self):
		from canadian_outlet.canadian_outlet.report.integration_exception_aging.integration_exception_aging import execute

		self._import("ORD-REP3", known=False)  # unknown listing -> Open exception
		columns, rows = execute({"channel": CHANNEL})
		match = [r for r in rows if r["channel_order_id"] == "ORD-REP3"]
		self.assertEqual(len(match), 1)
		self.assertEqual(match[0]["status"], "Open")
		self.assertEqual(match[0]["failure_stage"], "Resolution")
		self.assertGreaterEqual(match[0]["age_days"], 0)

	def test_channel_listing_health(self):
		from canadian_outlet.canadian_outlet.report.channel_listing_health.channel_listing_health import execute

		utils.make_listing(CHANNEL, "EXT-HEALTHY")
		utils.make_listing(CHANNEL, "EXT-INACTIVE", status="Inactive")
		columns, rows = execute({"channel": CHANNEL, "only_attention": 1})
		identities = [r["external_identity"] for r in rows]
		self.assertIn("EXT-INACTIVE", identities)
		self.assertNotIn("EXT-HEALTHY", identities)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
