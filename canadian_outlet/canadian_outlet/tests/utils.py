# Shared synthetic fixtures for the Phase 7 test suite (docs/TEST-PLAN.md).
# Synthetic data only — never real payloads, credentials, or customer data
# (docs/CONFIGURATION.md §5, docs/PRIVACY-REDACTION.md).
#
# These tests are written BEFORE the implementation (tests-first). The imports
# they perform inside test methods define the API contract for Phases 8-11:
#   canadian_outlet.co_catalog.resolution.resolve_external_identity(channel, external_identity)
#       -> item_code, raises UnresolvedListingError (fail closed)
#   canadian_outlet.co_orders.classification.classify_fulfillment(channel, evidence: dict)
#       -> "SELF" | "FBA" | "WFS" | "UNKNOWN"  (UNKNOWN is classifier-internal)
#   canadian_outlet.co_orders.import_service.import_order(order: dict)
#       -> ImportResult(outcome, sales_order, integration_exception)
#       raises ImportsDisabledError when the kill switch or channel is off
#   canadian_outlet.co_core.settings.get_required_conf(key) -> value, raises naming the key
#   canadian_outlet.co_core.redaction.scrub_secrets(text) -> text with co_* conf values masked

import frappe

TEST_ITEM = "_Test Item"
TEST_CUSTOMER = "_Test Customer"
TEST_WAREHOUSE = "_Test Warehouse - _TC"
TEST_COMPANY = "_Test Company"

WOO_EVIDENCE = {"channel_source": "woocommerce"}
AMAZON_AFN_EVIDENCE = {"fulfillment_channel": "AFN"}
AMAZON_MFN_EVIDENCE = {"fulfillment_channel": "MFN"}
WALMART_WFS_EVIDENCE = {"ship_node_type": "WFSFulfilled"}
WALMART_SELLER_EVIDENCE = {"ship_node_type": "SellerFulfilled"}


def make_channel(name, channel_type="WooCommerce", enabled=1):
	if frappe.db.exists("Channel", name):
		doc = frappe.get_doc("Channel", name)
		doc.enabled = enabled
		doc.save()
		return doc
	return frappe.get_doc(
		{
			"doctype": "Channel",
			"channel_name": name,
			"channel_type": channel_type,
			"enabled": enabled,
			"default_customer": TEST_CUSTOMER,
		}
	).insert()


def make_listing(channel, external_identity, item=TEST_ITEM, status="Active"):
	existing = frappe.db.exists(
		"Channel Listing", {"channel": channel, "external_identity": external_identity}
	)
	if existing:
		doc = frappe.get_doc("Channel Listing", existing)
		doc.item = item
		doc.status = status
		doc.save()
		return doc
	return frappe.get_doc(
		{
			"doctype": "Channel Listing",
			"channel": channel,
			"external_identity": external_identity,
			"item": item,
			"status": status,
		}
	).insert()


def make_rule(channel, evidence_key, evidence_value, fulfillment_type):
	existing = frappe.db.exists(
		"Channel Fulfillment Map",
		{"channel": channel, "evidence_key": evidence_key, "evidence_value": evidence_value},
	)
	if existing:
		return frappe.get_doc("Channel Fulfillment Map", existing)
	return frappe.get_doc(
		{
			"doctype": "Channel Fulfillment Map",
			"channel": channel,
			"evidence_key": evidence_key,
			"evidence_value": evidence_value,
			"fulfillment_type": fulfillment_type,
		}
	).insert()


def company_currency(company=TEST_COMPANY):
	return frappe.get_cached_value("Company", company, "default_currency")


def default_currency():
	# The import service creates Sales Orders against the site's default
	# company, so synthetic orders must use THAT company's currency or the
	# insert fails on missing exchange rates. Production channels send real
	# currencies and the company is CAD — finalized with Phase 0 Q9.
	default_company = frappe.defaults.get_global_default("company")
	return frappe.get_cached_value("Company", default_company, "default_currency")


def make_order(channel, channel_order_id, lines=None, evidence=None, **overrides):
	# Canonical normalized order shape (docs/ORDER-FLOW.md §2).
	order = {
		"channel": channel,
		"channel_order_id": channel_order_id,
		"order_timestamp": "2026-01-01T00:00:00Z",
		"channel_status": "processing",
		"currency": default_currency(),
		"evidence": evidence if evidence is not None else dict(WOO_EVIDENCE),
		"lines": lines
		if lines is not None
		else [{"external_identity": "EXT-SKU-1", "qty": 1, "rate": 9.99}],
	}
	order.update(overrides)
	return order


def ensure_fulfillment_supplier():
	name = "CO Marketplace Fulfilled"
	if not frappe.db.exists("Supplier", name):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}),
			}
		).insert(ignore_permissions=True)
	return name


def enable_imports(default_warehouse=None):
	if default_warehouse is None:
		# SELF Sales Orders inherit this warehouse, and ERPNext requires it to
		# belong to the order's company — which is the site default company.
		default_company = frappe.defaults.get_global_default("company")
		default_warehouse = frappe.db.get_value(
			"Warehouse", {"company": default_company, "is_group": 0}
		)
	frappe.db.set_single_value("Canadian Outlet Settings", "imports_enabled", 1)
	frappe.db.set_single_value("Canadian Outlet Settings", "default_warehouse", default_warehouse)
	frappe.db.set_single_value(
		"Canadian Outlet Settings", "marketplace_fulfillment_supplier", ensure_fulfillment_supplier()
	)


def disable_imports():
	frappe.db.set_single_value("Canadian Outlet Settings", "imports_enabled", 0)


def get_exceptions(channel, channel_order_id=None, **extra_filters):
	filters = {"channel": channel}
	if channel_order_id:
		filters["channel_order_id"] = channel_order_id
	filters.update(extra_filters)
	return frappe.get_all(
		"Integration Exception", filters=filters, fields=["name", "status", "failure_stage"]
	)


def get_log_rows(channel, channel_order_id):
	return frappe.get_all(
		"Order Import Log",
		filters={"channel": channel, "channel_order_id": channel_order_id},
		fields=["name", "outcome", "sales_order", "integration_exception", "import_key"],
	)


def get_sales_orders(channel, channel_order_id):
	return frappe.get_all(
		"Sales Order",
		filters={"co_sales_channel": channel, "co_channel_order_id": channel_order_id},
		fields=["name", "co_fulfillment_type", "docstatus"],
	)
