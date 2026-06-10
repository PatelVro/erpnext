# Channel: one row per sales channel instance (docs/DATA-MODEL.md section 2).
# Channels are instance data; no fixtures ship rows.

from frappe.model.document import Document


class Channel(Document):
	pass
