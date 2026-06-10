# Product 360 (C10, FLOW-DECISIONS D4): the owner's weekly questions on one
# screen — how many, where, reserved/available, listed on which channels,
# selling how fast, refill or not. Read-only; refill stays a human decision.

import frappe
from frappe.utils import add_days, flt, nowdate


def execute(filters=None):
	columns = [
		{"fieldname": "item_code", "label": "Item", "fieldtype": "Link", "options": "Item", "width": 180},
		{"fieldname": "item_name", "label": "Name", "fieldtype": "Data", "width": 200},
		{"fieldname": "shelf_qty", "label": "Shelf", "fieldtype": "Float", "width": 80},
		{"fieldname": "fba_qty", "label": "At FBA", "fieldtype": "Float", "width": 80},
		{"fieldname": "reserved_qty", "label": "On Hold", "fieldtype": "Float", "width": 80},
		{"fieldname": "available_qty", "label": "Available", "fieldtype": "Float", "width": 90},
		{"fieldname": "channels", "label": "Listed On", "fieldtype": "Data", "width": 200},
		{"fieldname": "sold_30d", "label": "Sold 30d", "fieldtype": "Float", "width": 90},
		{"fieldname": "last_purchase_rate", "label": "Last Buy Rate", "fieldtype": "Currency", "width": 110},
		{"fieldname": "reorder_level", "label": "Reorder Lvl", "fieldtype": "Float", "width": 90},
		{"fieldname": "refill", "label": "Refill?", "fieldtype": "Data", "width": 80},
	]

	shelf = frappe.db.get_single_value("Canadian Outlet Settings", "default_warehouse")
	fba = frappe.db.get_single_value("Canadian Outlet Settings", "fba_warehouse")
	since = add_days(nowdate(), -30)

	def bin_value(item_code, warehouse, field):
		if not warehouse:
			return 0
		return flt(frappe.db.get_value(
			"Bin", {"item_code": item_code, "warehouse": warehouse}, field))

	data = []
	for item in frappe.get_all(
		"Item", filters={"disabled": 0, "is_stock_item": 1},
		fields=["item_code", "item_name", "last_purchase_rate"],
		order_by="item_code",
	):
		channels = frappe.get_all(
			"Channel Listing", filters={"item": item.item_code, "status": "Active"},
			pluck="channel",
		)
		sold = frappe.db.sql(
			"""select ifnull(sum(soi.qty), 0) from `tabSales Order Item` soi
			join `tabSales Order` so on so.name = soi.parent
			where soi.item_code = %s and so.docstatus = 1 and so.transaction_date >= %s""",
			(item.item_code, since),
		)[0][0]
		reorder_level = flt(frappe.db.get_value(
			"Item Reorder", {"parent": item.item_code}, "warehouse_reorder_level"))
		shelf_qty = bin_value(item.item_code, shelf, "actual_qty")
		reserved = bin_value(item.item_code, shelf, "reserved_qty")
		available = shelf_qty - reserved
		data.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"shelf_qty": shelf_qty,
			"fba_qty": bin_value(item.item_code, fba, "actual_qty"),
			"reserved_qty": reserved,
			"available_qty": available,
			"channels": ", ".join(sorted(set(channels))),
			"sold_30d": flt(sold),
			"last_purchase_rate": flt(item.last_purchase_rate),
			"reorder_level": reorder_level,
			"refill": "REFILL" if reorder_level and available < reorder_level else "",
		})
	return columns, data
