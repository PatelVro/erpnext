# Canadian Outlet Settings: singleton for operator-facing business toggles
# (docs/DATA-MODEL.md section 6). Deployment configuration and secrets live in
# site config instead (docs/CONFIGURATION.md section 2).

from frappe.model.document import Document


class CanadianOutletSettings(Document):
	pass
