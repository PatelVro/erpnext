# Fulfillment classification (Phase 9). Implements INV-5: classification comes
# only from explicit Channel Fulfillment Map rows. Missing, unrecognized, or
# contradictory evidence returns UNKNOWN — which the import pipeline must
# treat as blocking (INV-6, INV-10). UNKNOWN is classifier-internal and is
# never written to any document.

import frappe

UNKNOWN = "UNKNOWN"
VALID_FULFILLMENT_TYPES = ("SELF", "FBA", "WFS")


def classify_fulfillment(channel, evidence):
	if not evidence:
		return UNKNOWN

	matched_types = set()
	for key, value in evidence.items():
		fulfillment_type = frappe.db.get_value(
			"Channel Fulfillment Map",
			{"channel": channel, "evidence_key": str(key), "evidence_value": str(value)},
			"fulfillment_type",
		)
		if fulfillment_type:
			matched_types.add(fulfillment_type)

	if len(matched_types) == 1:
		return matched_types.pop()
	# No match, or contradictory matches: fail closed (never default to SELF).
	return UNKNOWN
