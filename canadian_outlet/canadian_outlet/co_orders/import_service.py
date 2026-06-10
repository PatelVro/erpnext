# Order Import Service (Phases 10-11) — the SINGLE entry point through which
# every external order becomes a Sales Order (INV-9). Pipeline per
# docs/ORDER-FLOW.md §1:
#   kill switch / channel check (fail closed, T-PIPE-2)
#   → idempotency (INV-11A, enforced on Sales Order co_ fields)
#   → line resolution via Channel Listing (INV-2/3/4)
#   → fulfillment classification (INV-5/6)
#   → customer (generic per-channel policy, docs/ORDER-FLOW.md §4)
#   → atomic Sales Order creation (INV-10)
# Any blocking condition becomes a deduplicated Integration Exception
# (INV-11C) and an Order Import Log row; no partial records survive
# (savepoint rollback, T-ATOM-2). Stored payload copies are allowlist-only
# (docs/PRIVACY-REDACTION.md §3, T-PII-1/2). This module never creates Items,
# never touches stock documents, and never submits anything (INV-1, INV-8,
# docs/STOCK-FLOW.md).

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

import frappe
from frappe.utils import now_datetime, nowdate

from canadian_outlet.co_catalog.resolution import (
	UnresolvedListingError,
	resolve_external_identity,
)
from canadian_outlet.co_core.redaction import scrub_secrets
from canadian_outlet.co_orders.classification import (
	UNKNOWN,
	VALID_FULFILLMENT_TYPES,
	classify_fulfillment,
)

SAVEPOINT = "co_order_import"

# Mirrors docs/PRIVACY-REDACTION.md §3 — the only payload keys ever persisted.
ALLOWED_TOP_LEVEL_KEYS = (
	"channel",
	"channel_order_id",
	"order_timestamp",
	"channel_status",
	"currency",
	"totals",
	"tax_total",
	"evidence",
	"lines",
)
ALLOWED_LINE_KEYS = ("external_identity", "qty", "rate")
REPLAY_MINIMAL_KEYS = ("channel", "channel_order_id", "currency", "evidence", "lines")


class ImportsDisabledError(Exception):
	"""Imports are globally or per-channel disabled — deliberate operator
	state, so nothing is created (T-PIPE-2)."""


class _ImportBlocked(Exception):
	"""Internal: pipeline stop that becomes an Integration Exception."""

	def __init__(self, stage, reason, external_identity=None):
		super().__init__(reason)
		self.stage = stage
		self.reason = reason
		self.external_identity = external_identity


class _RaceDuplicate(Exception):
	"""Internal: the DB unique index rejected our insert because a concurrent
	import created the same (channel, channel_order_id) first."""


@dataclass
class ImportResult:
	outcome: str  # Created | Duplicate | Exception
	sales_order: Optional[str] = None
	integration_exception: Optional[str] = None
	quarantined: bool = False


def import_order(order):
	"""Import one canonical normalized order (docs/ORDER-FLOW.md §2)."""
	_check_imports_enabled(order)

	channel = order["channel"]
	channel_order_id = str(order.get("channel_order_id") or "")
	# Even malformed attempts must leave an audit trail: the log DocType
	# requires an order id, so empty ones are recorded under a placeholder
	# (the import itself is still blocked by _validate_envelope).
	log_order_id = channel_order_id or "(missing)"
	import_key = f"{channel}::{log_order_id}"
	payload_hash = _payload_hash(order)

	# INV-11A fast path. The authoritative enforcement is the DATABASE unique
	# index on (co_sales_channel, co_channel_order_id) — see _RaceDuplicate
	# below for the concurrent case this check alone cannot catch.
	existing = _find_existing_sales_order(channel, channel_order_id)
	if existing:
		exception_name = None
		if order.get("cancelled"):
			exception_name = _handle_channel_cancellation(channel, channel_order_id,
				existing, order, payload_hash)
		_write_log(channel, log_order_id, import_key, "Duplicate", payload_hash,
			sales_order=existing, integration_exception=exception_name)
		return ImportResult("Duplicate", sales_order=existing,
			integration_exception=exception_name)

	frappe.db.savepoint(SAVEPOINT)
	try:
		_validate_envelope(channel_order_id, order)
		resolved_lines = _resolve_lines(channel, order)
		fulfillment_type = _classify(channel, order)
		customer = _resolve_customer(channel)
		sales_order = _create_sales_order(
			channel, channel_order_id, order, resolved_lines, fulfillment_type, customer
		)
	except _RaceDuplicate:
		# A concurrent import won the unique index between our check and our
		# insert (INV-11A): this attempt is a Duplicate, not an Exception.
		frappe.db.rollback(save_point=SAVEPOINT)
		existing = _find_existing_sales_order(channel, channel_order_id)
		_write_log(channel, log_order_id, import_key, "Duplicate", payload_hash,
			sales_order=existing)
		return ImportResult("Duplicate", sales_order=existing)
	except _ImportBlocked as blocked:
		# INV-10: atomic — roll back anything partially created, then record
		# the failure (exception + log are the only records that survive).
		frappe.db.rollback(save_point=SAVEPOINT)
		exception_name = _record_exception(channel, channel_order_id, order, blocked, payload_hash)
		_write_log(channel, log_order_id, import_key, "Exception", payload_hash,
			integration_exception=exception_name)
		return ImportResult("Exception", integration_exception=exception_name)

	quarantined = fulfillment_type is None
	_write_log(channel, log_order_id, import_key, "Created", payload_hash,
		sales_order=sales_order)
	return ImportResult("Created", sales_order=sales_order, quarantined=quarantined)


def _find_existing_sales_order(channel, channel_order_id):
	return frappe.db.get_value(
		"Sales Order",
		{"co_sales_channel": channel, "co_channel_order_id": channel_order_id},
		"name",
	)


def _validate_envelope(channel_order_id, order):
	# Malformed payloads fail closed into Integration Exception (INV-10) —
	# never an unhandled traceback, never a "None"/empty order key.
	from frappe.utils import flt

	if not channel_order_id.strip() or channel_order_id == "None":
		raise _ImportBlocked("Creation", "Missing or empty channel_order_id")
	for index, line in enumerate(order.get("lines") or []):
		qty = flt(line.get("qty"))
		if qty <= 0:
			raise _ImportBlocked(
				"Creation", f"Line {index + 1}: qty must be positive, got {line.get('qty')!r}"
			)
		if line.get("rate") is None or flt(line.get("rate")) < 0:
			raise _ImportBlocked(
				"Creation", f"Line {index + 1}: rate missing or negative, got {line.get('rate')!r}"
			)


def _check_imports_enabled(order):
	if not frappe.db.get_single_value("Canadian Outlet Settings", "imports_enabled"):
		raise ImportsDisabledError("Canadian Outlet Settings: imports_enabled is off")
	channel = order.get("channel")
	channel_state = frappe.db.get_value("Channel", channel, "enabled")
	if channel_state is None:
		raise ImportsDisabledError(f"Channel does not exist: {channel}")
	if not channel_state:
		raise ImportsDisabledError(f"Channel is disabled: {channel}")


def _resolve_lines(channel, order):
	lines = order.get("lines") or []
	if not lines:
		raise _ImportBlocked("Creation", "Order has no lines")

	resolved = []
	for line in lines:
		external_identity = line.get("external_identity")
		try:
			item_code = resolve_external_identity(channel, external_identity)
		except UnresolvedListingError as err:
			# INV-4: unknown listing → exception, never an Item.
			raise _ImportBlocked("Resolution", str(err), external_identity=external_identity)
		resolved.append({"item_code": item_code, "qty": line["qty"], "rate": line["rate"]})
	return resolved


def _classify(channel, order):
	"""Returns SELF/FBA/WFS, or None for QUARANTINE (C3, FLOW-DECISIONS D3):
	unclear fulfillment imports as a real-but-quarantined draft instead of
	being blocked. UNKNOWN is still never written and never becomes SELF
	(INV-5/INV-6 as rewritten by C3)."""
	fulfillment_type = classify_fulfillment(channel, order.get("evidence") or {})
	if fulfillment_type == UNKNOWN or fulfillment_type not in VALID_FULFILLMENT_TYPES:
		return None
	return fulfillment_type


def _resolve_customer(channel):
	customer = frappe.db.get_value("Channel", channel, "default_customer")
	if not customer:
		raise _ImportBlocked("Customer", f"Channel {channel} has no default customer")
	return customer


def _create_sales_order(channel, channel_order_id, order, resolved_lines, fulfillment_type, customer):
	delivery_date = nowdate()
	currency = order.get("currency")
	# Channel rates are authoritative (rates come from the marketplace, not a
	# price list). Pick a selling price list in the order currency when one
	# exists so ERPNext does not demand a price-list exchange rate; if none
	# exists the site default applies and a missing exchange rate fails
	# closed into an Integration Exception (INV-10) for the operator to fix.
	selling_price_list = currency and frappe.db.get_value(
		"Price List", {"currency": currency, "selling": 1, "enabled": 1}
	)
	# SELF orders inherit the configured physical warehouse so the eventual
	# Delivery Note maps it (docs/STOCK-FLOW.md §1/§3). Informational on the
	# Sales Order itself — a Sales Order never moves stock. FBA/WFS orders
	# carry no local warehouse reference (INV-7).
	warehouse = None
	fulfillment_supplier = None
	if fulfillment_type is None:
		# Quarantine (C3): no warehouse, no drop-ship — the draft holds
		# nothing and waits for classify_quarantined_order.
		pass
	elif fulfillment_type == "SELF":
		warehouse = frappe.db.get_single_value("Canadian Outlet Settings", "default_warehouse")
	else:
		# INV-7: FBA/WFS lines are DROP-SHIP rows (delivered_by_supplier) —
		# ERPNext excludes them from shelf reservation and from Delivery Note
		# mapping, and demands no warehouse. ERPNext would otherwise auto-fill
		# item-default warehouses and reserve shelf stock for marketplace-
		# fulfilled orders (caught by test_fba_import_holds_nothing). The
		# fulfilling Supplier is operator-configured; absent → fail closed.
		fulfillment_supplier = frappe.db.get_single_value(
			"Canadian Outlet Settings", "marketplace_fulfillment_supplier"
		)
		if not fulfillment_supplier:
			raise _ImportBlocked(
				"Creation",
				"Canadian Outlet Settings: marketplace_fulfillment_supplier is not set "
				"— required for FBA/WFS orders (INV-7)",
			)
	doc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"transaction_date": nowdate(),
			"delivery_date": delivery_date,
			"currency": currency,
			"selling_price_list": selling_price_list,
			"co_sales_channel": channel,
			"co_channel_order_id": channel_order_id,
			"co_fulfillment_type": fulfillment_type,
			"co_quarantined": 1 if fulfillment_type is None else 0,
			"items": [
				{
					"item_code": line["item_code"],
					"qty": line["qty"],
					"rate": line["rate"],
					"delivery_date": delivery_date,
					"warehouse": warehouse,
					"delivered_by_supplier": 1 if fulfillment_type in ("FBA", "WFS") else 0,
					"supplier": fulfillment_supplier,
				}
				for line in resolved_lines
			],
		}
	)
	try:
		doc.insert(ignore_permissions=True)
		if fulfillment_type is None:
			# Quarantined drafts stay drafts (C3): visible, counted,
			# incapable of holding, shipping, or invoicing until classified.
			return doc.name
		# C1 (FLOW-DECISIONS D5, INV-12): a marketplace order is confirmed by
		# definition, so it is submitted on arrival. Submission is NOT a stock
		# movement (INV-8) — it places the availability HOLD: SELF lines carry
		# the warehouse and raise Bin.reserved_qty; FBA/WFS lines carry none
		# and hold nothing (INV-7). Cancelling the order releases the hold.
		doc.submit()
		if order.get("cancelled"):
			# Cancelled before we ever saw it: the per-order record must
			# still exist (D1), but it holds nothing.
			doc.cancel()
	except Exception as err:
		if _is_channel_order_unique_violation(err):
			raise _RaceDuplicate()
		raise _ImportBlocked("Creation", scrub_secrets(str(err)))
	return doc.name


def _has_submitted_delivery(sales_order):
	return bool(frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": sales_order, "docstatus": 1},
		limit=1,
	))


def _handle_channel_cancellation(channel, channel_order_id, sales_order, order, payload_hash):
	"""FLOW-DECISIONS D6: cancellation before ship is SILENT — cancel the
	order, which releases its hold natively. After ship it STOPS for human
	review (goods and money both in motion). Idempotent: an already-cancelled
	order is a no-op. Returns an Integration Exception name for the STOP case."""
	docstatus = frappe.db.get_value("Sales Order", sales_order, "docstatus")
	if docstatus != 1:
		return None  # draft or already cancelled — nothing to release

	if _has_submitted_delivery(sales_order):
		blocked = _ImportBlocked(
			"Cancellation",
			f"Channel cancelled {channel_order_id} after shipment — return/dispute review needed",
		)
		return _record_exception(channel, channel_order_id, order, blocked, payload_hash)

	frappe.get_doc("Sales Order", sales_order).cancel()
	return None


def _is_channel_order_unique_violation(err):
	from canadian_outlet.install import UNIQUE_CONSTRAINT

	return UNIQUE_CONSTRAINT in str(err) or isinstance(
		err, frappe.UniqueValidationError
	)


def _record_exception(channel, channel_order_id, order, blocked, payload_hash):
	# INV-11C: same (channel, order, stage, cause) → exactly one exception.
	dedup_key = hashlib.sha256(
		f"{channel}|{channel_order_id}|{blocked.stage}|{blocked.reason}".encode()
	).hexdigest()

	existing_name = frappe.db.exists("Integration Exception", {"dedup_key": dedup_key})
	if existing_name:
		existing = frappe.get_doc("Integration Exception", existing_name)
		if existing.status == "Resolved":
			# Replay after resolution failed again for the same cause
			# (docs/DATA-MODEL.md §5).
			existing.status = "Failed Replay"
			existing.save(ignore_permissions=True)
		return existing.name

	# A replay can fail for a NEW cause: link the new exception back to the
	# most recent prior exception for this order (docs/DATA-MODEL.md §5).
	prior = frappe.get_all(
		"Integration Exception",
		filters={"channel": channel, "channel_order_id": channel_order_id},
		order_by="creation desc",
		limit=1,
		pluck="name",
	)
	doc = frappe.get_doc(
		{
			"doctype": "Integration Exception",
			"channel": channel,
			"channel_order_id": channel_order_id,
			"failure_stage": blocked.stage,
			"failure_reason": scrub_secrets(blocked.reason),
			"external_identity": blocked.external_identity,
			"status": "Open",
			"dedup_key": dedup_key,
			"payload_hash": payload_hash,
			"external_payload_reference": f"{channel}:{channel_order_id}",
			"raw_payload_redacted": json.dumps(_redact(order, ALLOWED_TOP_LEVEL_KEYS)),
			"replay_payload_minimal": json.dumps(_redact(order, REPLAY_MINIMAL_KEYS)),
			"original_exception": prior[0] if prior else None,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _write_log(channel, channel_order_id, import_key, outcome, payload_hash,
		sales_order=None, integration_exception=None):
	frappe.get_doc(
		{
			"doctype": "Order Import Log",
			"channel": channel,
			"channel_order_id": channel_order_id,
			"import_key": import_key,
			"outcome": outcome,
			"sales_order": sales_order,
			"integration_exception": integration_exception,
			"payload_hash": payload_hash,
		}
	).insert(ignore_permissions=True)


def _redact(order, allowed_keys):
	# Allowlist-only copies (docs/PRIVACY-REDACTION.md §3): unknown and
	# disallowed keys — including any buyer/PII block — are stripped, and
	# lines keep only identity/qty/rate.
	redacted = {}
	for key in allowed_keys:
		if key not in order:
			continue
		if key == "lines":
			redacted["lines"] = [
				{k: line.get(k) for k in ALLOWED_LINE_KEYS if k in line}
				for line in (order.get("lines") or [])
			]
		else:
			redacted[key] = order[key]
	return redacted


def _payload_hash(order):
	canonical = json.dumps(order, sort_keys=True, default=str)
	return hashlib.sha256(canonical.encode()).hexdigest()
