# Order Import Log: append-only record of every import attempt — the INV-11A
# evidence trail (docs/DATA-MODEL.md section 7). Not the enforcement mechanism:
# order-level idempotency is enforced by the unique (co_sales_channel,
# co_channel_order_id) pair on Sales Order. Permissions deliberately omit
# write/delete; rows are created by the Order Import Service and never edited.

from frappe.model.document import Document


class OrderImportLog(Document):
	pass
