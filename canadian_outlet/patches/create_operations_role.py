# Creates the Canadian Outlet Operations role (Phase 20). Runs as a patch so
# the Role exists BEFORE DocType schema sync applies the permission rows that
# reference it. Rights philosophy: operations staff fix Channel Listings and
# work Integration Exceptions; channel/rule/settings configuration and audit
# trails are read-only for them.

import frappe

ROLE = "Canadian Outlet Operations"


def execute():
	if frappe.db.exists("Role", ROLE):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": ROLE,
			"desk_access": 1,
		}
	).insert(ignore_permissions=True)
