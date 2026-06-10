# Phase 12 tests — draft Delivery Note for SELF only (docs/STOCK-FLOW.md §3/§4,
# INV-7, INV-8). Extends the Phase 7 suite.

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-DN"


class TestDraftDeliveryNote(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "MFN", "SELF")
		utils.make_rule(CHANNEL, "fulfillment_channel", "AFN", "FBA")
		utils.enable_imports()

	def _import_submitted_order(self, order_id, evidence):
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		result = import_order(
			utils.make_order(
				CHANNEL,
				order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": 1, "rate": 5}],
				evidence=evidence,
			)
		)
		# C1: imported orders arrive submitted (the hold) — no human submit.
		return frappe.get_doc("Sales Order", result.sales_order)

	def test_self_order_gets_draft_only(self):
		from canadian_outlet.co_inventory.delivery_note_service import create_draft_delivery_note

		so = self._import_submitted_order("ORD-DN1", dict(utils.AMAZON_MFN_EVIDENCE))
		dn_name = create_draft_delivery_note(so.name)
		dn = frappe.get_doc("Delivery Note", dn_name)

		self.assertEqual(dn.docstatus, 0)  # draft, not a deduction (INV-8)
		self.assertEqual(
			frappe.get_all(
				"Stock Ledger Entry",
				filters={"voucher_type": "Delivery Note", "voucher_no": dn_name, "is_cancelled": 0},
			),
			[],
		)

	def test_second_call_is_idempotent(self):
		from canadian_outlet.co_inventory.delivery_note_service import create_draft_delivery_note

		so = self._import_submitted_order("ORD-DN2", dict(utils.AMAZON_MFN_EVIDENCE))
		first = create_draft_delivery_note(so.name)
		second = create_draft_delivery_note(so.name)
		self.assertEqual(first, second)

	def test_fba_order_is_refused(self):
		# INV-7: FBA/WFS never create local stock-deduction documents.
		from canadian_outlet.co_inventory.delivery_note_service import create_draft_delivery_note

		so = self._import_submitted_order("ORD-DN3", dict(utils.AMAZON_AFN_EVIDENCE))
		self.assertEqual(so.co_fulfillment_type, "FBA")
		self.assertRaises(frappe.ValidationError, create_draft_delivery_note, so.name)

	def test_draft_sales_order_is_refused(self):
		# Imports arrive submitted (C1), so the draft case is a manual order.
		from canadian_outlet.co_inventory.delivery_note_service import create_draft_delivery_note

		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": utils.TEST_CUSTOMER,
				"company": utils.TEST_COMPANY,
				"currency": utils.company_currency(),
				"selling_price_list": "_Test Price List",
				"transaction_date": frappe.utils.nowdate(),
				"delivery_date": frappe.utils.nowdate(),
				"co_fulfillment_type": "SELF",
				"items": [
					{
						"item_code": utils.TEST_ITEM,
						"qty": 1,
						"rate": 5,
						"delivery_date": frappe.utils.nowdate(),
					}
				],
			}
		).insert()
		self.assertEqual(so.docstatus, 0)
		self.assertRaises(frappe.ValidationError, create_draft_delivery_note, so.name)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
