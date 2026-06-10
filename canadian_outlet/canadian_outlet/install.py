# Install/sync-time schema guarantees. Runs via the after_sync hook (fires
# after fixtures on BOTH fresh install and migrate) because Frappe marks all
# patches as completed on fresh installs — anything created only by a patch
# would silently not exist on a new site.

import frappe

OPERATIONS_ROLE = "Canadian Outlet Operations"
UNIQUE_CONSTRAINT = "co_channel_order_unique"


def after_sync():
	ensure_operations_role()
	ensure_channel_order_unique_index()


def ensure_operations_role():
	if frappe.db.exists("Role", OPERATIONS_ROLE):
		return
	frappe.get_doc(
		{"doctype": "Role", "role_name": OPERATIONS_ROLE, "desk_access": 1}
	).insert(ignore_permissions=True)


def ensure_channel_order_unique_index():
	"""INV-11A enforced at the DATABASE level: a unique index on
	(co_sales_channel, co_channel_order_id) closes the check-then-insert race
	between concurrent webhook/scheduler/manual imports. MariaDB unique
	indexes permit multiple NULLs, so manual (non-channel) Sales Orders are
	unaffected."""
	indexes = frappe.db.sql(
		"SHOW INDEX FROM `tabSales Order` WHERE Key_name = %s", UNIQUE_CONSTRAINT
	)
	if indexes:
		return
	frappe.db.add_unique(
		"Sales Order",
		["co_sales_channel", "co_channel_order_id"],
		constraint_name=UNIQUE_CONSTRAINT,
	)
