# Canadian Outlet ERP — Invariants

Status: Phase 1 planning document. Normative.
Applies to: the `canadian_outlet` custom Frappe app. ERPNext core is upstream and is never modified.

These invariants are the constitution of this system. Code, tests, fixtures, and
documentation must conform to them. Any change to an invariant requires an explicit,
recorded human decision — never an implementation-time judgement call.

Each invariant is testable. `docs/TEST-PLAN.md` maps tests to invariants by ID.

---

## INV-1 — ERPNext Item is the internal product master

- The standard ERPNext **Item** DocType is the single internal representation of a product.
- No parallel or replacement product DocType is ever created (no "CO Item").
- Order import code must **never** create an Item. Items are created only by humans
  (or by an explicitly scoped, human-approved catalog process in a future phase).

## INV-2 — Channel Listing is the only external→internal product mapping

- The **Channel Listing** DocType is the single source of truth mapping an external
  marketplace identity (channel + external SKU / listing ID / ASIN / Walmart item ID)
  to an internal ERPNext Item.
- No other table, script, field, or convention (e.g. "the external SKU equals the
  item_code") may be used to resolve external products to Items.

## INV-3 — Order lines resolve through Channel Listing before Item

- Every external order line must be resolved via Channel Listing **before** any
  ERPNext Item is referenced.
- Resolution input is the external identity exactly as provided by the channel;
  no normalization heuristics that could silently change which Item is matched.

## INV-4 — Unknown listings create Integration Exception, never Items

- If an order line's external identity has no active Channel Listing, the import
  creates an **Integration Exception** for human review.
- The import must not create an Item, must not guess an Item, and (per INV-10)
  must not create a partial Sales Order.

## INV-5 — Fulfillment is derived from explicit evidence, never guessed

- Fulfillment classification uses explicit channel evidence via the
  **Channel Fulfillment Map** (e.g. Amazon `AFN`/`MFN`, Walmart WFS markers).
- Baseline rules:
  - WooCommerce → SELF
  - Amazon AFN → FBA
  - Amazon MFN → SELF
  - Walmart WFS → WFS
  - Walmart seller-fulfilled → SELF
- Missing, unrecognized, or contradictory evidence → classification result is
  UNKNOWN. **UNKNOWN must never be coerced to SELF** (or to any other value).

## INV-6 — Sales Order fulfillment type is SELF, FBA, or WFS only

- The custom field `Sales Order.co_fulfillment_type` permits exactly three values:
  `SELF`, `FBA`, `WFS`.
- `UNKNOWN` exists only inside the classifier as an intermediate result. An order
  classified UNKNOWN is **blocked from import** and becomes an Integration
  Exception (INV-10). A Sales Order with an empty or invalid `co_fulfillment_type`
  must never be produced by the import pipeline.

## INV-7 — Only SELF fulfillment can affect local stock

- `SELF` is the only fulfillment type whose orders may ever cause a movement of
  Canadian Outlet's local ERPNext stock.
- `FBA` and `WFS` orders must **never** create, submit, or trigger any
  stock-impacting ERPNext document against local warehouses. Marketplace-held
  inventory is not modeled as local ERPNext stock.

## INV-8 — Stock deducts only on a submitted stock-impacting document

- A **draft Delivery Note is not a stock deduction.** Draft documents must never be
  counted, reported, or treated as posted stock movements anywhere in code,
  reporting, or reconciliation.
- Stock deduction occurs only when a valid stock-impacting ERPNext document
  (Delivery Note, or where explicitly scoped, Stock Entry) is **submitted**
  (`docstatus = 1`).
- In V1 the submitter is a human (see `docs/STOCK-FLOW.md`). No automation submits
  stock-impacting documents until a later phase explicitly approves it.

## INV-9 — One shared Order Import Service

- All order ingestion — every channel, every transport (API poll, webhook, manual
  replay) — goes through the single app-level **Order Import Service**.
- No host scripts, console one-offs, or per-channel side paths may create Sales
  Orders, Customers, Items, or stock documents outside this service.

## INV-10 — Fail closed; imports are atomic

- Any unknown, ambiguous, or unsafe condition stops the import of that order and
  produces an Integration Exception for human review. The system never guesses.
- Imports are **atomic at the order level**: if any required order line cannot be
  resolved to an Item (INV-3/INV-4) or the order cannot be classified to a valid
  fulfillment type (INV-5/INV-6), **no Sales Order is created at all**. Partial
  Sales Orders are forbidden.

## INV-11 — Imports are idempotent

Re-delivery of the same external data (duplicate webhook, overlapping poll window,
manual replay) must not duplicate any record or effect.

- **INV-11A — order level:** the same external order (identified by
  `channel + channel_order_id`) imported more than once results in exactly one
  Sales Order, with the duplicate attempt recorded in the Order Import Log.
- **INV-11B — line level:** re-processing an order must not duplicate Sales Order
  Items, nor double any quantity.
- **INV-11C — exception level:** repeated failures of the same external order for
  the same cause result in exactly one open Integration Exception (subsequent
  occurrences update/annotate it, not duplicate it).

---

## Explicitly out of scope until separately approved

These are not invariants; they are reminders that the following do **not** exist in
V1 and must not be built opportunistically:

- Automatic stock posting from ShipStation or any shipment event
- Scheduled jobs of any kind
- Amazon / Walmart importers (WooCommerce is first; see phase plan)
- Payment reconciliation
- Frontend pages / dashboards

## Open items (must be resolved before the affected phase)

- ~~Redaction & retention policy~~ — **decided (Phase 4)**: see
  `docs/PRIVACY-REDACTION.md` (allowlist redaction, disallowed-PII list, 90-day
  post-terminal retention). No longer blocks Integration Exception.
- **Customer creation policy** on import (generic per-channel Customer vs.
  per-buyer Customer records). See `docs/ORDER-FLOW.md`.
