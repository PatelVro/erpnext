# T-CFG-1..2 (docs/TEST-PLAN.md) — docs/CONFIGURATION.md §2 and §5: required
# config fails loudly naming the key; secrets never reach stored records.
# Written before implementation (Phase 7); defines the co_core contract.

import frappe
from frappe.tests.utils import FrappeTestCase


class TestConfiguration(FrappeTestCase):
	def test_t_cfg_1_missing_required_key_fails_naming_the_key(self):
		# T-CFG-1: no silent defaults for required configuration.
		from canadian_outlet.co_core.settings import MissingConfigError, get_required_conf

		missing_key = "co_definitely_missing_key_for_test"
		self.assertIsNone(frappe.conf.get(missing_key))
		with self.assertRaises(MissingConfigError) as ctx:
			get_required_conf(missing_key)
		self.assertIn(missing_key, str(ctx.exception))

	def test_t_cfg_2_secret_values_are_scrubbed_from_text(self):
		# T-CFG-2: any co_* site-config value is masked before text is stored
		# or logged (docs/CONFIGURATION.md §5). The scrubber is the contract;
		# exception/log writers must pass free text through it.
		from canadian_outlet.co_core.redaction import scrub_secrets

		secret_value = "synthetic-secret-T-CFG-2-do-not-store"
		original = frappe.conf.get("co_test_secret")
		frappe.conf["co_test_secret"] = secret_value
		try:
			scrubbed = scrub_secrets(f"call failed: 401 for key {secret_value} at endpoint")
			self.assertNotIn(secret_value, scrubbed)
			self.assertIn("401", scrubbed)
		finally:
			if original is None:
				frappe.conf.pop("co_test_secret", None)
			else:
				frappe.conf["co_test_secret"] = original
