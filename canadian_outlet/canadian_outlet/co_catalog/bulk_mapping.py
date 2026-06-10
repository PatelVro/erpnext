# Bulk mapping import (C4, FLOW-DECISIONS D2): the owner pre-maps ALL channel
# SKUs from spreadsheets before go-live. CSV in (external_identity,item_code),
# row-level validation report out. Rejected rows never block accepted ones;
# nothing is guessed; existing identical mappings are skipped (idempotent);
# conflicting ones are rejected, not overwritten.

import csv
import io

import frappe


@frappe.whitelist()
def import_listings_csv(channel, csv_content):
	"""Returns {"created": n, "skipped": n, "rejected": [{"row", "reason"}]}.
	Each created listing fires fix-and-flow (Channel Listing.after_insert),
	so stuck orders waiting on these SKUs import immediately."""
	reader = csv.reader(io.StringIO(csv_content))
	rows = [row for row in reader if any(cell.strip() for cell in row)]
	if rows and _tokens_lower(rows[0])[:1] in (["external_identity"], ["sku"]):
		rows = rows[1:]  # header row

	result = {"created": 0, "skipped": 0, "rejected": []}
	for index, row in enumerate(rows, start=1):
		if len(row) < 2 or not row[0].strip() or not row[1].strip():
			result["rejected"].append({"row": index, "reason": "needs sku,item_code"})
			continue
		external_identity, item_code = row[0].strip(), row[1].strip()

		existing = frappe.db.get_value(
			"Channel Listing",
			{"channel": channel, "external_identity": external_identity},
			"item",
		)
		if existing == item_code:
			result["skipped"] += 1
			continue
		if existing:
			result["rejected"].append({
				"row": index,
				"reason": f"{external_identity} already maps to {existing} — not overwritten",
			})
			continue

		try:
			frappe.get_doc({
				"doctype": "Channel Listing",
				"channel": channel,
				"external_identity": external_identity,
				"item": item_code,
				"status": "Active",
			}).insert()
			result["created"] += 1
		except Exception as err:
			result["rejected"].append({"row": index, "reason": str(err)[:140]})
	return result


def _tokens_lower(row):
	return [cell.strip().lower() for cell in row]
