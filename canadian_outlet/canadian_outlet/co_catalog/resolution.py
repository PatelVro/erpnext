# Item resolution (Phase 8). Implements INV-2/INV-3: Channel Listing is the
# ONLY mapping from external marketplace identity to an ERPNext Item, and the
# match is exact — no normalization, no item_code conventions (T-RES-5), no
# Item creation ever (INV-1, INV-4). Unknown or inactive listings fail closed
# (INV-10) by raising UnresolvedListingError.

import frappe


class UnresolvedListingError(Exception):
	"""External identity has no Active Channel Listing (INV-2, INV-4)."""


def resolve_external_identity(channel, external_identity):
	item = frappe.db.get_value(
		"Channel Listing",
		{"channel": channel, "external_identity": external_identity, "status": "Active"},
		"item",
	)
	if not item:
		raise UnresolvedListingError(
			f"No active Channel Listing for channel={channel}, "
			f"external_identity={external_identity}"
		)
	return item
