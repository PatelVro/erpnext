# Secret scrubbing (docs/CONFIGURATION.md §5, T-CFG-2): any free text destined
# for a stored record (failure_reason, log text) passes through scrub_secrets
# so co_* site-config values can never leak into the database.

import frappe

MASK = "[REDACTED]"


def scrub_secrets(text):
	if not text:
		return text
	for key in list(frappe.conf or {}):
		if not (isinstance(key, str) and key.startswith("co_")):
			continue
		value = frappe.conf.get(key)
		if isinstance(value, str) and value and value in text:
			text = text.replace(value, MASK)
	return text
