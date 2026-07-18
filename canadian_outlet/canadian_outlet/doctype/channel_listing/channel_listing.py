# Channel Listing: the single external-to-internal product mapping
# (docs/DATA-MODEL.md section 4). Implements INV-2: only this DocType maps a
# marketplace identity to an ERPNext Item.

import frappe
from frappe import _
from frappe.model.document import Document


class ChannelListing(Document):
	def validate(self):
		self._validate_unique_identity()
		self._validate_item_enabled()

	def after_insert(self):
		self._fix_and_flow()

	def _fix_and_flow(self):
		# C4 (FLOW-DECISIONS D8): confirming a mapping IS the fix — every
		# order stuck on this exact (channel, external_identity) re-imports
		# immediately. Controller-level, not hooks.doc_events, so T-PIPE-1's
		# no-side-channel pin stays meaningful. Failures are logged per
		# exception and never block the mapping itself.
		if self.status != "Active":
			return
		stuck = frappe.get_all(
			"Integration Exception",
			filters={
				"channel": self.channel,
				"external_identity": self.external_identity,
				"failure_stage": "Resolution",
				"status": ("in", ["Open", "In Review", "Failed Replay"]),
			},
			pluck="name",
		)
		for name in stuck:
			try:
				frappe.db.set_value("Integration Exception", name, "status", "Resolved")
				from canadian_outlet.co_orders.replay import replay_exception

				replay_exception(name)
			except Exception:
				frappe.log_error(
					title=f"Fix-and-flow replay failed: {name}",
					message=frappe.get_traceback(),
				)

	def _validate_item_enabled(self):
		# A listing to a disabled Item would fail closed at resolution and
		# flood Integration Exceptions; catch it at mapping time instead
		# (INV-2 hygiene — surfaced by the Channel Listing Health report).
		if frappe.db.get_value("Item", self.item, "disabled"):
			frappe.throw(_("Item {0} is disabled and cannot be mapped").format(self.item))

	def _validate_unique_identity(self):
		# (channel, external_identity) is unique: one external identity maps
		# to exactly one Item per channel (INV-2, docs/DATA-MODEL.md section 4).
		duplicate = frappe.db.exists(
			"Channel Listing",
			{
				"channel": self.channel,
				"external_identity": self.external_identity,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("A Channel Listing for {0} / {1} already exists: {2}").format(
					self.channel, self.external_identity, duplicate
				)
			)
