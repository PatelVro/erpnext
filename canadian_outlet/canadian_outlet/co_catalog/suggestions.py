# Suggest-and-confirm (C4, FLOW-DECISIONS D2): the system PROPOSES likely
# Item matches for an unknown, messy marketplace SKU; the human decides.
# Suggestions never act on their own — confirming one simply means a human
# creates the Channel Listing (which fix-and-flow then replays).

import difflib
import re

import frappe


def _tokens(text):
	return set(re.findall(r"[A-Za-z0-9]+", (text or "").upper()))


def _score(sku_tokens, sku, candidate_text):
	candidate_tokens = _tokens(candidate_text)
	if not sku_tokens or not candidate_tokens:
		return 0.0
	overlap = len(sku_tokens & candidate_tokens) / len(sku_tokens)
	ratio = difflib.SequenceMatcher(
		None, sku.upper(), (candidate_text or "").upper()
	).ratio()
	return round(0.65 * overlap + 0.35 * ratio, 3)


@frappe.whitelist()
def suggest_matches(channel, external_identity, limit=5):
	"""Read-only ranked suggestions for an unmapped SKU. Pool: enabled Items,
	scored against item_code + item_name token overlap and text similarity."""
	sku_tokens = _tokens(external_identity)
	suggestions = []
	for item in frappe.get_all(
		"Item", filters={"disabled": 0, "is_stock_item": 1},
		fields=["item_code", "item_name"],
	):
		score = max(
			_score(sku_tokens, external_identity, item.item_code),
			_score(sku_tokens, external_identity, item.item_name),
		)
		if score > 0.2:
			suggestions.append(
				{"item_code": item.item_code, "item_name": item.item_name, "score": score}
			)
	suggestions.sort(key=lambda s: s["score"], reverse=True)
	return suggestions[: int(limit)]
