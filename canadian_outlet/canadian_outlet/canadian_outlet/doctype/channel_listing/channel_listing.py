# Channel Listing: the single external-to-internal product mapping
# (docs/DATA-MODEL.md section 4). Implements INV-2: only this DocType maps a
# marketplace identity to an ERPNext Item.

import frappe
from frappe import _
from frappe.model.document import Document


class ChannelListing(Document):
	def validate(self):
		self._validate_unique_identity()

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
