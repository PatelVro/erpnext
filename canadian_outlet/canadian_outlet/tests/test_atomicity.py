# T-ATOM-1..2 (docs/TEST-PLAN.md) — INV-10: atomic imports, no partial
# Sales Orders, no orphan records. Written before implementation (Phase 7).

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Woo-Atomic"


class TestAtomicity(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL)
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def test_t_atom_1_one_bad_line_means_no_sales_order(self):
		# T-ATOM-1 (INV-10)
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-ATOM1-GOOD")
		order = utils.make_order(
			CHANNEL,
			"ORD-ATOM1",
			lines=[
				{"external_identity": "EXT-SKU-ATOM1-GOOD", "qty": 1, "rate": 10},
				{"external_identity": "EXT-UNKNOWN-ATOM1", "qty": 1, "rate": 20},
			],
		)
		result = import_order(order)

		self.assertEqual(result.outcome, "Exception")
		self.assertEqual(utils.get_sales_orders(CHANNEL, "ORD-ATOM1"), [])
		self.assertEqual(len(utils.get_exceptions(CHANNEL, "ORD-ATOM1")), 1)

	def test_t_atom_2_failed_import_leaves_no_orphans(self):
		# T-ATOM-2 (INV-10)
		from canadian_outlet.co_orders.import_service import import_order

		so_count_before = frappe.db.count("Sales Order")
		customer_count_before = frappe.db.count("Customer")
		item_count_before = frappe.db.count("Item")

		order = utils.make_order(
			CHANNEL,
			"ORD-ATOM2",
			lines=[{"external_identity": "EXT-UNKNOWN-ATOM2", "qty": 1, "rate": 5}],
		)
		import_order(order)

		self.assertEqual(frappe.db.count("Sales Order"), so_count_before)
		self.assertEqual(frappe.db.count("Customer"), customer_count_before)
		self.assertEqual(frappe.db.count("Item"), item_count_before)
