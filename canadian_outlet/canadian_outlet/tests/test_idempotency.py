# T-IDEM-1..5 (docs/TEST-PLAN.md) — INV-11A, INV-11B, INV-11C, INV-10.
# Written before implementation (Phase 7); exercises the Phase 10/11 import
# pipeline and the replay loop (docs/ORDER-FLOW.md §3).

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Woo-Idem"


class TestIdempotency(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL)
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def test_t_idem_1_duplicate_import_creates_one_sales_order(self):
		# T-IDEM-1 (INV-11A)
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-IDEM1")
		order = utils.make_order(
			CHANNEL, "ORD-IDEM1", lines=[{"external_identity": "EXT-SKU-IDEM1", "qty": 2, "rate": 10}]
		)
		first = import_order(order)
		second = import_order(order)

		self.assertEqual(first.outcome, "Created")
		self.assertEqual(second.outcome, "Duplicate")
		self.assertEqual(len(utils.get_sales_orders(CHANNEL, "ORD-IDEM1")), 1)
		outcomes = sorted(row.outcome for row in utils.get_log_rows(CHANNEL, "ORD-IDEM1"))
		self.assertEqual(outcomes, ["Created", "Duplicate"])

	def test_t_idem_2_reprocessing_never_duplicates_lines(self):
		# T-IDEM-2 (INV-11B)
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-IDEM2")
		order = utils.make_order(
			CHANNEL, "ORD-IDEM2", lines=[{"external_identity": "EXT-SKU-IDEM2", "qty": 3, "rate": 10}]
		)
		import_order(order)
		import_order(order)

		so_name = utils.get_sales_orders(CHANNEL, "ORD-IDEM2")[0].name
		so = frappe.get_doc("Sales Order", so_name)
		self.assertEqual(len(so.items), 1)
		self.assertEqual(so.items[0].qty, 3)

	def test_t_idem_3_repeated_failure_yields_one_open_exception(self):
		# T-IDEM-3 (INV-11C)
		from canadian_outlet.co_orders.import_service import import_order

		order = utils.make_order(
			CHANNEL, "ORD-IDEM3", lines=[{"external_identity": "EXT-UNKNOWN-IDEM3", "qty": 1, "rate": 5}]
		)
		import_order(order)
		import_order(order)

		open_exceptions = utils.get_exceptions(CHANNEL, "ORD-IDEM3", status="Open")
		self.assertEqual(len(open_exceptions), 1)

	def test_t_idem_4_resolved_then_replay_imports_once(self):
		# T-IDEM-4 (INV-11A, INV-11C): Resolved = fix applied; the order counts
		# as imported only when replay succeeds (docs/DATA-MODEL.md §5).
		from canadian_outlet.co_orders.import_service import import_order

		order = utils.make_order(
			CHANNEL, "ORD-IDEM4", lines=[{"external_identity": "EXT-SKU-IDEM4", "qty": 1, "rate": 5}]
		)
		failed = import_order(order)
		self.assertEqual(failed.outcome, "Exception")

		# Human fixes the cause and marks the exception Resolved.
		utils.make_listing(CHANNEL, "EXT-SKU-IDEM4")
		exc = frappe.get_doc("Integration Exception", failed.integration_exception)
		exc.status = "Resolved"
		exc.save()

		# Replay re-enters the pipeline like any other delivery.
		replay = import_order(order)
		self.assertEqual(replay.outcome, "Created")
		self.assertEqual(len(utils.get_sales_orders(CHANNEL, "ORD-IDEM4")), 1)
		exc.reload()
		self.assertEqual(exc.status, "Resolved")

		# Replaying again is a no-op duplicate.
		again = import_order(order)
		self.assertEqual(again.outcome, "Duplicate")
		self.assertEqual(len(utils.get_sales_orders(CHANNEL, "ORD-IDEM4")), 1)

	def test_t_idem_5_ignored_requires_reason(self):
		# T-IDEM-5 (INV-10): runs against the Phase 5 DocType — green already.
		exc = frappe.get_doc(
			{
				"doctype": "Integration Exception",
				"channel": CHANNEL,
				"channel_order_id": "ORD-IDEM5",
				"failure_stage": "Resolution",
				"status": "Ignored",
				"dedup_key": "test-idem5-dedup",
			}
		)
		self.assertRaises(frappe.ValidationError, exc.insert)

		exc.ignored_reason = "Synthetic test payload — intentionally not imported."
		exc.insert()
		self.assertEqual(exc.status, "Ignored")
		self.assertTrue(exc.resolved_or_ignored_on)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
