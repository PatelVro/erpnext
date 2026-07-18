# C5 + C6 tests (FLOW-DECISIONS D9/D4, BUILD-CHANGE-PLAN C5/C6).
# C5: taxes per order; the invoice rides the deduction heartbeat behind
# switch ④. C6: At-FBA is real ledger stock — inbound transfers in, FBA
# sales deduct it, true-up corrects it; the shelf is never touched.

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-C56"


def _actual(item_code, warehouse):
	return flt(frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
	))


class TestC5Invoicing(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		frappe.db.set_single_value("Canadian Outlet Settings", "auto_invoice_on_shipment", 0)

	def _import(self, order_id, qty=2, tax_total=3.25):
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-" + order_id)
		result = import_order(
			utils.make_order(
				CHANNEL, order_id,
				lines=[{"external_identity": "EXT-SKU-" + order_id, "qty": qty, "rate": 10}],
				tax_total=tax_total,
			)
		)
		so = frappe.get_doc("Sales Order", result.sales_order)
		if so.items[0].warehouse:
			make_stock_entry(item_code=utils.TEST_ITEM, target=so.items[0].warehouse,
				qty=qty + 10, basic_rate=1, company=so.company)
		return so

	def _ship(self, order_id, qty):
		from canadian_outlet.co_shipping.shipstation import record_shipment_event, translate_shipment

		return record_shipment_event(translate_shipment(CHANNEL, {
			"orderNumber": order_id, "carrierCode": "canada_post",
			"trackingNumber": "TRACK-" + order_id, "shipDate": "2026-01-10", "voided": False,
			"shipmentItems": [{"sku": "EXT-SKU-" + order_id, "quantity": qty}],
		}))

	def test_order_tax_lands_on_the_order(self):
		# D9: taxes per order, as the channel charged them.
		so = self._import("ORD-C5A", qty=2, tax_total=3.25)
		self.assertEqual(len(so.taxes), 1)
		self.assertEqual(flt(so.taxes[0].tax_amount), 3.25)
		self.assertEqual(flt(so.grand_total), flt(so.net_total) + 3.25)

	def test_tax_without_account_fails_closed(self):
		from canadian_outlet.co_orders.import_service import import_order

		frappe.db.set_single_value("Canadian Outlet Settings", "marketplace_tax_account", None)
		utils.make_listing(CHANNEL, "EXT-SKU-ORD-C5B")
		result = import_order(
			utils.make_order(
				CHANNEL, "ORD-C5B",
				lines=[{"external_identity": "EXT-SKU-ORD-C5B", "qty": 1, "rate": 10}],
				tax_total=1.5,
			)
		)
		self.assertEqual(result.outcome, "Exception")
		self.assertEqual(utils.get_sales_orders(CHANNEL, "ORD-C5B"), [])

	def test_switch_off_no_invoice_on_deduction(self):
		so = self._import("ORD-C5C")
		self._ship("ORD-C5C", 2)
		self.assertFalse(frappe.db.exists(
			"Sales Invoice Item", {"sales_order": so.name, "docstatus": ("<", 2)}
		))

	def test_switch_on_invoice_rides_the_deduction(self):
		frappe.db.set_single_value("Canadian Outlet Settings", "auto_invoice_on_shipment", 1)
		so = self._import("ORD-C5D", qty=2, tax_total=2.0)
		self._ship("ORD-C5D", 2)

		invoice_name = frappe.db.get_value(
			"Sales Invoice Item", {"sales_order": so.name, "docstatus": 1}, "parent"
		)
		self.assertTrue(invoice_name)
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		self.assertEqual(invoice.docstatus, 1)  # submitted in the same heartbeat
		self.assertEqual(flt(invoice.total_taxes_and_charges), 2.0)

	def test_invoice_failure_never_undoes_the_deduction(self):
		frappe.db.set_single_value("Canadian Outlet Settings", "auto_invoice_on_shipment", 1)
		so = self._import("ORD-C5E")
		errors_before = frappe.db.count("Error Log")
		with patch(
			"canadian_outlet.co_billing.invoice_service.create_invoice_for_delivery",
			side_effect=frappe.ValidationError("synthetic invoice failure"),
		):
			self._ship("ORD-C5E", 2)

		self.assertGreater(frappe.db.count("Error Log"), errors_before)
		# The deduction stands.
		self.assertEqual(
			flt(frappe.db.get_value("Sales Order Item", {"parent": so.name}, "delivered_qty")), 2
		)


class TestC6Fba(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "Amazon")
		utils.make_rule(CHANNEL, "fulfillment_channel", "AFN", "FBA")
		utils.enable_imports()  # deterministic shelf (utils.shelf_warehouse)
		self.company = frappe.defaults.get_global_default("company")
		self.fba = self._ensure_fba_warehouse()
		frappe.db.set_single_value("Canadian Outlet Settings", "fba_warehouse", self.fba)

	def _ensure_fba_warehouse(self):
		existing = frappe.db.get_value(
			"Warehouse", {"warehouse_name": "At Amazon FBA", "company": self.company}
		)
		if existing:
			return existing
		return frappe.get_doc({
			"doctype": "Warehouse", "warehouse_name": "At Amazon FBA", "company": self.company,
		}).insert(ignore_permissions=True).name

	def test_inbound_transfer_moves_shelf_to_fba_idempotently(self):
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_inventory.fba import record_fba_inbound

		shelf = frappe.db.get_single_value("Canadian Outlet Settings", "default_warehouse")
		make_stock_entry(item_code=utils.TEST_ITEM, target=shelf, qty=30, basic_rate=1,
			company=self.company)
		shelf_before = _actual(utils.TEST_ITEM, shelf)
		fba_before = _actual(utils.TEST_ITEM, self.fba)

		record_fba_inbound("FBA-INB-001", {utils.TEST_ITEM: 10})
		self.assertEqual(_actual(utils.TEST_ITEM, shelf), shelf_before - 10)
		self.assertEqual(_actual(utils.TEST_ITEM, self.fba), fba_before + 10)

		self.assertRaises(
			frappe.ValidationError, record_fba_inbound, "FBA-INB-001", {utils.TEST_ITEM: 10}
		)

	def test_fba_sale_deducts_at_fba_never_the_shelf(self):
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry
		from canadian_outlet.co_orders.import_service import import_order

		shelf = frappe.db.get_single_value("Canadian Outlet Settings", "default_warehouse")
		make_stock_entry(item_code=utils.TEST_ITEM, target=self.fba, qty=20, basic_rate=1,
			company=self.company)
		shelf_before = _actual(utils.TEST_ITEM, shelf)
		fba_before = _actual(utils.TEST_ITEM, self.fba)

		utils.make_listing(CHANNEL, "EXT-SKU-C6B")
		result = import_order(
			utils.make_order(
				CHANNEL, "ORD-C6B",
				lines=[{"external_identity": "EXT-SKU-C6B", "qty": 3, "rate": 10}],
				evidence=dict(utils.AMAZON_AFN_EVIDENCE),
			)
		)
		self.assertEqual(result.outcome, "Created")
		self.assertEqual(_actual(utils.TEST_ITEM, self.fba), fba_before - 3)
		self.assertEqual(_actual(utils.TEST_ITEM, shelf), shelf_before)

	def test_unmodeled_fba_is_a_no_op(self):
		from canadian_outlet.co_orders.import_service import import_order

		frappe.db.set_single_value("Canadian Outlet Settings", "fba_warehouse", None)
		se_before = frappe.db.count("Stock Entry")
		utils.make_listing(CHANNEL, "EXT-SKU-C6C")
		result = import_order(
			utils.make_order(
				CHANNEL, "ORD-C6C",
				lines=[{"external_identity": "EXT-SKU-C6C", "qty": 1, "rate": 10}],
				evidence=dict(utils.AMAZON_AFN_EVIDENCE),
			)
		)
		self.assertEqual(result.outcome, "Created")
		self.assertEqual(frappe.db.count("Stock Entry"), se_before)

	def test_true_up_sets_fba_count(self):
		from canadian_outlet.co_inventory.fba import true_up_fba

		true_up_fba({utils.TEST_ITEM: 42})
		self.assertEqual(_actual(utils.TEST_ITEM, self.fba), 42)

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
