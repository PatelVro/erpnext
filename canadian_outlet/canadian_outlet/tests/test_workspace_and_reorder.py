# Phase 25/26 tests — workspace desk config and the Reorder Status report.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils


class TestWorkspace(FrappeTestCase):
	def test_workspace_exists_and_is_public(self):
		self.assertTrue(frappe.db.exists("Workspace", "Canadian Outlet"))
		ws = frappe.get_doc("Workspace", "Canadian Outlet")
		self.assertEqual(ws.public, 1)
		self.assertIn("Integration Exception", [s.link_to for s in ws.shortcuts])
		self.assertIn("Channel Listing", [l.link_to for l in ws.links if l.type == "Link"])


class TestReorderStatus(FrappeTestCase):
	def test_item_below_reorder_level_is_reported(self):
		from canadian_outlet.canadian_outlet.report.reorder_status.reorder_status import execute

		item = frappe.get_doc("Item", utils.TEST_ITEM)
		# _Test Item's standard records may already carry a reorder row for
		# this warehouse — update it rather than appending a duplicate.
		row = next(
			(
				r for r in item.reorder_levels
				if r.warehouse == utils.TEST_WAREHOUSE and r.material_request_type == "Purchase"
			),
			None,
		)
		if row:
			row.warehouse_reorder_level = 100000
			row.warehouse_reorder_qty = 10
		else:
			item.append(
				"reorder_levels",
				{
					"warehouse": utils.TEST_WAREHOUSE,
					"warehouse_reorder_level": 100000,
					"warehouse_reorder_qty": 10,
					"material_request_type": "Purchase",
				},
			)
		item.save()

		columns, rows = execute({"warehouse": utils.TEST_WAREHOUSE})
		match = [r for r in rows if r.item == utils.TEST_ITEM and r.warehouse == utils.TEST_WAREHOUSE]
		self.assertEqual(len(match), 1)
		self.assertGreater(match[0].shortfall, 0)
		self.assertEqual(match[0].reorder_level, 100000)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
