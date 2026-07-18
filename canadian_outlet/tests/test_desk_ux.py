# Phase 29 tests — desk UX wiring. Client scripts are browser code the suite
# cannot execute; what it CAN pin: the hook registrations point at files that
# exist, the JS calls only whitelisted service methods that exist, and no
# server-side automation hooks crept in alongside (T-PIPE-1 still guards
# doc_events/scheduler independently).

import os

import frappe
from frappe.tests.utils import FrappeTestCase

import canadian_outlet
from canadian_outlet import hooks

APP_PATH = os.path.dirname(canadian_outlet.__file__)


class TestDeskUx(FrappeTestCase):
	def test_doctype_js_files_exist(self):
		for mapping in (hooks.doctype_js, hooks.doctype_list_js):
			for doctype, path in mapping.items():
				self.assertTrue(
					os.path.exists(os.path.join(APP_PATH, path)),
					f"{doctype} -> {path} missing",
				)

	def test_js_calls_only_existing_whitelisted_methods(self):
		import re

		called = set()
		for mapping in (hooks.doctype_js, hooks.doctype_list_js):
			for path in mapping.values():
				content = open(os.path.join(APP_PATH, path)).read()
				called.update(re.findall(r'"(canadian_outlet\.[\w.]+)"', content))

		self.assertTrue(called, "expected the form scripts to call app methods")
		for dotted in called:
			method = frappe.get_attr(dotted)
			self.assertTrue(callable(method), dotted)
			self.assertIn(method, frappe.whitelisted, f"{dotted} is not whitelisted")

	def test_workspace_shows_open_exception_count(self):
		shortcuts = frappe.get_all(
			"Workspace Shortcut",
			filters={"parent": "Canadian Outlet", "link_to": "Integration Exception"},
			fields=["stats_filter"],
		)
		self.assertTrue(shortcuts)
		self.assertIn("Open", shortcuts[0].stats_filter or "")
