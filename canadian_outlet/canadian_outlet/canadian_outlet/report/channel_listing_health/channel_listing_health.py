# Channel Listing Health (Phase 22): listings needing attention — inactive
# listings and listings mapped to disabled Items (which fail closed at
# resolution, INV-2/INV-10, so they surface here before they surface as
# Integration Exceptions).

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	if filters.get("channel"):
		conditions["channel"] = filters.channel

	listings = frappe.get_all(
		"Channel Listing",
		filters=conditions,
		fields=["name", "channel", "external_identity", "item", "status"],
		order_by="channel, external_identity",
	)
	rows = []
	for listing in listings:
		item_disabled = frappe.db.get_value("Item", listing["item"], "disabled")
		needs_attention = listing["status"] != "Active" or item_disabled
		if filters.get("only_attention") and not needs_attention:
			continue
		listing["item_disabled"] = int(bool(item_disabled))
		listing["needs_attention"] = int(bool(needs_attention))
		rows.append(listing)

	columns = [
		{"fieldname": "channel", "label": _("Channel"), "fieldtype": "Link", "options": "Channel", "width": 160},
		{"fieldname": "external_identity", "label": _("External Identity"), "fieldtype": "Data", "width": 180},
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 180},
		{"fieldname": "status", "label": _("Listing Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "item_disabled", "label": _("Item Disabled"), "fieldtype": "Check", "width": 110},
		{"fieldname": "needs_attention", "label": _("Needs Attention"), "fieldtype": "Check", "width": 120},
	]
	return columns, rows
