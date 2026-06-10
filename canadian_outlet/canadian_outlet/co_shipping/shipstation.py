# ShipStation shipment sync. Recording an event is always safe and
# informational; converting a shipped event into a deduction (C2,
# FLOW-DECISIONS D5/D7) happens only via process_shipment_event — operator-
# invoked while switch ③ deduct_on_shipped_event is OFF (the default),
# automatic when it is deliberately ON. The deduction document is a
# created-and-submitted partial Delivery Note (INV-8). Duplicate events are
# idempotent on event_hash. Config keys per docs/CONFIGURATION.md §4.3.

import hashlib

import frappe

from canadian_outlet.co_core.settings import get_optional_conf, get_required_conf

DEFAULT_BASE_URL = "https://ssapi.shipstation.com"


def translate_shipment(channel, payload):
	"""ShipStation /shipments record -> canonical shipment event. Carries no
	buyer data: ship-to addresses are deliberately dropped
	(docs/PRIVACY-REDACTION.md §4); shipment items keep sku+qty only."""
	import json as _json

	carrier_status = "voided" if payload.get("voided") else "shipped"
	shipment_items = [
		{"sku": item.get("sku") or "", "qty": item.get("quantity") or 0}
		for item in (payload.get("shipmentItems") or [])
	]
	event = {
		"channel": channel,
		"channel_order_id": str(payload.get("orderNumber") or ""),
		"carrier": payload.get("carrierCode"),
		"carrier_status": carrier_status,
		"tracking_number": payload.get("trackingNumber"),
		"event_timestamp": payload.get("shipDate") or payload.get("createDate"),
		"source": "ShipStation",
		"shipment_items": _json.dumps(shipment_items) if shipment_items else None,
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
	# C2 (switch ③, OFF by default — D10 manual-first): when enabled, a
	# shipped event converts the hold to a deduction immediately; when off,
	# the operator runs process_shipment_event per event.
	if frappe.db.get_single_value("Canadian Outlet Settings", "deduct_on_shipped_event"):
		try:
			process_shipment_event(doc.name)
		except Exception:
			frappe.log_error(
				title=f"Shipment deduction failed: {doc.name}",
				message=frappe.get_traceback(),
			)
	return doc.name


@frappe.whitelist()
def process_shipment_event(event_name):
	"""C2 (FLOW-DECISIONS D5/D7): convert one shipped event's hold into a real
	deduction — a created-and-submitted partial Delivery Note for exactly that
	shipment's quantities. Constraints, all pinned by tests
	(test_c2_deduction):
	- shipped events only; voids are inert (1B — voids never touch the books)
	- SELF orders only (INV-7); FBA/WFS events deduct nothing
	- shipment items resolve through Channel Listing (INV-2); unknown SKU or
	  missing items → no deduction, event stays for the human queue
	- quantities cap at the order's undelivered remainder; over-shipments are
	  logged, never deducted past the order
	- idempotent: an event that already produced a Delivery Note is a no-op,
	  and delivered-qty capping makes duplicate boxes safe
	Returns the Delivery Note name, or None when nothing was deducted."""
	import json as _json

	from canadian_outlet.co_catalog.resolution import (
		UnresolvedListingError,
		resolve_external_identity,
	)
	from canadian_outlet.co_inventory.delivery_note_service import create_delivery_for_shipment

	event = frappe.get_doc("Shipment Status Event", event_name)
	if event.carrier_status != "shipped" or not event.sales_order:
		return None
	if event.delivery_note:
		return None  # already converted — idempotent
	if frappe.db.get_value("Sales Order", event.sales_order, "co_fulfillment_type") != "SELF":
		return None

	if not event.shipment_items:
		frappe.log_error(
			title=f"Shipment event without items: {event.name}",
			message="No shipmentItems in the source payload; nothing deducted (fail closed).",
		)
		return None

	item_qtys = {}
	for entry in _json.loads(event.shipment_items):
		try:
			item_code = resolve_external_identity(event.channel, entry.get("sku"))
		except UnresolvedListingError:
			frappe.log_error(
				title=f"Shipment SKU unmapped: {event.name}",
				message=f"sku={entry.get('sku')!r} has no active Channel Listing; "
				"nothing deducted (fail closed, INV-2/INV-10).",
			)
			return None
		item_qtys[item_code] = item_qtys.get(item_code, 0) + (entry.get("qty") or 0)

	requested = dict(item_qtys)
	dn_name = create_delivery_for_shipment(event.sales_order, item_qtys)
	if dn_name:
		_maybe_auto_invoice(dn_name)
		if any(qty > 0 for qty in item_qtys.values()):
			frappe.log_error(
				title=f"Over-shipment capped: {event.name}",
				message=f"Channel reported {requested}; undeliverable remainder "
				f"{ {k: v for k, v in item_qtys.items() if v > 0} } was not deducted.",
			)
		event.db_set("delivery_note", dn_name)
	return dn_name


def _maybe_auto_invoice(delivery_note):
	"""C5 (switch ④, OFF by default — D10 manual-first): the invoice rides the
	deduction heartbeat. A failed invoice is logged and never undoes the
	deduction — the human queue is the backstop."""
	if not frappe.db.get_single_value("Canadian Outlet Settings", "auto_invoice_on_shipment"):
		return
	try:
		from canadian_outlet.co_billing.invoice_service import create_invoice_for_delivery

		invoice_name = create_invoice_for_delivery(delivery_note)
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if invoice.docstatus == 0:
			invoice.submit()
	except Exception:
		frappe.log_error(
			title=f"Auto-invoice failed: {delivery_note}",
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
