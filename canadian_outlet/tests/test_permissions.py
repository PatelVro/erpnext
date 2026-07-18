# Phase 20 tests — the Canadian Outlet Operations role. Triage-driven rights:
# operations staff fix Channel Listings and work Integration Exceptions;
# configuration (channels, rules, settings) and audit trails are read-only.

import frappe
from frappe.tests.utils import FrappeTestCase

ROLE = "Canadian Outlet Operations"


def _perm(doctype):
	rows = [p for p in frappe.get_meta(doctype).permissions if p.role == ROLE]
	assert len(rows) == 1, f"expected exactly one {ROLE} permission row on {doctype}"
	return rows[0]


class TestOperationsRole(FrappeTestCase):
	def test_role_exists_with_desk_access(self):
		self.assertTrue(frappe.db.exists("Role", ROLE))
		self.assertEqual(frappe.db.get_value("Role", ROLE, "desk_access"), 1)

	def test_listing_triage_rights(self):
		perm = _perm("Channel Listing")
		self.assertEqual((perm.read, perm.write, perm.create, perm.delete or 0), (1, 1, 1, 0))

	def test_exception_triage_rights(self):
		perm = _perm("Integration Exception")
		self.assertEqual((perm.read, perm.write, perm.create or 0, perm.delete or 0), (1, 1, 0, 0))

	def test_configuration_is_read_only(self):
		for doctype in ("Channel", "Channel Fulfillment Map", "Canadian Outlet Settings"):
			perm = _perm(doctype)
			self.assertEqual(perm.read, 1, doctype)
			self.assertFalse(perm.write, doctype)
			self.assertFalse(perm.create, doctype)

	def test_audit_trails_are_read_only(self):
		for doctype in ("Order Import Log", "Shipment Status Event"):
			perm = _perm(doctype)
			self.assertEqual(perm.read, 1, doctype)
			self.assertFalse(perm.write, doctype)
			self.assertFalse(perm.create, doctype)
			self.assertFalse(perm.delete, doctype)
