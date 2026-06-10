# BIG RED BUTTON (C8, FLOW-DECISIONS D10, owner's 3b): when safe_mode is ON,
# nothing in this app may create or submit a stock- or money-impacting
# document — automatic OR one-click — while intake CONTINUES, with every new
# order arriving quarantined. Orders are never lost during a scare; numbers
# never move until a human turns the switch off. This is INV-13.

import frappe
from frappe import _


def is_safe_mode():
	return bool(frappe.db.get_single_value("Canadian Outlet Settings", "safe_mode"))


def assert_not_safe_mode(action):
	if is_safe_mode():
		frappe.throw(
			_("SAFE MODE is on (Canadian Outlet Settings): {0} is frozen. "
			"Orders keep arriving in quarantine; nothing moves stock or money "
			"until safe mode is turned off (INV-13).").format(action)
		)
