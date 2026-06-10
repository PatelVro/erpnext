# Approved scheduled jobs (Phase 24). Authorization: the operator's standing
# directive; ERP-INVARIANTS' out-of-scope list was amended in the same change
# and T-PIPE-1 pins hooks.scheduler_events to EXACTLY these two entries — any
# other scheduled automation still fails the suite.
#
# Fail-closed by design: both jobs no-op unless the relevant kill switches are
# deliberately enabled, so a fresh install schedules nothing into action.
# One channel failing must never block the others; failures are logged and
# the failed window is retried next run (imports are idempotent, INV-11).
# ShipStation shipment sync stays operator-run: shipments are per-account,
# not per-channel, and guessing the channel tag would violate INV-10.

import frappe
from frappe.utils import add_days, now_datetime

SYNC_WINDOW_DAYS = 2


def daily_channel_sync():
	if not frappe.db.get_single_value("Canadian Outlet Settings", "imports_enabled"):
		return {"skipped": "imports_disabled"}

	since = add_days(now_datetime(), -SYNC_WINDOW_DAYS).isoformat()
	summary = {}
	for channel in frappe.get_all(
		"Channel", filters={"enabled": 1}, fields=["name", "channel_type"]
	):
		try:
			summary[channel.name] = _sync_channel(channel, since)
		except Exception:
			summary[channel.name] = {"error": "logged"}
			frappe.log_error(
				title=f"Daily channel sync failed: {channel.name}",
				message=frappe.get_traceback(),
			)
	return summary


def _sync_channel(channel, since):
	if channel.channel_type == "WooCommerce":
		from canadian_outlet.co_orders.adapters.woocommerce import import_woocommerce_orders

		return import_woocommerce_orders(channel.name, modified_after=since)
	if channel.channel_type == "Amazon":
		from canadian_outlet.co_orders.adapters.amazon import import_amazon_orders

		return import_amazon_orders(channel.name, created_after=since)
	if channel.channel_type == "Walmart":
		from canadian_outlet.co_orders.adapters.walmart import import_walmart_orders

		return import_walmart_orders(channel.name, created_start_date=since)
	return {"skipped": f"unknown channel_type {channel.channel_type}"}


def weekly_retention_purge():
	from canadian_outlet.co_core.retention import purge_expired_payload_copies

	return purge_expired_payload_copies()
