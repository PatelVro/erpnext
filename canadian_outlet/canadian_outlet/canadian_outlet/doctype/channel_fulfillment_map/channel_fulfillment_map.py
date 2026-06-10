# Channel Fulfillment Map: declarative evidence-to-classification rules
# (docs/DATA-MODEL.md section 3). Implements INV-5: fulfillment comes only
# from explicit, reviewable rows; a missing row means UNKNOWN, never SELF.

import frappe
from frappe import _
from frappe.model.document import Document


class ChannelFulfillmentMap(Document):
	def validate(self):
		self._validate_unique_rule()

	def _validate_unique_rule(self):
		# One classification per (channel, evidence_key, evidence_value):
		# duplicate rows could classify the same evidence two ways (INV-5).
		duplicate = frappe.db.exists(
			"Channel Fulfillment Map",
			{
				"channel": self.channel,
				"evidence_key": self.evidence_key,
				"evidence_value": self.evidence_value,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("A fulfillment rule for {0} / {1} / {2} already exists: {3}").format(
					self.channel, self.evidence_key, self.evidence_value, duplicate
				)
			)
