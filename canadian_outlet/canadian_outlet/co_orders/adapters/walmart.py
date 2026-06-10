# Walmart Marketplace adapter (Phase 16). Translation + data-driven
# classification only — all imports flow through the shared Order Import
# Service (INV-9). Walmart WFS -> WFS, seller-fulfilled -> SELF via Channel
# Fulfillment Map rows (INV-5); any other/missing ship node type has no rule,
# classifies UNKNOWN, and fails closed (INV-6, INV-10) — never SELF. WFS
# orders never touch local stock (INV-7). Transport is operator-triggered
# only. Config keys per CONFIGURATION.md §4.5.

import frappe
from frappe import _
from frappe.utils import flt

from canadian_outlet.co_core.settings import get_optional_conf, get_required_conf
from canadian_outlet.co_orders.import_service import import_order

EVIDENCE_KEY = "ship_node_type"
BASELINE_RULES = (("WFSFulfilled", "WFS"), ("SellerFulfilled", "SELF"))
DEFAULT_BASE_URL = "https://marketplace.walmartapis.com"


def translate_order(channel, payload):
	"""Walmart MP order -> canonical normalized order (docs/ORDER-FLOW.md §2).
	Buyer/shipping info is never carried (docs/PRIVACY-REDACTION.md §4)."""
	order_lines = ((payload.get("orderLines") or {}).get("orderLine")) or []
	return {
		"channel": channel,
		"channel_order_id": str(payload.get("purchaseOrderId") or ""),
		"order_timestamp": str(payload.get("orderDate") or ""),
		"channel_status": _first_line_status(order_lines),
		"currency": _currency(order_lines),
		"evidence": {EVIDENCE_KEY: (payload.get("shipNode") or {}).get("type") or ""},
		"lines": [
			{
				"external_identity": (line.get("item") or {}).get("sku") or "",
				"qty": flt((line.get("orderLineQuantity") or {}).get("amount")),
				"rate": _unit_price(line),
			}
			for line in order_lines
		],
	}


def _first_line_status(order_lines):
	for line in order_lines:
		statuses = ((line.get("orderLineStatuses") or {}).get("orderLineStatus")) or []
		for status in statuses:
			if status.get("status"):
				return status["status"]
	return ""


def _charge(line):
	charges = ((line.get("charges") or {}).get("charge")) or []
	for charge in charges:
		if charge.get("chargeType") == "PRODUCT":
			return charge.get("chargeAmount") or {}
	return {}


def _currency(order_lines):
	for line in order_lines:
		currency = _charge(line).get("currency")
		if currency:
			return currency
	return None


def _unit_price(line):
	return flt(_charge(line).get("amount"))


def get_access_token():
	import requests

	response = requests.post(
		f"{_base_url()}/v3/token",
		data={"grant_type": "client_credentials"},
		auth=(
			get_required_conf("co_walmart_client_id"),
			get_required_conf("co_walmart_client_secret"),
		),
		headers={"WM_SVC.NAME": "Canadian Outlet ERP", "WM_QOS.CORRELATION_ID": frappe.generate_hash(length=12), "Accept": "application/json"},
		timeout=30,
	)
	response.raise_for_status()
	return response.json()["access_token"]


def _base_url():
	return get_optional_conf("co_walmart_base_url", DEFAULT_BASE_URL).rstrip("/")


def fetch_orders(created_start_date, token=None):
	import requests

	token = token or get_access_token()
	response = requests.get(
		f"{_base_url()}/v3/orders",
		params={"createdStartDate": created_start_date},
		headers={
			"WM_SEC.ACCESS_TOKEN": token,
			"WM_SVC.NAME": "Canadian Outlet ERP",
			"WM_QOS.CORRELATION_ID": frappe.generate_hash(length=12),
			"Accept": "application/json",
		},
		timeout=30,
	)
	response.raise_for_status()
	elements = (response.json().get("list") or {}).get("elements") or {}
	return elements.get("order") or []


@frappe.whitelist()
def import_walmart_orders(channel, created_start_date):
	"""Operator-triggered import run (no scheduler). Every order goes through
	the shared Order Import Service — no Walmart-specific path (INV-9)."""
	summary = {"created": 0, "duplicate": 0, "exception": 0}
	token = get_access_token()
	for payload in fetch_orders(created_start_date, token=token):
		result = import_order(translate_order(channel, payload))
		summary[result.outcome.lower()] += 1
	return summary


@frappe.whitelist()
def setup_walmart_channel(channel):
	"""Explicit, human-invoked setup: WFSFulfilled->WFS and
	SellerFulfilled->SELF as data rules (INV-5)."""
	channel_type = frappe.db.get_value("Channel", channel, "channel_type")
	if channel_type != "Walmart":
		frappe.throw(_("{0} is not a Walmart channel").format(channel))
	for evidence_value, fulfillment_type in BASELINE_RULES:
		if not frappe.db.exists(
			"Channel Fulfillment Map",
			{"channel": channel, "evidence_key": EVIDENCE_KEY, "evidence_value": evidence_value},
		):
			frappe.get_doc(
				{
					"doctype": "Channel Fulfillment Map",
					"channel": channel,
					"evidence_key": EVIDENCE_KEY,
					"evidence_value": evidence_value,
					"fulfillment_type": fulfillment_type,
				}
			).insert()
