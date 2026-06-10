app_name = "canadian_outlet"
app_title = "Canadian Outlet"
app_publisher = "Canadian Outlet"
app_description = "Canadian Outlet business logic for ERPNext"
app_email = "torvaldsl8@gmail.com"
app_license = "Proprietary"

required_apps = ["erpnext"]

# Phase 6: Sales Order custom fields shipped as fixtures (docs/DATA-MODEL.md §8).
# Filtered to exactly the three approved co_ fields — never a blanket export.
fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Sales Order-co_sales_channel",
					"Sales Order-co_channel_order_id",
					"Sales Order-co_fulfillment_type",
				],
			]
		],
	}
]

# Per AGENTS.md, every hook added here must arrive in an explicitly approved
# phase and cite the invariant it implements (docs/ERP-INVARIANTS.md).
# The following stay empty until their phase is approved:
#   - doc_events            (no Sales Order / Delivery Note automation)
#   - scheduler_events      (no scheduled jobs)
#   - override_doctype_class (never — ERPNext core behavior stays untouched)
