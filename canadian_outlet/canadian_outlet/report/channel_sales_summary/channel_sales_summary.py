# Channel Sales Summary (Phase 22): Sales Orders grouped by channel and
# fulfillment type. Reads existing data only — no writes, no business rules.

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"co_sales_channel": ("is", "set"), "docstatus": ("<", 2)}
	if filters.get("from_date"):
		conditions["transaction_date"] = (">=", filters.from_date)
	if filters.get("channel"):
		conditions["co_sales_channel"] = filters.channel

	rows = frappe.get_all(
		"Sales Order",
		filters=conditions,
		fields=[
			"co_sales_channel as channel",
			"co_fulfillment_type as fulfillment_type",
			"count(name) as orders",
			"sum(base_grand_total) as total",
		],
		group_by="co_sales_channel, co_fulfillment_type",
		order_by="co_sales_channel",
	)

	columns = [
		{"fieldname": "channel", "label": _("Channel"), "fieldtype": "Link", "options": "Channel", "width": 200},
		{"fieldname": "fulfillment_type", "label": _("Fulfillment"), "fieldtype": "Data", "width": 110},
		{"fieldname": "orders", "label": _("Orders"), "fieldtype": "Int", "width": 90},
		{"fieldname": "total", "label": _("Total (Company Currency)"), "fieldtype": "Currency", "width": 180},
	]
	return columns, rows
