# Amazon SP-API adapter (Phase 15). Translation + data-driven classification
# only — all imports flow through the shared Order Import Service (INV-9).
# Amazon AFN -> FBA, MFN -> SELF via Channel Fulfillment Map rows (INV-5);
# any other/missing FulfillmentChannel value has no rule, classifies UNKNOWN,
# and fails closed (INV-6, INV-10) — never SELF. FBA orders never touch local
# stock (INV-7; enforced by the stock model, verified by T-STK-3).
# Transport is operator-triggered only. Config keys per CONFIGURATION.md §4.4.

import frappe
from frappe import _
from frappe.utils import flt

from canadian_outlet.co_core.settings import get_optional_conf, get_required_conf
from canadian_outlet.co_orders.import_service import import_order

EVIDENCE_KEY = "fulfillment_channel"
BASELINE_RULES = (("AFN", "FBA"), ("MFN", "SELF"))
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
REGION_ENDPOINTS = {
	"na": "https://sellingpartnerapi-na.amazon.com",
	"eu": "https://sellingpartnerapi-eu.amazon.com",
	"fe": "https://sellingpartnerapi-fe.amazon.com",
}


def translate_order(channel, payload, order_items):
	"""SP-API order + order items -> canonical normalized order
	(docs/ORDER-FLOW.md §2). Buyer/shipping blocks are never carried
	(docs/PRIVACY-REDACTION.md §4)."""
	return {
		"channel": channel,
		"channel_order_id": str(payload.get("AmazonOrderId") or ""),
		"order_timestamp": payload.get("PurchaseDate"),
		"channel_status": payload.get("OrderStatus"),
		"cancelled": payload.get("OrderStatus") == "Canceled",
		"currency": (payload.get("OrderTotal") or {}).get("CurrencyCode"),
		"totals": (payload.get("OrderTotal") or {}).get("Amount"),
		"tax_total": sum(
			flt((item.get("ItemTax") or {}).get("Amount")) for item in (order_items or [])
		),
		"evidence": {EVIDENCE_KEY: payload.get("FulfillmentChannel") or ""},
		"lines": [
			{
				# Missing SKU stays empty and fails closed at resolution (INV-4).
				"external_identity": item.get("SellerSKU") or "",
				"qty": flt(item.get("QuantityOrdered")),
				"rate": _unit_price(item),
			}
			for item in (order_items or [])
		],
	}


def _unit_price(item):
	qty = flt(item.get("QuantityOrdered"))
	line_total = flt((item.get("ItemPrice") or {}).get("Amount"))
	return line_total / qty if qty else 0


def get_access_token():
	"""LWA token exchange. Errors raise; nothing is swallowed."""
	import requests

	response = requests.post(
		LWA_TOKEN_URL,
		data={
			"grant_type": "refresh_token",
			"refresh_token": get_required_conf("co_amazon_lwa_refresh_token"),
			"client_id": get_required_conf("co_amazon_lwa_client_id"),
			"client_secret": get_required_conf("co_amazon_lwa_client_secret"),
		},
		timeout=30,
	)
	response.raise_for_status()
	return response.json()["access_token"]


def _endpoint():
	region = get_optional_conf("co_amazon_region", "na")
	endpoint = REGION_ENDPOINTS.get(region)
	if not endpoint:
		frappe.throw(_("Unknown co_amazon_region: {0}").format(region))
	return endpoint


def fetch_orders(created_after, token=None, next_token=None):
	"""One page of SP-API orders. Returns (orders, next_token) — callers must
	follow NextToken or windows beyond one page are silently truncated."""
	import requests

	token = token or get_access_token()
	params = {
		"MarketplaceIds": get_required_conf("co_amazon_marketplace_ids"),
		"CreatedAfter": created_after,
	}
	if next_token:
		params["NextToken"] = next_token
	response = requests.get(
		f"{_endpoint()}/orders/v0/orders",
		params=params,
		headers={"x-amz-access-token": token},
		timeout=30,
	)
	response.raise_for_status()
	payload = response.json().get("payload", {})
	return payload.get("Orders", []), payload.get("NextToken")


def fetch_order_items(amazon_order_id, token=None):
	"""All items of one order — follows OrderItems NextToken internally."""
	import requests

	token = token or get_access_token()
	items, next_token = [], None
	while True:
		params = {"NextToken": next_token} if next_token else {}
		response = requests.get(
			f"{_endpoint()}/orders/v0/orders/{amazon_order_id}/orderItems",
			params=params,
			headers={"x-amz-access-token": token},
			timeout=30,
		)
		response.raise_for_status()
		payload = response.json().get("payload", {})
		items.extend(payload.get("OrderItems", []))
		next_token = payload.get("NextToken")
		if not next_token:
			return items


@frappe.whitelist()
def import_amazon_orders(channel, created_after):
	"""Operator-triggered import run (no Amazon-specific Sales Order path —
	INV-9). Follows NextToken across all pages; overlap is safe (INV-11)."""
	summary = {"created": 0, "duplicate": 0, "exception": 0}
	token = get_access_token()
	next_token = None
	while True:
		orders, next_token = fetch_orders(created_after, token=token, next_token=next_token)
		for payload in orders:
			items = fetch_order_items(payload.get("AmazonOrderId"), token=token)
			result = import_order(translate_order(channel, payload, items))
			summary[result.outcome.lower()] += 1
		if not next_token:
			return summary


@frappe.whitelist()
def setup_amazon_channel(channel):
	"""Explicit, human-invoked setup: AFN->FBA and MFN->SELF as data rules
	(INV-5). No rule exists for any other value — unknown stays UNKNOWN."""
	channel_type = frappe.db.get_value("Channel", channel, "channel_type")
	if channel_type != "Amazon":
		frappe.throw(_("{0} is not an Amazon channel").format(channel))
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
