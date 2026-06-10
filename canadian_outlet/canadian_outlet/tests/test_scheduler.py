# Phase 24 tests — the two approved scheduled jobs. Fail-closed: both no-op
# while kill switches are off; one failing channel never blocks the others.
# Network fetches are mocked; everything else runs the real pipeline.

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

WOO = "CO-Test-Sched-Woo"
AMZ = "CO-Test-Sched-Amz"

WOO_PAYLOAD = {
	"id": 9101,
	"status": "processing",
	"total": "10.00",
	"date_created_gmt": "2026-01-07T00:00:00",
	"line_items": [{"sku": "SCHED-SKU-1", "quantity": 1, "price": 10}],
}


class TestScheduler(FrappeTestCase):
	def setUp(self):
		from canadian_outlet.co_orders.adapters.woocommerce import setup_woocommerce_channel

		utils.make_channel(WOO, "WooCommerce")
		setup_woocommerce_channel(WOO)
		utils.make_listing(WOO, "SCHED-SKU-1")

	def test_kill_switch_off_means_no_op(self):
		from canadian_outlet.co_core.scheduler import daily_channel_sync

		utils.disable_imports()
		# Fetch must never even be attempted while disabled.
		with patch(
			"canadian_outlet.co_orders.adapters.woocommerce.fetch_orders",
			side_effect=AssertionError("fetch attempted while imports disabled"),
		):
			result = daily_channel_sync()
		self.assertEqual(result, {"skipped": "imports_disabled"})
		self.assertEqual(utils.get_sales_orders(WOO, "9999"), [])

	def test_enabled_sync_imports_through_shared_pipeline(self):
		from canadian_outlet.co_core.scheduler import daily_channel_sync

		utils.enable_imports()
		payload = dict(WOO_PAYLOAD, currency=utils.default_currency())
		with patch(
			"canadian_outlet.co_orders.adapters.woocommerce.fetch_orders",
			return_value=[payload],
		):
			result = daily_channel_sync()

		self.assertEqual(result[WOO]["created"], 1)
		sales_orders = utils.get_sales_orders(WOO, "9101")
		self.assertEqual(len(sales_orders), 1)
		self.assertEqual(sales_orders[0].co_fulfillment_type, "SELF")

	def test_one_failing_channel_does_not_block_others(self):
		from canadian_outlet.co_core.scheduler import daily_channel_sync

		utils.make_channel(AMZ, "Amazon")
		utils.enable_imports()
		payload = dict(WOO_PAYLOAD, id=9102, currency=utils.default_currency())
		with patch(
			"canadian_outlet.co_orders.adapters.woocommerce.fetch_orders",
			return_value=[payload],
		), patch(
			"canadian_outlet.co_orders.adapters.amazon.get_access_token",
			side_effect=Exception("synthetic LWA outage"),
		):
			result = daily_channel_sync()

		self.assertEqual(result[AMZ], {"error": "logged"})
		self.assertEqual(result[WOO]["created"], 1)

	def test_weekly_purge_runs(self):
		from canadian_outlet.co_core.scheduler import weekly_retention_purge

		result = weekly_retention_purge()
		self.assertIn("purged", result)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
