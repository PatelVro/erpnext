# Phase 27 tests — read-only Amazon settlement reconciliation. Synthetic
# settlement content in the documented V2 flat-file shape; asserts matching
# and, critically, that reconciliation writes NOTHING.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Settlement"

HEADER = "\t".join(
	["settlement-id", "transaction-type", "order-id", "amount-type", "amount-description", "amount", "posted-date"]
)


def _settlement(order_id):
	lines = [
		HEADER,
		"\t".join(["7777", "", "", "", "TotalAmount", "123.45", "2026-01-10"]),
		"\t".join(["7777", "Order", order_id, "ItemPrice", "Principal", "20.00", "2026-01-10"]),
		"\t".join(["7777", "Order", order_id, "ItemPrice", "Principal", "10.00", "2026-01-10"]),
		"\t".join(["7777", "Order", order_id, "ItemFees", "Commission", "-4.50", "2026-01-10"]),
		"\t".join(["7777", "Order", "999-GHOST-ORDER", "ItemPrice", "Principal", "5.00", "2026-01-10"]),
	]
	return "\n".join(lines)


class TestSettlementReconciliation(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "MFN", "SELF")
		utils.enable_imports()

	def test_settlement_matches_orders_and_writes_nothing(self):
		from canadian_outlet.co_billing.settlement import reconcile_amazon_settlement
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-SETTLE")
		import_order(
			utils.make_order(
				CHANNEL, "111-SETTLE-1",
				lines=[{"external_identity": "EXT-SKU-SETTLE", "qty": 2, "rate": 15}],
				evidence={"fulfillment_channel": "MFN"},
			)
		)

		counts_before = {
			dt: frappe.db.count(dt)
			for dt in ("Payment Entry", "Journal Entry", "Integration Exception", "Sales Invoice")
		}

		result = reconcile_amazon_settlement(CHANNEL, _settlement("111-SETTLE-1"))

		self.assertEqual(result["orders_in_settlement"], 2)
		self.assertEqual(result["matched"], 1)
		self.assertEqual(result["unmatched"], 1)

		by_order = {r["order_id"]: r for r in result["rows"]}
		matched = by_order["111-SETTLE-1"]
		self.assertEqual(matched["status"], "Matched")
		self.assertEqual(matched["settlement_principal"], 30.0)  # principal lines only
		self.assertTrue(matched["sales_order"])
		self.assertEqual(by_order["999-GHOST-ORDER"]["status"], "Unmatched")
		self.assertIsNone(by_order["999-GHOST-ORDER"]["sales_order"])

		# Read-only: nothing was created anywhere.
		for dt, before in counts_before.items():
			self.assertEqual(frappe.db.count(dt), before, dt)

	def test_account_level_rows_are_ignored(self):
		from canadian_outlet.co_billing.settlement import reconcile_amazon_settlement

		content = "\n".join(
			[HEADER, "\t".join(["7777", "", "", "", "TotalAmount", "999.99", "2026-01-10"])]
		)
		result = reconcile_amazon_settlement(CHANNEL, content)
		self.assertEqual(result["orders_in_settlement"], 0)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
