# Integration Exception Aging (Phase 22): the triage queue by age. Non-
# terminal exceptions (Open / In Review / Failed Replay), oldest first.

import frappe
from frappe import _
from frappe.utils import date_diff, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"status": ("in", ["Open", "In Review", "Failed Replay"])}
	if filters.get("channel"):
		conditions["channel"] = filters.channel

	rows = frappe.get_all(
		"Integration Exception",
		filters=conditions,
		fields=["name", "channel", "channel_order_id", "failure_stage", "status", "creation"],
		order_by="creation asc",
	)
	for row in rows:
		row["age_days"] = date_diff(nowdate(), row["creation"])

	columns = [
		{"fieldname": "name", "label": _("Exception"), "fieldtype": "Link", "options": "Integration Exception", "width": 140},
		{"fieldname": "channel", "label": _("Channel"), "fieldtype": "Link", "options": "Channel", "width": 160},
		{"fieldname": "channel_order_id", "label": _("Channel Order"), "fieldtype": "Data", "width": 150},
		{"fieldname": "failure_stage", "label": _("Stage"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "age_days", "label": _("Age (Days)"), "fieldtype": "Int", "width": 100},
	]
	return columns, rows
