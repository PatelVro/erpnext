# T-PII-1..2 (docs/TEST-PLAN.md) — docs/PRIVACY-REDACTION.md: stored payload
# copies are allowlist-only; planted PII appears nowhere in stored records.
# Written before implementation (Phase 7).

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from canadian_outlet.tests import utils

CHANNEL = "CO-Test-Woo-PII"

# Mirrors the allowlist in docs/PRIVACY-REDACTION.md §3.
ALLOWED_TOP_LEVEL_KEYS = {
	"channel",
	"channel_order_id",
	"order_timestamp",
	"channel_status",
	"currency",
	"totals",
	"tax_total",
	"evidence",
	"lines",
}
ALLOWED_LINE_KEYS = {"external_identity", "qty", "rate"}

PLANTED_PII = {
	"name": "Synthetic Q. Testbuyer",
	"email": "synthetic.buyer@example.invalid",
	"phone": "+1-555-0100-TEST",
	"street": "123 Synthetic Test Street",
	"payment_token": "tok_synthetic_test_12345",
}


class TestPayloadPrivacy(FrappeTestCase):
	def setUp(self):
		utils.make_channel(CHANNEL)
		utils.make_rule(CHANNEL, "channel_source", "woocommerce", "SELF")
		utils.enable_imports()

	def _import_failing_order_with_pii(self, order_id):
		from canadian_outlet.co_orders.import_service import import_order

		order = utils.make_order(
			CHANNEL,
			order_id,
			lines=[{"external_identity": "EXT-UNKNOWN-" + order_id, "qty": 1, "rate": 5}],
			buyer={
				"full_name": PLANTED_PII["name"],
				"email": PLANTED_PII["email"],
				"phone": PLANTED_PII["phone"],
				"address": {"street": PLANTED_PII["street"], "city": "Testville"},
				"payment": {"token": PLANTED_PII["payment_token"]},
			},
		)
		return import_order(order)

	def test_t_pii_1_stored_payload_copies_are_allowlist_only(self):
		# T-PII-1 (PRIVACY-REDACTION §2-3, INV-10): unknown/extra payload
		# fields (the buyer block) are stripped, not stored.
		result = self._import_failing_order_with_pii("ORD-PII1")
		self.assertEqual(result.outcome, "Exception")

		exc = frappe.get_doc("Integration Exception", result.integration_exception)
		for raw in (exc.raw_payload_redacted, exc.replay_payload_minimal):
			self.assertTrue(raw)
			payload = json.loads(raw)
			self.assertTrue(set(payload.keys()) <= ALLOWED_TOP_LEVEL_KEYS, payload.keys())
			for line in payload.get("lines", []):
				self.assertTrue(set(line.keys()) <= ALLOWED_LINE_KEYS, line.keys())

	def test_t_pii_2_planted_pii_appears_nowhere_in_stored_records(self):
		# T-PII-2 (PRIVACY-REDACTION §4): name, address, phone, email, payment
		# data absent from the exception (all text fields) and the log row.
		result = self._import_failing_order_with_pii("ORD-PII2")

		exc = frappe.get_doc("Integration Exception", result.integration_exception)
		exception_text = json.dumps(exc.as_dict(), default=str)
		for label, value in PLANTED_PII.items():
			self.assertNotIn(value, exception_text, f"PII leaked into exception: {label}")

		for row in utils.get_log_rows(CHANNEL, "ORD-PII2"):
			log_text = json.dumps(
				frappe.get_doc("Order Import Log", row.name).as_dict(), default=str
			)
			for label, value in PLANTED_PII.items():
				self.assertNotIn(value, log_text, f"PII leaked into log: {label}")

# Frappe test runner: create ERPNext standard test records first.
test_dependencies = ["Company", "Item", "Customer", "Warehouse"]
