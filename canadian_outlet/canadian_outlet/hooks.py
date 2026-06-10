app_name = "canadian_outlet"
app_title = "Canadian Outlet"
app_publisher = "Canadian Outlet"
app_description = "Canadian Outlet business logic for ERPNext"
app_email = "torvaldsl8@gmail.com"
app_license = "Proprietary"

required_apps = ["erpnext"]

# Schema guarantees that must exist on FRESH installs too (patches are marked
# completed on fresh installs, so they cannot be the only mechanism). Runs
# after fixtures on install and migrate.
after_sync = ["canadian_outlet.install.after_sync"]

# Phase 29: desk client scripts — plain JS served from public/, no build step
# (the old repo's CDN-React frontend stays retired). Buttons only call the
# same whitelisted services used from the console; no business logic in JS.
doctype_js = {
	"Integration Exception": "public/js/integration_exception.js",
	"Sales Order": "public/js/sales_order.js",
}
doctype_list_js = {
	"Integration Exception": "public/js/integration_exception_list.js",
}

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
					"Sales Order-co_quarantined",
				],
			]
		],
	}
]

# Phase 24: the ONLY approved scheduled jobs (T-PIPE-1 pins this exact set).
# Both no-op unless their kill switches are deliberately enabled.
scheduler_events = {
	"daily": ["canadian_outlet.co_core.scheduler.daily_channel_sync"],
	"weekly": ["canadian_outlet.co_core.scheduler.weekly_retention_purge"],
}

# Per AGENTS.md, every hook added here must arrive in an explicitly approved
# phase and cite the invariant it implements (docs/ERP-INVARIANTS.md).
# The following stay empty until their phase is approved:
#   - doc_events            (no Sales Order / Delivery Note automation)
#   - override_doctype_class (never — ERPNext core behavior stays untouched)
