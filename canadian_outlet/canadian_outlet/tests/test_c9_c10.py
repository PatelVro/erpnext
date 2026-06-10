# C9 + C10 tests (FLOW-DECISIONS D9/D4, BUILD-CHANGE-PLAN C9/C10).
# C9: settlement orders matched to invoices become DRAFT Payment Entries —
# human confirms each. C10: the Product-360 report answers the owner's
# weekly questions on one screen.

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-C910"

HEADER = "\t".join(
	["settlement-id", "transaction-type", "order-id", "amount-type", "amount-description", "amount", "posted-date"]
)


def _default_company_bank_account():
	company = frappe.defaults.get_global_default("company")
	existing = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Bank", "is_group": 0}
	)
	if existing:
		return existing
	parent = frappe.db.get_value(
		"Account", {"company": company, "root_type": "Asset", "is_group": 1}
	)
	return frappe.get_doc({
		"doctype": "Account", "account_name": "CO Test Bank", "company": company,
		"parent_account": parent, "account_type": "Bank",
	}).insert(ignore_permissions=True).name


class TestC9SettlementPayments(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "MFN", "SELF")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "safe_mode", 0)
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		frappe.db.set_single_value("Canadian Outlet Settings", "auto_invoice_on_shipment", 1)

	def _shipped_invoiced_order(self, order_id, qty=1):
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_orders.import_service import import_order
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		result = import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": qty, "rate": 30}],
				evidence=dict(utils.AMAZON_MFN_EVIDENCE),
			)
		)
		so = frappe.get_doc("Sales Order", result.sales_order)
		make_stock_entry(item_code=utils.TEST_ITEM, target=so.items[0].warehouse,
			qty=qty + 5, basic_rate=1, company=so.company)
		record_shipment_event(translate_shipment(CHANNEL, {
			"orderNumber": order_id, "carrierCode": "canada_post",
			"trackingNumber": "TRACK-" + order_id, "shipDate": "2026-01-12", "voided": False,
			"shipmentItems": [{"sku": "EXT-SKU-" + order_id, "quantity": qty}],
		}))
		return so

	def test_matched_settlement_stages_draft_payment_once(self):
		from canadian_outlet.co_billing.settlement import confirm_settlement_payments

		so = self._shipped_invoiced_order("ORD-C9A")
		content = "\n".join([
			HEADER,
			"\t".join(["8888", "Order", "ORD-C9A", "ItemPrice", "Principal", "30.00", "2026-01-13"]),
			"\t".join(["8888", "Order", "GHOST-ORDER", "ItemPrice", "Principal", "5.00", "2026-01-13"]),
		])
		result = confirm_settlement_payments(CHANNEL, content, bank_account=_default_company_bank_account())

		self.assertEqual(len(result["payment_drafts"]), 1)
		payment = frappe.get_doc("Payment Entry", result["payment_drafts"][0])
		self.assertEqual(payment.docstatus, 0)  # human confirms
		self.assertIn("Settlement ORD-C9A", payment.reference_no)

		# Idempotent: running the same settlement again reuses the open draft.
		again = confirm_settlement_payments(CHANNEL, content, bank_account=_default_company_bank_account())
		self.assertEqual(again["payment_drafts"], result["payment_drafts"])

	def test_unmatched_and_uninvoiced_rows_are_skipped(self):
		from canadian_outlet.co_billing.settlement import confirm_settlement_payments

		content = "\n".join([
			HEADER,
			"\t".join(["8889", "Order", "NEVER-SEEN", "ItemPrice", "Principal", "9.99", "2026-01-13"]),
		])
		result = confirm_settlement_payments(CHANNEL, content)
		self.assertEqual(result["payment_drafts"], [])
		self.assertEqual(result["skipped_for_payment"], 1)


class TestC10Product360(FrappeTestCase):
	def test_report_answers_the_weekly_questions(self):
		from canadian_outlet.canadian_outlet.report.product_360.product_360 import execute

		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "MFN", "SELF")
		utils.enable_imports()
		utils.make_listing(CHANNEL, "EXT-SKU-P360", utils.TEST_ITEM)

		columns, data = execute({})
		fieldnames = {c["fieldname"] for c in columns}
		self.assertTrue({"shelf_qty", "fba_qty", "available_qty", "channels",
			"sold_30d", "refill"} <= fieldnames)

		row = next(r for r in data if r["item_code"] == utils.TEST_ITEM)
		self.assertIn(CHANNEL, row["channels"])
		self.assertEqual(flt(row["available_qty"]), flt(row["shelf_qty"]) - flt(row["reserved_qty"]))

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
