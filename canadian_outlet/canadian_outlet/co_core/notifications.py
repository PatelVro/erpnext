# Notifications (C7, FLOW-DECISIONS D6): the back-office tap on the shoulder.
# INSTANT email per STOP (new Integration Exception), a DAILY digest of the
# review queues, and a LOUDER escalation for anything untouched 3+ days.
# Recipient is operator-configured; unset → notifications skip quietly (the
# queues still exist in the desk). Sending is best-effort and never blocks
# the pipeline.

import frappe
from frappe.utils import add_days, now_datetime

ESCALATION_DAYS = 3


def _recipient():
	return frappe.db.get_single_value("Canadian Outlet Settings", "notification_email")


def _send(subject, message):
	recipient = _recipient()
	if not recipient:
		return False
	try:
		frappe.sendmail(recipients=[recipient], subject=subject, message=message,
			delayed=True)
		return True
	except Exception:
		frappe.log_error(title=f"Notification send failed: {subject}",
			message=frappe.get_traceback())
		return False


def notify_stop(exception_doc):
	"""Instant email per STOP — called from Integration Exception.after_insert."""
	_send(
		f"[CO STOP] {exception_doc.name}: {exception_doc.failure_stage} "
		f"({exception_doc.channel})",
		f"Order {exception_doc.channel_order_id or '-'} stopped at stage "
		f"{exception_doc.failure_stage}.<br>Reason: {exception_doc.failure_reason}<br>"
		f"Open it in ERPNext: Integration Exception {exception_doc.name}",
	)


def daily_review_digest():
	"""Scheduled daily (C7-amended T-PIPE-1 set). Summarizes everything
	waiting on a human; escalates separately for stale items."""
	open_exceptions = frappe.get_all(
		"Integration Exception", filters={"status": ("in", ["Open", "In Review", "Failed Replay"])},
		fields=["name", "failure_stage", "creation"],
	)
	quarantined = frappe.db.count("Sales Order", {"co_quarantined": 1, "docstatus": 0})
	unconverted = frappe.db.count(
		"Shipment Status Event",
		{"carrier_status": "shipped", "delivery_note": ("is", "not set"),
			"sales_order": ("is", "set")},
	)

	summary = {
		"open_exceptions": len(open_exceptions),
		"quarantined_orders": quarantined,
		"unconverted_shipments": unconverted,
		"escalations": 0,
	}

	if any((open_exceptions, quarantined, unconverted)):
		_send(
			f"[CO DAILY] {len(open_exceptions)} exceptions, {quarantined} quarantined, "
			f"{unconverted} unconverted shipments",
			"<br>".join([
				f"Open/active Integration Exceptions: {len(open_exceptions)}",
				f"Quarantined orders awaiting classification: {quarantined}",
				f"Shipped events awaiting deduction: {unconverted}",
			]),
		)

	cutoff = add_days(now_datetime(), -ESCALATION_DAYS)
	stale = [row for row in open_exceptions if row.creation < cutoff]
	if stale:
		summary["escalations"] = len(stale)
		names = ", ".join(row.name for row in stale[:20])
		_send(
			f"[CO ESCALATION] {len(stale)} item(s) untouched for {ESCALATION_DAYS}+ days",
			f"These have been waiting too long: {names}",
		)
	return summary
