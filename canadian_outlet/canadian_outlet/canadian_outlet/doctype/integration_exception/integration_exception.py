# Integration Exception: fail-closed landing zone for unknown/unsafe imports
# (INV-4, INV-10) and the replay anchor (INV-11C). Status lifecycle per
# docs/DATA-MODEL.md section 5; payload fields per docs/PRIVACY-REDACTION.md.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

TERMINAL_STATUSES = ("Resolved", "Ignored")


class IntegrationException(Document):
	def validate(self):
		self._validate_ignored_reason()
		self._set_terminal_timestamp()

	def _validate_ignored_reason(self):
		# Ignored requires an explicit human reason (docs/DATA-MODEL.md §5);
		# server-side enforcement backing the UI mandatory_depends_on.
		if self.status == "Ignored" and not (self.ignored_reason or "").strip():
			frappe.throw(_("Ignored Reason is required when status is Ignored"))

	def _set_terminal_timestamp(self):
		# resolved_or_ignored_on drives the retention purge window
		# (docs/PRIVACY-REDACTION.md §5).
		if self.status in TERMINAL_STATUSES:
			if not self.resolved_or_ignored_on:
				self.resolved_or_ignored_on = now_datetime()
		else:
			self.resolved_or_ignored_on = None
