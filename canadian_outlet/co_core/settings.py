# The only module that reads frappe.conf (docs/CONFIGURATION.md §2).
# Required keys fail loudly naming the key — no silent defaults (T-CFG-1).

import frappe


class MissingConfigError(frappe.ValidationError):
	pass


def get_required_conf(key):
	value = frappe.conf.get(key)
	if value in (None, ""):
		raise MissingConfigError(
			f"Missing required site config key: {key} (see docs/CONFIGURATION.md)"
		)
	return value


def get_optional_conf(key, default=None):
	value = frappe.conf.get(key)
	return default if value in (None, "") else value
