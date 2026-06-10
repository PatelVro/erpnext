# At-FBA location (C6, FLOW-DECISIONS D4, owner's B1): Amazon-held stock is
# REAL ledger stock in the operator-configured FBA warehouse. Outbound boxes
# transfer shelf → At-FBA (tagged with the Amazon Inbound Shipment ID); FBA
# sales deduct At-FBA per order; a periodic human true-up reconciles against
# Amazon's reported counts. The 1431 Yonge shelf is never touched by any of
# this beyond the deliberate outbound transfer. WFS stays informational
# (OPEN, per the plan). Leave fba_warehouse unset to keep FBA unmodeled.

import frappe
from frappe import _
from frappe.utils import flt, nowdate, nowtime


def _fba_warehouse():
	return frappe.db.get_single_value("Canadian Outlet Settings", "fba_warehouse")


@frappe.whitelist()
def record_fba_inbound(inbound_shipment_id, items):
	"""Record one outbound box to Amazon: a submitted Material Transfer from
	the shelf to At-FBA, tagged with the Inbound Shipment ID. Idempotent per
	inbound id. `items` = {item_code: qty} (JSON string accepted)."""
	import json

	if isinstance(items, str):
		items = json.loads(items)

	fba_warehouse = _fba_warehouse()
	shelf = frappe.db.get_single_value("Canadian Outlet Settings", "default_warehouse")
	if not fba_warehouse or not shelf:
		frappe.throw(_("Canadian Outlet Settings: default_warehouse and fba_warehouse are required"))

	remarks = f"Amazon Inbound Shipment {inbound_shipment_id}"
	if frappe.db.exists("Stock Entry", {"remarks": remarks, "docstatus": 1}):
		frappe.throw(_("Inbound shipment {0} is already recorded").format(inbound_shipment_id))

	entry = frappe.get_doc({
		"doctype": "Stock Entry",
		"stock_entry_type": "Material Transfer",
		"company": frappe.db.get_value("Warehouse", fba_warehouse, "company"),
		"remarks": remarks,
		"items": [
			{
				"item_code": item_code,
				"qty": flt(qty),
				"s_warehouse": shelf,
				"t_warehouse": fba_warehouse,
			}
			for item_code, qty in items.items()
		],
	})
	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry.name


def issue_fba_sale(sales_order_doc):
	"""C6: an FBA sale deducts the At-FBA location, per order, automatically.
	No-op when FBA is unmodeled (fba_warehouse unset); a failed issue (e.g.
	count drift below zero) logs and never blocks the import — the periodic
	true-up is the corrective."""
	fba_warehouse = _fba_warehouse()
	if not fba_warehouse:
		return None
	try:
		entry = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"company": sales_order_doc.company,
			"remarks": f"FBA sale {sales_order_doc.co_channel_order_id} "
				f"({sales_order_doc.name})",
			"items": [
				{
					"item_code": line.item_code,
					"qty": line.qty,
					"s_warehouse": fba_warehouse,
				}
				for line in sales_order_doc.items
			],
		})
		entry.insert(ignore_permissions=True)
		entry.submit()
		return entry.name
	except Exception:
		frappe.log_error(
			title=f"FBA issue failed: {sales_order_doc.name}",
			message=frappe.get_traceback(),
		)
		return None


@frappe.whitelist()
def true_up_fba(items):
	"""Periodic human reconciliation (B1): set At-FBA counts to Amazon's
	reported numbers via a submitted Stock Reconciliation.
	`items` = {item_code: qty} (JSON string accepted)."""
	import json

	if isinstance(items, str):
		items = json.loads(items)

	fba_warehouse = _fba_warehouse()
	if not fba_warehouse:
		frappe.throw(_("Canadian Outlet Settings: fba_warehouse is not set"))

	reconciliation = frappe.get_doc({
		"doctype": "Stock Reconciliation",
		"purpose": "Stock Reconciliation",
		"company": frappe.db.get_value("Warehouse", fba_warehouse, "company"),
		"posting_date": nowdate(),
		"posting_time": nowtime(),
		"set_posting_time": 1,
		"items": [
			{
				"item_code": item_code,
				"warehouse": fba_warehouse,
				"qty": flt(qty),
				"valuation_rate": flt(
					frappe.db.get_value("Item", item_code, "valuation_rate")
				) or 1,
			}
			for item_code, qty in items.items()
		],
	})
	reconciliation.insert(ignore_permissions=True)
	reconciliation.submit()
	return reconciliation.name
