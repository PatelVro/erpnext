# T-PIPE-1..2 (docs/TEST-PLAN.md) — INV-9, INV-10: one shared Order Import
# Service, no side-channel automation, kill switch fails closed.
# Written before implementation (Phase 7).

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Woo-Pipe"


class TestPipelineExclusivity(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL)
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def test_t_pipe_1_no_side_channel_automation_registered(self):
		# T-PIPE-1 (INV-9): the app registers no document automation and no
		# scheduler; the only order-creation entry point is import_order.
		from canadian_outlet import hooks

		self.assertFalse(getattr(hooks, "doc_events", None))
		self.assertFalse(getattr(hooks, "scheduler_events", None))
		self.assertFalse(getattr(hooks, "override_doctype_class", None))

		from canadian_outlet.co_orders.import_service import import_order

		self.assertTrue(callable(import_order))

	def test_t_pipe_2_kill_switch_and_disabled_channel_fail_closed(self):
		# T-PIPE-2 (INV-9, INV-10): contract — when imports are disabled
		# globally or the channel is disabled, import_order raises
		# ImportsDisabledError and creates nothing (no Sales Order, no log row,
		# no exception flood while operators have deliberately paused imports).
		from canadian_outlet.co_orders.import_service import ImportsDisabledError, import_order

		utils.make_listing(CHANNEL, "EXT-SKU-PIPE2")
		order = utils.make_order(
			CHANNEL, "ORD-PIPE2", lines=[{"external_identity": "EXT-SKU-PIPE2", "qty": 1, "rate": 5}]
		)

		utils.disable_imports()
		with self.assertRaises(ImportsDisabledError):
			import_order(order)
		self.assertEqual(utils.get_sales_orders(CHANNEL, "ORD-PIPE2"), [])
		self.assertEqual(utils.get_log_rows(CHANNEL, "ORD-PIPE2"), [])

		utils.enable_imports()
		frappe.db.set_value("Channel", CHANNEL, "enabled", 0)
		with self.assertRaises(ImportsDisabledError):
			import_order(order)
		self.assertEqual(utils.get_sales_orders(CHANNEL, "ORD-PIPE2"), [])
