# C7 + C8 tests (FLOW-DECISIONS D6/D10, BUILD-CHANGE-PLAN C7/C8).
# C7: instant STOP emails, daily digest, 3-day escalation. C8: the big red
# button — stock and money frozen, intake continues into quarantine (INV-13).

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-C78"
RECIPIENT = "ops@canadianoutlet.invalid"


class TestC7Notifications(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "safe_mode", 0)
		frappe.db.set_single_value("Canadian Outlet Settings", "notification_email", RECIPIENT)

	def _sent(self, capture):
		return [call.kwargs.get("subject") or call.args[1] for call in capture.call_args_list]

	def test_stop_creates_instant_email(self):
		from canadian_outlet.co_orders.import_service import import_order

		with patch("canadian_outlet.co_core.notifications.frappe.sendmail") as sendmail:
			result = import_order(
				utils.make_order(
					CHANNEL, "ORD-C7A",
					lines=[{"external_identity": "C7-UNMAPPED", "qty": 1, "rate": 5}],
				)
			)
		self.assertEqual(result.outcome, "Exception")
		subjects = self._sent(sendmail)
		self.assertTrue(any("[CO STOP]" in s for s in subjects), subjects)
		self.assertEqual(sendmail.call_args.kwargs["recipients"], [RECIPIENT])

	def test_digest_and_escalation(self):
		from canadian_outlet.co_core.notifications import daily_review_digest
		from canadian_outlet.co_orders.import_service import import_order

		with patch("canadian_outlet.co_core.notifications.frappe.sendmail"):
			stuck = import_order(
				utils.make_order(
					CHANNEL, "ORD-C7B",
					lines=[{"external_identity": "C7-UNMAPPED-B", "qty": 1, "rate": 5}],
				)
			)
		# Backdate it past the escalation window.
		frappe.db.set_value("Integration Exception", stuck.integration_exception,
			"creation", add_days(now_datetime(), -4), update_modified=False)

		with patch("canadian_outlet.co_core.notifications.frappe.sendmail") as sendmail:
			summary = daily_review_digest()

		self.assertGreaterEqual(summary["open_exceptions"], 1)
		self.assertGreaterEqual(summary["escalations"], 1)
		subjects = self._sent(sendmail)
		self.assertTrue(any("[CO DAILY]" in s for s in subjects), subjects)
		self.assertTrue(any("[CO ESCALATION]" in s for s in subjects), subjects)

	def test_no_recipient_means_quiet_skip(self):
		from canadian_outlet.co_core.notifications import daily_review_digest
		from canadian_outlet.co_orders.import_service import import_order

		frappe.db.set_single_value("Canadian Outlet Settings", "notification_email", None)
		with patch("canadian_outlet.co_core.notifications.frappe.sendmail") as sendmail:
			import_order(
				utils.make_order(
					CHANNEL, "ORD-C7C",
					lines=[{"external_identity": "C7-UNMAPPED-C", "qty": 1, "rate": 5}],
				)
			)
			daily_review_digest()
		sendmail.assert_not_called()


class TestC8SafeMode(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL, "WooCommerce")
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()
		frappe.db.set_single_value("Canadian Outlet Settings", "deduct_on_shipped_event", 1)
		frappe.db.set_single_value("Canadian Outlet Settings", "safe_mode", 1)

	def tearDown(self):
		frappe.db.set_single_value("Canadian Outlet Settings", "safe_mode", 0)
		super().tearDown()

	def test_intake_continues_into_quarantine(self):
		# INV-13: a perfectly classifiable SELF order still arrives quarantined.
		from canadian_outlet.co_orders.import_service import import_order

		utils.make_listing(CHANNEL, "EXT-SKU-C8A")
		result = import_order(
			utils.make_order(
				CHANNEL, "ORD-C8A",
				lines=[{"external_identity": "EXT-SKU-C8A", "qty": 2, "rate": 10}],
			)
		)
		self.assertEqual(result.outcome, "Created")
		self.assertTrue(result.quarantined)
		so = frappe.get_doc("Sales Order", result.sales_order)
		self.assertEqual(so.docstatus, 0)
		self.assertEqual(so.co_quarantined, 1)

	def test_nothing_converts_or_releases_while_frozen(self):
		from canadian_outlet.co_orders.import_service import import_order
		from canadian_outlet.co_orders.quarantine import classify_quarantined_order
		from canadian_outlet.co_shipping.shipstation import (
			process_shipment_event,
			record_shipment_event,
			translate_shipment,
		)

		utils.make_listing(CHANNEL, "EXT-SKU-C8B")
		result = import_order(
			utils.make_order(
				CHANNEL, "ORD-C8B",
				lines=[{"external_identity": "EXT-SKU-C8B", "qty": 1, "rate": 10}],
			)
		)
		# Release is frozen.
		self.assertRaises(
			frappe.ValidationError, classify_quarantined_order, result.sales_order, "SELF"
		)
		# Shipped events record but never convert.
		dn_before = frappe.db.count("Delivery Note")
		event = record_shipment_event(translate_shipment(CHANNEL, {
			"orderNumber": "ORD-C8B", "carrierCode": "canada_post",
			"trackingNumber": "TRACK-C8B", "shipDate": "2026-01-11", "voided": False,
			"shipmentItems": [{"sku": "EXT-SKU-C8B", "quantity": 1}],
		}))
		self.assertTrue(frappe.db.exists("Shipment Status Event", event))
		self.assertIsNone(process_shipment_event(event))
		self.assertEqual(frappe.db.count("Delivery Note"), dn_before)

	def test_money_surfaces_are_frozen(self):
		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery
		from canadian_outlet.co_billing.payment_service import record_payment_for_invoice

		self.assertRaises(frappe.ValidationError, create_invoice_for_delivery, "DN-ANY")
		self.assertRaises(frappe.ValidationError, record_payment_for_invoice, "SI-ANY")

	def test_switch_off_releases_normally(self):
		from canadian_outlet.co_orders.import_service import import_order
		from canadian_outlet.co_orders.quarantine import classify_quarantined_order

		utils.make_listing(CHANNEL, "EXT-SKU-C8C")
		result = import_order(
			utils.make_order(
				CHANNEL, "ORD-C8C",
				lines=[{"external_identity": "EXT-SKU-C8C", "qty": 1, "rate": 10}],
			)
		)
		frappe.db.set_single_value("Canadian Outlet Settings", "safe_mode", 0)
		classify_quarantined_order(result.sales_order, "SELF")
		so = frappe.get_doc("Sales Order", result.sales_order)
		self.assertEqual(so.docstatus, 1)
		self.assertEqual(so.co_fulfillment_type, "SELF")

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
