# C4 tests — suggest-and-confirm, bulk mapping import, fix-and-flow
# (FLOW-DECISIONS D2/D8, BUILD-CHANGE-PLAN C4).

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-C4"


class TestC4Mapping(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def _make_item(self, code, name):
		if not frappe.db.exists("Item", code):
			frappe.get_doc({
				"doctype": "Item", "item_code": code, "item_name": name,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}),
				"stock_uom": "Nos", "is_stock_item": 1,
			}).insert()
		return code

	def test_suggestions_rank_the_plausible_match_first(self):
		self._make_item("IPHONE-13-128GB-OPENBOX", "iPhone 13 128GB Open Box")
		self._make_item("GALAXY-S22-256GB-OPENBOX", "Galaxy S22 256GB Open Box")

		from canadian_outlet.co_catalog.suggestions import suggest_matches

		results = suggest_matches(CHANNEL, "WOO-IPHONE-13-128GB-OB")
		self.assertTrue(results)
		self.assertEqual(results[0]["item_code"], "IPHONE-13-128GB-OPENBOX")
		# Never acts on its own: suggesting creates no listing.
		self.assertFalse(frappe.db.exists(
			"Channel Listing", {"channel": CHANNEL, "external_identity": "WOO-IPHONE-13-128GB-OB"}
		))

	def test_bulk_csv_import_validates_per_row(self):
		from canadian_outlet.co_catalog.bulk_mapping import import_listings_csv

		self._make_item("IPHONE-13-128GB-OPENBOX", "iPhone 13 128GB Open Box")
		utils.make_listing(CHANNEL, "CSV-EXISTING", utils.TEST_ITEM)

		csv_content = "\n".join([
			"sku,item_code",
			"CSV-GOOD-1,IPHONE-13-128GB-OPENBOX",
			f"CSV-GOOD-2,{utils.TEST_ITEM}",
			"CSV-BAD-ITEM,DOES-NOT-EXIST",
			f"CSV-EXISTING,IPHONE-13-128GB-OPENBOX",  # conflicts — not overwritten
			f"CSV-EXISTING,{utils.TEST_ITEM}",        # identical — skipped
			",MISSING-SKU",
		])
		result = import_listings_csv(CHANNEL, csv_content)

		self.assertEqual(result["created"], 2)
		self.assertEqual(result["skipped"], 1)
		self.assertEqual(len(result["rejected"]), 3)
		self.assertEqual(
			frappe.db.get_value(
				"Channel Listing", {"channel": CHANNEL, "external_identity": "CSV-EXISTING"}, "item"
			),
			utils.TEST_ITEM,  # conflict did not overwrite
		)

	def test_fix_and_flow_releases_stuck_orders_on_mapping(self):
		# D8-A: confirming the mapping IS the action — the stuck order imports
		# immediately, no separate replay click.
		from canadian_outlet.co_orders.import_service import import_order

		stuck = import_order(
			utils.make_order(
				CHANNEL, "ORD-C4A",
				lines=[{"external_identity": "C4-UNMAPPED-SKU", "qty": 1, "rate": 5}],
			)
		)
		self.assertEqual(stuck.outcome, "Exception")

		utils.make_listing(CHANNEL, "C4-UNMAPPED-SKU", utils.TEST_ITEM)

		sales_orders = utils.get_sales_orders(CHANNEL, "ORD-C4A")
		self.assertEqual(len(sales_orders), 1)
		self.assertEqual(sales_orders[0].docstatus, 1)
		self.assertEqual(
			frappe.db.get_value("Integration Exception", stuck.integration_exception, "status"),
			"Resolved",
		)

	def test_bulk_import_also_triggers_fix_and_flow(self):
		from canadian_outlet.co_catalog.bulk_mapping import import_listings_csv
		from canadian_outlet.co_orders.import_service import import_order

		stuck = import_order(
			utils.make_order(
				CHANNEL, "ORD-C4B",
				lines=[{"external_identity": "C4-CSV-SKU", "qty": 1, "rate": 5}],
			)
		)
		self.assertEqual(stuck.outcome, "Exception")

		import_listings_csv(CHANNEL, f"C4-CSV-SKU,{utils.TEST_ITEM}")
		self.assertEqual(len(utils.get_sales_orders(CHANNEL, "ORD-C4B")), 1)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
