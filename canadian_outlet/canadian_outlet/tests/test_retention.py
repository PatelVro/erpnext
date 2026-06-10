# Retention purge tests (docs/PRIVACY-REDACTION.md §5-6). Operator-invoked
# only — no scheduler exists (T-PIPE-1 guards that globally).

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Retention"


class TestRetentionPurge(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def _make_exception(self, order_id):
		from canadian_outlet.co_orders.import_service import import_order

		result = import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": 1, "rate": 5}],
			)
		)
		return result.integration_exception

	def _resolve_and_backdate(self, exc_name, days_ago):
		exc = frappe.get_doc("Integration Exception", exc_name)
		exc.status = "Resolved"
		exc.save(ignore_permissions=True)
		frappe.db.set_value(
			"Integration Exception", exc_name,
			"resolved_or_ignored_on", add_days(now_datetime(), -days_ago),
		)

	def test_expired_terminal_exception_loses_payload_copies_only(self):
		from canadian_outlet.co_core.retention import purge_expired_payload_copies

		exc_name = self._make_exception("ORD-RET1")
		self._resolve_and_backdate(exc_name, days_ago=91)

		result = purge_expired_payload_copies()
		self.assertGreaterEqual(result["purged"], 1)

		exc = frappe.get_doc("Integration Exception", exc_name)
		self.assertFalse(exc.raw_payload_redacted)
		self.assertFalse(exc.replay_payload_minimal)
		# Hash and external reference are retained indefinitely (no PII).
		self.assertTrue(exc.payload_hash)
		self.assertTrue(exc.external_payload_reference)

	def test_recent_terminal_exception_is_kept(self):
		from canadian_outlet.co_core.retention import purge_expired_payload_copies

		exc_name = self._make_exception("ORD-RET2")
		self._resolve_and_backdate(exc_name, days_ago=10)

		purge_expired_payload_copies()
		exc = frappe.get_doc("Integration Exception", exc_name)
		self.assertTrue(exc.raw_payload_redacted)
		self.assertTrue(exc.replay_payload_minimal)

	def test_open_exception_is_never_purged(self):
		from canadian_outlet.co_core.retention import purge_expired_payload_copies

		exc_name = self._make_exception("ORD-RET3")  # stays Open
		purge_expired_payload_copies()
		exc = frappe.get_doc("Integration Exception", exc_name)
		self.assertEqual(exc.status, "Open")
		self.assertTrue(exc.replay_payload_minimal)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
