# T-RES-1..5 (docs/TEST-PLAN.md) — INV-1, INV-2, INV-3, INV-4, INV-10.
# Written before implementation (Phase 7); exercises the Phase 8 resolver and
# the Phase 10/11 import pipeline.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Woo-Resolution"


class TestItemResolution(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL)
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def test_t_res_1_known_listing_resolves_to_mapped_item(self):
		# T-RES-1 (INV-2, INV-3)
		from canadian_outlet.co_catalog.resolution import resolve_external_identity

		utils.make_listing(CHANNEL, "EXT-SKU-RES1")
		self.assertEqual(resolve_external_identity(CHANNEL, "EXT-SKU-RES1"), utils.TEST_ITEM)

	def test_t_res_2_unknown_identity_creates_resolution_exception(self):
		# T-RES-2 (INV-4)
		from canadian_outlet.co_orders.import_service import import_order

		order = utils.make_order(
			CHANNEL, "ORD-RES2", lines=[{"external_identity": "EXT-UNKNOWN-RES2", "qty": 1, "rate": 5}]
		)
		result = import_order(order)
		self.assertEqual(result.outcome, "Exception")
		exceptions = utils.get_exceptions(CHANNEL, "ORD-RES2", failure_stage="Resolution")
		self.assertEqual(len(exceptions), 1)
		self.assertEqual(exceptions[0].status, "Open")

	def test_t_res_3_unknown_identity_does_not_create_item(self):
		# T-RES-3 (INV-1, INV-4)
		from canadian_outlet.co_orders.import_service import import_order

		item_count_before = frappe.db.count("Item")
		order = utils.make_order(
			CHANNEL, "ORD-RES3", lines=[{"external_identity": "EXT-UNKNOWN-RES3", "qty": 1, "rate": 5}]
		)
		import_order(order)
		self.assertEqual(frappe.db.count("Item"), item_count_before)
		self.assertFalse(frappe.db.exists("Item", "EXT-UNKNOWN-RES3"))

	def test_t_res_4_inactive_listing_fails_closed(self):
		# T-RES-4 (INV-2, INV-10)
		from canadian_outlet.co_catalog.resolution import (
			UnresolvedListingError,
			resolve_external_identity,
		)
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-RES4", status="Inactive")
		with self.assertRaises(UnresolvedListingError):
			resolve_external_identity(CHANNEL, "EXT-SKU-RES4")

		order = utils.make_order(
			CHANNEL, "ORD-RES4", lines=[{"external_identity": "EXT-SKU-RES4", "qty": 1, "rate": 5}]
		)
		result = import_order(order)
		self.assertEqual(result.outcome, "Exception")

	def test_t_res_5_item_code_match_without_listing_fails_closed(self):
		# T-RES-5 (INV-2): no convention-based resolution — an external identity
		# equal to an existing item_code must NOT resolve without a listing.
		from canadian_outlet.co_catalog.resolution import (
			UnresolvedListingError,
			resolve_external_identity,
		)

		self.assertTrue(frappe.db.exists("Item", utils.TEST_ITEM))
		with self.assertRaises(UnresolvedListingError):
			resolve_external_identity(CHANNEL, utils.TEST_ITEM)
