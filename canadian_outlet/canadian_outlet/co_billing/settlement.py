# Amazon settlement reconciliation (Phase 27) — READ-ONLY. Parses the
# publicly documented settlement flat-file (V2, tab-delimited) and matches
# order-level principal amounts against ERPNext Sales Orders by
# (channel, channel_order_id). Produces visibility, not postings: this module
# writes NOTHING — no Payment Entries, no Journal Entries, no exceptions.
# Posting settlements to the GL requires accounting policy decisions and is
# explicitly out of scope until a human provides them.

import csv
import io

import frappe
from frappe.utils import flt


def parse_settlement_file(content):
	"""Tab-delimited settlement V2 rows as dicts, keyed by the header line."""
	reader = csv.DictReader(io.StringIO(content), delimiter="\t")
	return [row for row in reader]


def reconcile_amazon_settlement(channel, content):
	"""Match settlement order rows to Sales Orders. Returns a summary plus
	one row per order-id: Matched / Unmatched, settlement principal vs the
	order's grand total (fees make these differ legitimately — the report
	shows both; judgement stays human)."""
	principal_by_order = {}
	for row in parse_settlement_file(content):
		order_id = (row.get("order-id") or "").strip()
		if not order_id:
			continue  # account-level fees, reserves, etc.
		if (row.get("amount-type") or "").strip() == "ItemPrice":
			principal_by_order.setdefault(order_id, 0.0)
			principal_by_order[order_id] += flt(row.get("amount"))

	rows = []
	matched = 0
	for order_id, principal in sorted(principal_by_order.items()):
		so = frappe.db.get_value(
			"Sales Order",
			{"co_sales_channel": channel, "co_channel_order_id": order_id},
			["name", "grand_total"],
			as_dict=True,
		)
		status = "Matched" if so else "Unmatched"
		if so:
			matched += 1
		rows.append(
			{
				"order_id": order_id,
				"settlement_principal": principal,
				"sales_order": so.name if so else None,
				"order_grand_total": so.grand_total if so else None,
				"status": status,
			}
		)

	return {
		"orders_in_settlement": len(rows),
		"matched": matched,
		"unmatched": len(rows) - matched,
		"rows": rows,
	}
