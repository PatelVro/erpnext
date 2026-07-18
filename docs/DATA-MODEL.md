# Canadian Outlet ERP — Data Model

Status: Phase 1 planning document. Design only — **no DocType JSON exists yet**;
implementation happens in Phase 3 after explicit approval. Field lists below are
design intent, not generated schema.

Governing invariants: INV-1, INV-2, INV-4, INV-6, INV-11.

---

> **Precedence note (2026-06-10):** the owner's workflow decisions in
> `docs/FLOW-DECISIONS.md` are the top business authority. Sections of this
> document that conflict with it are superseded; each implementation phase of
> `docs/BUILD-CHANGE-PLAN.md` rewrites the affected sections here in the same
> change.

## 1. Principles

- Reuse ERPNext standard DocTypes: Item, Customer, Sales Order, Sales Order Item,
  Delivery Note, Delivery Note Item, Warehouse, Sales Invoice (Payment Entry later
  if needed). **No parallel replacements** for any of these (INV-1).
- Custom DocTypes are few, narrow, and integration-facing only.
- All custom fields on standard DocTypes are prefixed `co_` and delivered as
  fixtures from the `canadian_outlet` app (never created by hand in production).
- Nothing in this model stores full raw marketplace payloads (§9).

## 2. Custom DocType: Channel

One row per sales channel instance (e.g. "WooCommerce — canadianoutlet.ca").

| Field | Type | Notes |
|---|---|---|
| channel_name | Data (unique) | Human name; document name |
| channel_type | Select: WooCommerce / Amazon / Walmart | Adapter selector |
| enabled | Check | Disabled channel: no imports accepted |
| default_customer | Link Customer | Used under the generic-customer policy (`docs/ORDER-FLOW.md` §4) |

## 3. Custom DocType: Channel Fulfillment Map

Declarative evidence→classification rules per channel (INV-5). Keeps fulfillment
mapping data-driven and auditable instead of buried in adapter code.

| Field | Type | Notes |
|---|---|---|
| channel | Link Channel | |
| evidence_key | Data | e.g. `fulfillment_channel` |
| evidence_value | Data | e.g. `AFN`, `MFN`, `WFS` |
| fulfillment_type | Select: SELF / FBA / WFS | Never UNKNOWN — absence of a matching row *is* UNKNOWN |

Classifier contract: exact match on (channel, evidence_key, evidence_value) →
that row's fulfillment_type; no match → UNKNOWN → Integration Exception
(INV-5, INV-6, INV-10). Baseline rows (Woo→SELF, AFN→FBA, MFN→SELF, WFS→WFS,
Walmart seller-fulfilled→SELF) ship as reviewed fixtures in Phase 3.

## 4. Custom DocType: Channel Listing

The single external→internal product mapping (INV-2).

| Field | Type | Notes |
|---|---|---|
| channel | Link Channel | |
| external_identity | Data | SKU / ASIN / listing ID exactly as the channel provides it |
| item | Link Item | Internal master (INV-1) |
| status | Select: Active / Inactive | Inactive listings do not resolve; they fail closed to Integration Exception |

Uniqueness: (channel, external_identity) is unique. One external identity maps to
exactly one Item per channel. Many listings may point at the same Item.

Enforcement note (INV-11A): order-level idempotency is **enforced** by the unique
(co_sales_channel, co_channel_order_id) pair on Sales Order (§8); the Order
Import Log (§7) is the evidence trail, not the enforcement mechanism.

## 5. Custom DocType: Integration Exception

The fail-closed landing zone (INV-4, INV-10) and replay anchor.

| Field | Type | Notes |
|---|---|---|
| channel | Link Channel | |
| channel_order_id | Data | When order-scoped |
| failure_stage | Select: Resolution / Classification / Customer / Creation / Replay / Cancellation | Pipeline step that stopped; Cancellation = channel cancelled after shipment (C1) |
| failure_reason | Small Text | Human-readable; never contains secrets |
| external_identity | Data | For resolution failures |
| status | Select: **Open / In Review / Resolved / Ignored / Failed Replay** | The complete status set — no other value exists |
| ignored_reason | Small Text | **Mandatory when status = Ignored**; empty otherwise |
| resolved_or_ignored_on | Datetime | Set when status becomes terminal; drives the retention purge (PRIVACY-REDACTION.md §5) |
| dedup_key | Data (unique) | Hash of (channel, channel_order_id, failure_stage, cause) — enforces INV-11C |
| payload_hash | Data | §9 |
| raw_payload_redacted | Long Text | §9 |
| external_payload_reference | Data | §9 |
| replay_payload_minimal | Long Text | §9 |

Status semantics:

- `Open` — exception created, awaiting triage.
- `In Review` — someone is investigating or correcting the issue.
- `Resolved` — the blocking issue was fixed. **The order is not considered
  imported until a subsequent replay succeeds**; proof of import is the Order
  Import Log outcome `Created` (and the resulting Sales Order), not this
  status. After a successful replay the exception remains `Resolved`.
- `Ignored` — intentionally not imported (e.g. cancelled source order, test
  payload, confirmed non-actionable duplicate). Requires `ignored_reason`.
- `Failed Replay` — replay was attempted after resolution but import failed
  again; returns to triage. If the new failure has a **different** cause than
  the original, a new exception is created for the new cause (its own
  dedup_key, per INV-11C), linked back to the original.

## 6. Custom DocType: Canadian Outlet Settings

Single (singleton) DocType for operator-facing business toggles — as opposed to
deployment configuration, which lives in site config (`docs/CONFIGURATION.md` §2).

Initial fields are minimal and added per phase. Reserved from day one:

| Field | Type | Notes |
|---|---|---|
| imports_enabled | Check | Global kill switch for the Order Import Service |
| default_warehouse | Link Warehouse | 1431 Yonge (provisional, see `docs/STOCK-FLOW.md` §1). SELF Sales Orders inherit it on their items |
| marketplace_fulfillment_supplier | Link Supplier | Drop-ship fulfiller for FBA/WFS lines (C1, INV-7); required for FBA/WFS imports |
| deduct_on_shipped_event | Check | Switch ③ (C2): shipped event converts hold→per-shipment deduction; OFF by default, manual-first |

## 7. Custom DocType: Order Import Log

Append-only record of every import attempt (INV-11A evidence trail).

| Field | Type | Notes |
|---|---|---|
| channel | Link Channel | |
| channel_order_id | Data | |
| import_key | Data | `channel + channel_order_id` — the INV-11A idempotency key (OPEN — Phase 0 question 8 confirms). **Not unique here**: the log records every attempt, so duplicates and replays produce multiple rows per key |
| outcome | Select: Created / Duplicate / Exception | |
| sales_order | Link Sales Order | When outcome = Created |
| integration_exception | Link Integration Exception | When outcome = Exception |
| payload_hash | Data | §9 |

## 7A. Custom DocType: Shipment Status Event (Phase 14)

Append-only record of carrier/shipment status per channel order — **status sync
only**. Recording an event never creates, submits, or implies any stock
document; "shipped" recorded here is NOT "stock posted" (INV-8,
docs/STOCK-FLOW.md §4). Schema decision made in Phase 14 (a 7th custom
DocType, preferred over Sales Order custom fields to keep an auditable
event history).

| Field | Type | Notes |
|---|---|---|
| channel | Link Channel | |
| channel_order_id | Data | |
| sales_order | Link Sales Order | Resolved via (co_sales_channel, co_channel_order_id); empty when no matching order exists — recording is informational and never fails closed into order flow |
| carrier | Data | e.g. carrier code |
| carrier_status | Data | e.g. shipped / voided, as the source reports it |
| tracking_number | Data | Not PII; addresses are never stored (PRIVACY-REDACTION §4) |
| event_timestamp | Data | Source timestamp, verbatim |
| source | Data | e.g. ShipStation |
| event_hash | Data (unique) | Hash of (channel, order, tracking, status, timestamp) — duplicate events are idempotent |

Like Order Import Log, permissions omit write/delete: rows are created by the
shipping sync service and never edited.

## 8. Custom fields on standard DocTypes (fixtures, Phase 3)

On **Sales Order**:

| Field | Type | Notes |
|---|---|---|
| co_sales_channel | Link Channel | |
| co_channel_order_id | Data | Unique together with channel (backstops INV-11A at the document level) |
| co_fulfillment_type | Select: SELF / FBA / WFS | Exactly three options (INV-6). No blank produced by import; no UNKNOWN option exists on the field |

No custom fields on Item, Customer, Delivery Note, or Warehouse in V1. Channel
identity lives on Channel Listing, not on Item (the old system wrote channel IDs
onto Item — retired).

## 9. Payload / PII rules

Full raw marketplace payloads are **not stored by default**. The model uses:

- `payload_hash` — hash of the canonical payload, for dedup/audit (always safe).
- `raw_payload_redacted` — payload with PII fields removed/masked per the
  redaction policy.
- `external_payload_reference` — pointer to retrieve the original from the
  channel itself (order ID / API reference), instead of holding a copy.
- `replay_payload_minimal` — the minimum fields needed to replay the import.

Scope: this rule governs **stored copies of channel payloads**. It does not
forbid operational order data required for fulfillment (e.g. the ship-to
address on a SELF Sales Order), whose handling belongs to the customer policy
(`docs/ORDER-FLOW.md` §4, still open).

**DECIDED (Phase 4):** the redaction allowlist, the disallowed-PII list (no
name, address, phone, email, payment details, or raw blobs in stored copies),
and the 90-day post-terminal retention window are defined normatively in
`docs/PRIVACY-REDACTION.md`. That policy gates the Phase 5 implementation of
Integration Exception and Order Import Log.

## 10. Naming & conventions

- Custom DocTypes live in the `canadian_outlet` app, module per `modules.txt`
  (module layout finalized in Phase 2 scaffold).
- Select values are stored uppercase for fulfillment types (`SELF`, `FBA`,
  `WFS`); status values in title case as listed in §5.
- All schema ships as app fixtures/DocType JSON under version control — no
  hand-created Custom Fields or DocTypes in any site.
