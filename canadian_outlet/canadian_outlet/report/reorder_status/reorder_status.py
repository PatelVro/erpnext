# Reorder Status (Phase 26): purchasing visibility from ERPNext's own
# reorder configuration (Item Reorder rows) and live Bin quantities. Strictly
# read-only — no Material Requests, no purchase automation, no invented
# policy; the reorder levels themselves are business data set by humans.

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = ""
	values = {}
	if filters.get("warehouse"):
		conditions += " and ir.warehouse = %(warehouse)s"
		values["warehouse"] = filters.warehouse

	rows = frappe.db.sql(
		f"""
		select
			ir.parent as item,
			ir.warehouse,
			coalesce(b.actual_qty, 0) as actual_qty,
			coalesce(b.projected_qty, 0) as projected_qty,
			ir.warehouse_reorder_level as reorder_level,
			ir.warehouse_reorder_qty as reorder_qty,
			ir.warehouse_reorder_level - coalesce(b.projected_qty, 0) as shortfall
		from `tabItem Reorder` ir
		inner join `tabItem` i on i.name = ir.parent and i.disabled = 0
		left join `tabBin` b on b.item_code = ir.parent and b.warehouse = ir.warehouse
		where coalesce(b.projected_qty, 0) < ir.warehouse_reorder_level
			{conditions}
		order by shortfall desc
		""",
		values,
		as_dict=True,
	)

	columns = [
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 200},
		{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"fieldname": "actual_qty", "label": _("Actual Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "projected_qty", "label": _("Projected Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "reorder_level", "label": _("Reorder Level"), "fieldtype": "Float", "width": 110},
		{"fieldname": "reorder_qty", "label": _("Reorder Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "shortfall", "label": _("Shortfall"), "fieldtype": "Float", "width": 100},
	]
	return columns, rows
