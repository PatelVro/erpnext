# WooCommerce webhook receiver tests. ORDER-FLOW §6 permits a webhook
# transport ONLY when signature verification and idempotency are demonstrated
# by tests first — these are those tests. No network, no scheduler.

import base64
import hashlib
import hmac
import json

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Woo-Webhook"
SECRET = "synthetic-webhook-secret-T-WHK"


def _sign(body, secret=SECRET):
	return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def _payload(order_id):
	return json.dumps(
		{
			"id": order_id,
			"status": "processing",
			"currency": utils.default_currency(),
			"total": "12.50",
			"date_created_gmt": "2026-01-05T00:00:00",
			"billing": {"email": "synthetic.hook@example.invalid"},
			"line_items": [{"sku": "WHK-SKU-1", "quantity": 1, "price": 12.5}],
		}
	).encode()


class TestWooCommerceWebhook(FrappeTestCase):
	def setUp(self):
		from canadian_outlet.co_orders.adapters.woocommerce import setup_woocommerce_channel

		utils.make_channel(CHANNEL, "WooCommerce")
		setup_woocommerce_channel(CHANNEL)
		utils.make_listing(CHANNEL, "WHK-SKU-1")
		utils.enable_imports()
		self._saved = frappe.conf.get("co_woocommerce_webhook_secret")
		frappe.conf["co_woocommerce_webhook_secret"] = SECRET

	def tearDown(self):
		if self._saved is None:
			frappe.conf.pop("co_woocommerce_webhook_secret", None)
		else:
			frappe.conf["co_woocommerce_webhook_secret"] = self._saved
		super().tearDown()

	def test_invalid_signature_is_rejected_and_creates_nothing(self):
		from canadian_outlet.co_orders.adapters.woocommerce import handle_webhook

		body = _payload(8001)
		self.assertRaises(
			frappe.PermissionError, handle_webhook, CHANNEL, body, _sign(body, "wrong-secret")
		)
		self.assertRaises(frappe.PermissionError, handle_webhook, CHANNEL, body, None)
		self.assertEqual(utils.get_sales_orders(CHANNEL, "8001"), [])
		self.assertEqual(utils.get_log_rows(CHANNEL, "8001"), [])

	def test_tampered_body_is_rejected(self):
		from canadian_outlet.co_orders.adapters.woocommerce import handle_webhook

		signature = _sign(_payload(8002))
		tampered = _payload(8002).replace(b'"quantity": 1', b'"quantity": 9')
		self.assertRaises(frappe.PermissionError, handle_webhook, CHANNEL, tampered, signature)

	def test_valid_signature_imports_via_shared_pipeline(self):
		from canadian_outlet.co_orders.adapters.woocommerce import handle_webhook

		body = _payload(8003)
		result = handle_webhook(CHANNEL, body, _sign(body))
		self.assertEqual(result["outcome"], "Created")
		sales_orders = utils.get_sales_orders(CHANNEL, "8003")
		self.assertEqual(len(sales_orders), 1)
		self.assertEqual(sales_orders[0].co_fulfillment_type, "SELF")
		self.assertEqual(sales_orders[0].docstatus, 0)

	def test_duplicate_webhook_is_idempotent(self):
		from canadian_outlet.co_orders.adapters.woocommerce import handle_webhook

		body = _payload(8004)
		first = handle_webhook(CHANNEL, body, _sign(body))
		second = handle_webhook(CHANNEL, body, _sign(body))
		self.assertEqual(first["outcome"], "Created")
		self.assertEqual(second["outcome"], "Duplicate")
		self.assertEqual(len(utils.get_sales_orders(CHANNEL, "8004")), 1)

	def test_missing_secret_fails_loudly(self):
		from canadian_outlet.co_core.settings import MissingConfigError
		from canadian_outlet.co_orders.adapters.woocommerce import handle_webhook

		frappe.conf.pop("co_woocommerce_webhook_secret", None)
		body = _payload(8005)
		self.assertRaises(MissingConfigError, handle_webhook, CHANNEL, body, _sign(body))

	def test_kill_switch_blocks_webhook(self):
		from canadian_outlet.co_orders.adapters.woocommerce import handle_webhook
		from canadian_outlet.co_orders.import_service import ImportsDisabledError

		utils.disable_imports()
		body = _payload(8006)
		self.assertRaises(ImportsDisabledError, handle_webhook, CHANNEL, body, _sign(body))
		self.assertEqual(utils.get_sales_orders(CHANNEL, "8006"), [])

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
