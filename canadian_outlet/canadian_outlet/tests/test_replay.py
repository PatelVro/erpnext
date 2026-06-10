# Replay loop tests (docs/ORDER-FLOW.md §3, docs/DATA-MODEL.md §5) —
# INV-11A/C. Replay is operator-invoked; no automation.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Replay"


class TestReplay(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def _fail_order(self, order_id):
		from canadian_outlet.co_orders.import_service import import_order

		result = import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": 1, "rate": 5}],
			)
		)
		self.assertEqual(result.outcome, "Exception")
		return result.integration_exception

	def test_replay_after_fix_imports_and_resolves(self):
		from canadian_outlet.co_orders.replay import replay_exception

		exc_name = self._fail_order("ORD-RPL1")
		# C4 fix-and-flow: creating the mapping imports the order immediately
		# and resolves the exception — no manual replay needed.
		utils.make_listing(CHANNEL, "EXT-SKU-ORD-RPL1")
		self.assertEqual(len(utils.get_sales_orders(CHANNEL, "ORD-RPL1")), 1)
		self.assertEqual(frappe.db.get_value("Integration Exception", exc_name, "status"), "Resolved")

		# Manual replay remains available and is a safe no-op duplicate.
		result = replay_exception(exc_name)
		self.assertEqual(result["outcome"], "Duplicate")
		self.assertEqual(len(utils.get_sales_orders(CHANNEL, "ORD-RPL1")), 1)

	def test_replay_failing_again_after_resolved_marks_failed_replay(self):
		# DATA-MODEL §5: Resolved + replay fails same cause -> Failed Replay.
		from canadian_outlet.co_orders.replay import replay_exception

		exc_name = self._fail_order("ORD-RPL2")
		exc = frappe.get_doc("Integration Exception", exc_name)
		exc.status = "Resolved"  # human believes it is fixed — but it is not
		exc.save(ignore_permissions=True)

		result = replay_exception(exc_name)
		self.assertEqual(result["outcome"], "Exception")
		self.assertEqual(
			frappe.db.get_value("Integration Exception", exc_name, "status"), "Failed Replay"
		)
		self.assertEqual(utils.get_sales_orders(CHANNEL, "ORD-RPL2"), [])

	def test_ignored_exception_is_not_replayable(self):
		from canadian_outlet.co_orders.replay import replay_exception

		exc_name = self._fail_order("ORD-RPL3")
		exc = frappe.get_doc("Integration Exception", exc_name)
		exc.status = "Ignored"
		exc.ignored_reason = "Synthetic test order — intentionally dropped."
		exc.save(ignore_permissions=True)

		self.assertRaises(frappe.ValidationError, replay_exception, exc_name)
		self.assertEqual(utils.get_sales_orders(CHANNEL, "ORD-RPL3"), [])

	def test_replay_without_payload_fails_loudly(self):
		from canadian_outlet.co_orders.replay import replay_exception

		exc_name = self._fail_order("ORD-RPL4")
		frappe.db.set_value("Integration Exception", exc_name, "replay_payload_minimal", None)

		self.assertRaises(frappe.ValidationError, replay_exception, exc_name)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
