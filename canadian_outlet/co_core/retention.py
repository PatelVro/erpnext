# Operator-invoked retention purge (docs/PRIVACY-REDACTION.md §5-6).
# Clears stored payload copies (raw_payload_redacted, replay_payload_minimal)
# on TERMINAL exceptions past the retention window; payload_hash and
# external_payload_reference are retained indefinitely (no PII).
# Deliberately NOT a scheduled job — scheduler use stays gated (AGENTS.md);
# operations run this manually per docs/OPERATIONS.md.

import frappe
from frappe.utils import add_days, now_datetime

DEFAULT_RETENTION_DAYS = 90
TERMINAL_STATUSES = ("Resolved", "Ignored")


@frappe.whitelist()
def purge_expired_payload_copies(retention_days=DEFAULT_RETENTION_DAYS):
	cutoff = add_days(now_datetime(), -int(retention_days))
	expired = frappe.get_all(
		"Integration Exception",
		filters={
			"status": ("in", TERMINAL_STATUSES),
			"resolved_or_ignored_on": ("<", cutoff),
		},
		or_filters={
			"raw_payload_redacted": ("is", "set"),
			"replay_payload_minimal": ("is", "set"),
		},
		pluck="name",
	)
	for name in expired:
		frappe.db.set_value(
			"Integration Exception",
			name,
			{"raw_payload_redacted": None, "replay_payload_minimal": None},
		)
	return {"purged": len(expired), "cutoff": str(cutoff)}
