# WooCommerce adapter (Phase 13). Adapters translate channel payloads into the
# canonical normalized order shape and hand them to the shared Order Import
# Service — they make NO business decisions and perform NO Frappe writes
# (INV-9, docs/ORDER-FLOW.md §1). WooCommerce orders carry the constant
# evidence row that classifies to SELF via the Channel Fulfillment Map
# (INV-5; the rule is data, not code).
#
# Transport is operator-triggered only — no scheduler (docs/ORDER-FLOW.md §6).
# Config keys per docs/CONFIGURATION.md §4.2.

import frappe
from frappe import _
from frappe.utils import flt

from canadian_outlet.co_core.settings import get_optional_conf, get_required_conf
from canadian_outlet.co_orders.import_service import import_order

WOO_EVIDENCE_KEY = "channel_source"
WOO_EVIDENCE_VALUE = "woocommerce"
DEFAULT_API_PATH = "/wp-json/wc/v3"
DEFAULT_STATUSES = "processing"


def translate_order(channel, payload):
	"""Woo REST order payload -> canonical normalized order
	(docs/ORDER-FLOW.md §2). Buyer/billing/shipping blocks are deliberately
	not carried: the customer policy is generic-per-channel and stored copies
	are allowlist-only (docs/PRIVACY-REDACTION.md §3-4)."""
	return {
		"channel": channel,
		"channel_order_id": str(payload.get("id")),
		"order_timestamp": payload.get("date_created_gmt") or payload.get("date_created"),
		"channel_status": payload.get("status"),
		"cancelled": payload.get("status") in ("cancelled", "refunded", "failed", "trash"),
		"currency": payload.get("currency"),
		"totals": payload.get("total"),
		"tax_total": payload.get("total_tax"),
		"evidence": {WOO_EVIDENCE_KEY: WOO_EVIDENCE_VALUE},
		"lines": [
			{
				# Empty SKU stays empty: it will fail Channel Listing
				# resolution and land in Integration Exception (INV-4) —
				# never guessed from the product name (INV-10).
				"external_identity": line.get("sku") or "",
				"qty": flt(line.get("quantity")),
				"rate": flt(line.get("price")),
			}
			for line in (payload.get("line_items") or [])
		],
	}


def fetch_orders(statuses=DEFAULT_STATUSES, modified_after=None, page=1, per_page=50):
	"""Read-only fetch from the Woo REST API. Network errors raise — callers
	decide; nothing is swallowed (fail loudly, docs/CONFIGURATION.md §2)."""
	import requests

	base_url = get_required_conf("co_woocommerce_base_url").rstrip("/")
	api_path = get_optional_conf("co_woocommerce_api_path", DEFAULT_API_PATH)
	params = {"status": statuses, "page": page, "per_page": per_page, "orderby": "id", "order": "asc"}
	if modified_after:
		params["modified_after"] = modified_after

	response = requests.get(
		f"{base_url}{api_path}/orders",
		params=params,
		auth=(
			get_required_conf("co_woocommerce_consumer_key"),
			get_required_conf("co_woocommerce_consumer_secret"),
		),
		timeout=30,
	)
	response.raise_for_status()
	return response.json()


@frappe.whitelist()
def import_woocommerce_orders(channel, statuses=DEFAULT_STATUSES, modified_after=None):
	"""Operator-triggered import run (manual transport, docs/ORDER-FLOW.md §6).
	Every payload goes through the shared Order Import Service — there is no
	Woo-specific Sales Order path (INV-9). Pages until the API returns an
	empty page, so windows larger than one page are not silently truncated;
	re-importing overlap is safe (INV-11)."""
	summary = {"created": 0, "duplicate": 0, "exception": 0}
	page = 1
	while True:
		batch = fetch_orders(statuses=statuses, modified_after=modified_after, page=page)
		if not batch:
			break
		for payload in batch:
			result = import_order(translate_order(channel, payload))
			summary[result.outcome.lower()] += 1
		page += 1
	return summary


def verify_webhook_signature(raw_body, signature):
	"""WooCommerce signs webhooks with base64(HMAC-SHA256(secret, body)).
	Constant-time comparison; missing secret fails loudly (T-CFG-1)."""
	import base64
	import hashlib
	import hmac

	secret = get_required_conf("co_woocommerce_webhook_secret")
	if not signature:
		return False
	expected = base64.b64encode(
		hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
	).decode()
	return hmac.compare_digest(expected, signature)


def handle_webhook(channel, raw_body, signature):
	"""Verify, translate, and import one webhook delivery. Permitted by
	ORDER-FLOW §6 because signature verification and idempotency are
	demonstrated by tests (test_woocommerce_webhook). Invalid signatures
	create nothing; duplicates are idempotent via the shared pipeline
	(INV-11A); the kill switch raises so WooCommerce retries later."""
	import json

	if not verify_webhook_signature(raw_body, signature):
		frappe.throw(_("Invalid webhook signature"), frappe.PermissionError)

	# Channel isolation: the secret authenticates the WooCommerce store, so a
	# valid signature must not be redirectable at another channel type. (One
	# Woo store per site is the documented assumption — CONFIGURATION §4.2;
	# per-channel secrets become necessary if a second store is added.)
	if frappe.db.get_value("Channel", channel, "channel_type") != "WooCommerce":
		frappe.throw(_("{0} is not a WooCommerce channel").format(channel), frappe.PermissionError)

	payload = json.loads(raw_body)
	result = import_order(translate_order(channel, payload))
	return {
		"outcome": result.outcome,
		"sales_order": result.sales_order,
		"integration_exception": result.integration_exception,
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def woocommerce_webhook(channel):
	"""HTTP endpoint for WooCommerce webhook deliveries. Guest access is safe
	because handle_webhook rejects anything without a valid HMAC signature."""
	return handle_webhook(
		channel,
		frappe.request.get_data(),
		frappe.request.headers.get("X-WC-Webhook-Signature"),
	)


@frappe.whitelist()
def setup_woocommerce_channel(channel):
	"""Explicit, human-invoked setup: ensures the data-driven SELF rule for a
	WooCommerce channel exists (INV-5 — the mapping is data, not code)."""
	channel_type = frappe.db.get_value("Channel", channel, "channel_type")
	if channel_type != "WooCommerce":
		frappe.throw(_("{0} is not a WooCommerce channel").format(channel))
	if not frappe.db.exists(
		"Channel Fulfillment Map",
		{"channel": channel, "evidence_key": WOO_EVIDENCE_KEY, "evidence_value": WOO_EVIDENCE_VALUE},
	):
		frappe.get_doc(
			{
				"doctype": "Channel Fulfillment Map",
				"channel": channel,
				"evidence_key": WOO_EVIDENCE_KEY,
				"evidence_value": WOO_EVIDENCE_VALUE,
				"fulfillment_type": "SELF",
			}
		).insert()
