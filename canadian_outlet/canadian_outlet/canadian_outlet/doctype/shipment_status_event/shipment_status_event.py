# Shipment Status Event: append-only carrier status record (Phase 14,
# docs/DATA-MODEL.md section 7A). Status sync only — never stock (INV-8).
# Permissions deliberately omit write/delete; rows are created by
# co_shipping.shipstation and never edited.

from frappe.model.document import Document


class ShipmentStatusEvent(Document):
	pass
