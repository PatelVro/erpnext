# ShipStation shipment STATUS sync (Phase 14) — records what the carrier
# says, nothing more. This module must never create, submit, or cancel any
# stock-impacting document, never auto-submit Delivery Notes, and never treat
# "shipped" as "stock posted" (INV-8, docs/STOCK-FLOW.md §4). Duplicate
# events are idempotent on event_hash (docs/DATA-MODEL.md §7A, T-SHIP-2).
# Transport is operator-triggered only — no scheduler (AGENTS.md scope gates).
# Config keys per docs/CONFIGURATION.md §4.3.

import hashlib

import frappe

from canadian_outlet.co_core.settings import get_optional_conf, get_required_conf

DEFAULT_BASE_URL = "https://ssapi.shipstation.com"


def translate_shipment(channel, payload):
	"""ShipStation /shipments record -> canonical shipment event. Carries no
	buyer data: ship-to addresses are deliberately dropped
	(docs/PRIVACY-REDACTION.md §4)."""
	carrier_status = "voided" if payload.get("voided") else "shipped"
	event = {
		"channel": channel,
		"channel_order_id": str(payload.get("orderNumber") or ""),
		"carrier": payload.get("carrierCode"),
		"carrier_status": carrier_status,
		"tracking_number": payload.get("trackingNumber"),
		"event_timestamp": payload.get("shipDate") or payload.get("createDate"),
		"source": "ShipStation",
	}
	event["event_hash"] = hashlib.sha256(
		"|".join(
			str(event.get(key) or "")
			for key in ("channel", "channel_order_id", "tracking_number", "carrier_status", "event_timestamp")
		).encode()
	).hexdigest()
	return event


def record_shipment_event(event):
	"""Idempotently persist one shipment event. Returns the event name.
	Informational only: an unknown order records an unlinked event (T-SHIP-4)
	rather than failing closed — status sync must not flood Integration
	Exceptions or affect order flow."""
	existing = frappe.db.exists("Shipment Status Event", {"event_hash": event["event_hash"]})
	if existing:
		return existing

	sales_order = frappe.db.get_value(
		"Sales Order",
		{
			"co_sales_channel": event["channel"],
			"co_channel_order_id": event["channel_order_id"],
		},
		"name",
	)
	doc = frappe.get_doc(
		{
			"doctype": "Shipment Status Event",
			"sales_order": sales_order,
			**event,
		}
	)
	doc.insert(ignore_permissions=True)
	_maybe_auto_submit_delivery_note(doc)
	return doc.name


def _maybe_auto_submit_delivery_note(event):
	"""STOCK-FLOW §5 upgrade, explicitly approved: a 'shipped' event SUBMITS
	the existing draft Delivery Note of the matching SELF order. Constraints,
	all enforced here and by tests (test_auto_submit_dn):
	- kill switch: auto_submit_delivery_note_on_shipped, OFF by default
	- never creates a Delivery Note — only submits an existing draft
	- SELF only (INV-7); exactly-once (event dedup + a submitted DN leaves
	  no draft for later events)
	- a failed submit leaves the draft for the human queue (logged), so the
	  human review path remains the backstop"""
	if event.carrier_status != "shipped":
		return
	if not event.sales_order:
		return
	if not frappe.db.get_single_value(
		"Canadian Outlet Settings", "auto_submit_delivery_note_on_shipped"
	):
		return
	if frappe.db.get_value("Sales Order", event.sales_order, "co_fulfillment_type") != "SELF":
		return

	draft = frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": event.sales_order, "docstatus": 0},
		pluck="parent",
		limit=1,
	)
	if not draft:
		return

	try:
		frappe.get_doc("Delivery Note", draft[0]).submit()
	except Exception:
		frappe.log_error(
			title=f"Auto-submit failed: {draft[0]} (event {event.name})",
			message=frappe.get_traceback(),
		)


def fetch_shipments(page=1, page_size=100, ship_date_start=None):
	"""Read-only fetch from the ShipStation API. Errors raise; nothing is
	swallowed (docs/CONFIGURATION.md §2)."""
	import requests

	base_url = get_optional_conf("co_shipstation_base_url", DEFAULT_BASE_URL).rstrip("/")
	params = {"page": page, "pageSize": page_size}
	if ship_date_start:
		params["shipDateStart"] = ship_date_start

	response = requests.get(
		f"{base_url}/shipments",
		params=params,
		auth=(
			get_required_conf("co_shipstation_api_key"),
			get_required_conf("co_shipstation_api_secret"),
		),
		timeout=30,
	)
	response.raise_for_status()
	return response.json().get("shipments", [])


@frappe.whitelist()
def import_shipstation_shipments(channel, ship_date_start=None):
	"""Operator-triggered status sync run (no scheduler)."""
	recorded = 0
	for payload in fetch_shipments(ship_date_start=ship_date_start):
		record_shipment_event(translate_shipment(channel, payload))
		recorded += 1
	return {"events_processed": recorded}
