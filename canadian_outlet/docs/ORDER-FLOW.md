# Canadian Outlet ERP — Order Flow

Status: Phase 1 planning document. Normative once approved.
Governing invariants: INV-2, INV-3, INV-4, INV-5, INV-6, INV-9, INV-10, INV-11.

> **Precedence note (2026-06-10):** the owner's workflow decisions in
> `docs/FLOW-DECISIONS.md` are the top business authority. Sections of this
> document that conflict with it are superseded; each implementation phase of
> `docs/BUILD-CHANGE-PLAN.md` rewrites the affected sections here in the same
> change.

This document defines the single pipeline by which external marketplace orders
become ERPNext Sales Orders. There is exactly one pipeline (INV-9); channel
adapters differ only in how they fetch and translate payloads into the common
import shape.

---

## 1. Pipeline overview

```
Channel payload (WooCommerce first; Amazon/Walmart in later phases)
        │
        ▼
Channel adapter
  – fetch/receive payload
  – translate to the canonical ImportedOrder shape
  – NO business decisions, NO Frappe writes
        │
        ▼
Order Import Service  (the only entry point — INV-9)
  1. Record attempt in Order Import Log
  2. Idempotency check (INV-11A): channel + channel_order_id
       already imported → log duplicate, stop (success, no-op)
  3. Resolve every line via Channel Listing (INV-2, INV-3)
       any line unresolved → Integration Exception, stop (INV-4, INV-10)
  4. Classify fulfillment via Channel Fulfillment Map (INV-5)
       result UNKNOWN → Integration Exception, stop (INV-6, INV-10)
  5. Resolve/create Customer per the customer policy (§4)
  6. Create AND SUBMIT Sales Order (atomic: all lines or nothing — INV-10)
       set co_sales_channel, co_channel_order_id, co_fulfillment_type
       submission places the availability HOLD (INV-12, C1); SELF lines carry
       the default warehouse; channel-cancelled orders are cancelled in place
  7. Mark Order Import Log entry with outcome
        │
        ├── success → Sales Order (draft, standard ERPNext lifecycle)
        └── failure → Integration Exception (deduplicated per INV-11C)
```

Stock consequences of the resulting Sales Order are defined in
`docs/STOCK-FLOW.md` — the import pipeline itself never touches stock.

## 2. Canonical import shape

Adapters translate channel payloads into one canonical structure consumed by the
Order Import Service. Defined precisely in Phase 5; its required content is:

- channel identifier (link to Channel)
- `channel_order_id` (external order ID, exactly as the channel provides it)
- order-level fulfillment evidence (e.g. Amazon fulfillment channel, Walmart ship
  node type; for WooCommerce, the constant SELF mapping)
- lines: external item identity (exactly as provided), quantity, unit price,
  currency
- buyer/shipping info as needed by the customer policy (§4), minimized per the
  payload/PII rules in `docs/DATA-MODEL.md`

## 3. Failure handling

- Every stop in steps 2–6 is recorded: duplicates in the Order Import Log,
  failures as Integration Exceptions linked from the log entry.
- An Integration Exception carries enough to diagnose and replay (see
  `docs/DATA-MODEL.md`): channel, channel_order_id, failure stage, failure reason,
  redacted/minimal payload fields, payload hash.
- Repeated failure of the same order for the same cause updates the existing open
  exception (INV-11C); it never creates duplicates.
- **Resolution loop:** a human fixes the underlying cause (e.g. creates the
  missing Channel Listing) and sets the exception to `Resolved`, then triggers
  replay. Replay re-enters the pipeline at step 1 like any other delivery and is
  therefore idempotent by construction. **Resolved does not mean imported** —
  the order counts as imported only when replay succeeds (Order Import Log
  outcome `Created`). A replay that fails again sets the exception status to
  `Failed Replay`. Payload data carried by exceptions follows
  `docs/PRIVACY-REDACTION.md`.

## 4. Customer policy

OPEN (Phase 0 question 7) — decision required before Phase 5 implementation.

Conservative working default until decided: **one generic Customer per Channel**
(e.g. "WooCommerce Customer"), with order-specific shipping details carried on the
Sales Order's shipping address. This avoids importing buyer PII into the Customer
master by default. If per-buyer Customers are chosen instead, the redaction/
retention policy (Phase 1.5) must cover the Customer master too.

## 5. What the pipeline never does

- Never creates an Item (INV-1, INV-4).
- Never guesses a fulfillment type (INV-5); never writes UNKNOWN or blank to
  `co_fulfillment_type` (INV-6).
- Never creates a partial Sales Order (INV-10).
- Submits the Sales Order on arrival (C1/INV-12 — the hold), but never creates
  or submits any stock-impacting document; holds are not deductions (INV-8).
- Never stores full raw payloads (see payload/PII rules in `docs/DATA-MODEL.md`).

## 6. V1 scope boundaries

- **Channels:** WooCommerce (Phase 13), Amazon (Phase 15), Walmart (Phase 16)
  — all live through the one shared pipeline; classification rules per INV-5.
- **Transport:** manual/operator-triggered import runs and manual replay.
  A scheduled polling job is **not** implied by this — scheduled jobs of any
  kind require their own explicit approval (see ERP-INVARIANTS out-of-scope
  list). The WooCommerce **webhook receiver exists** under this section's
  condition — signature verification and idempotency are demonstrated by
  tests (`tests/test_woocommerce_webhook.py`): HMAC-SHA256 with constant-time
  comparison, invalid/tampered deliveries create nothing, duplicates are
  idempotent via the shared pipeline, and the kill switch raises so the
  source retries later.
- **Draft Delivery Note on import:** NOT created in V1 by default. Auto-creating a
  draft Delivery Note for SELF orders is a candidate convenience for a later
  explicitly scoped change (OPEN — Phase 0 question 6). Until then, operators
  create the Delivery Note from the Sales Order using standard ERPNext flow.
- **Pricing/taxes:** OPEN (Phase 0 question 9) — working assumption CAD-only,
  marketplace-computed totals carried onto the Sales Order; to be finalized
  before Phase 6.
