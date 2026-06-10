# Canadian Outlet ERP — Privacy & Redaction Policy

Status: Phase 4 planning document. Normative once approved. **No implementation
exists yet** — this policy governs the Phase 5 Integration Exception / Order
Import Log implementation and every later phase that touches payloads.

## 1. Scope

This policy governs **stored copies of channel payload data** — anything
persisted in Integration Exception, Order Import Log, or any future record
derived from marketplace payloads. It does not forbid operational order data
required for fulfillment (e.g. the ship-to address on a SELF Sales Order);
that is governed by the customer policy (`docs/ORDER-FLOW.md` §4, still open).

## 2. The four payload fields

Full raw marketplace payloads are **never stored by default**. The only
payload-derived fields permitted are:

| Field | Content | PII allowed |
|---|---|---|
| `payload_hash` | Hash of the canonical payload, for dedup/audit | none (hash only) |
| `external_payload_reference` | Pointer to re-fetch the original from the channel (order ID / API path) | none |
| `raw_payload_redacted` | Payload reduced to the allowlist in §3 | none |
| `replay_payload_minimal` | The minimum allowlisted fields needed to replay the import | none |

A debugging escape hatch that stores an unredacted payload is **not provided**.
If a payload must be inspected, re-fetch it from the channel via
`external_payload_reference`.

## 3. Redaction is allowlist-based

Redaction keeps **only** the following; everything not listed is stripped,
including unknown/new fields the channel adds later (fail closed, INV-10):

- channel identifier and `channel_order_id`
- order timestamps and order status from the channel
- per line: external item identity (SKU/ASIN/item ID), quantity, unit price
- currency, order-level totals, tax totals
- fulfillment evidence keys/values (e.g. `fulfillment_channel: AFN`)

## 4. Disallowed by default in stored payload copies

Never stored in `raw_payload_redacted`, `replay_payload_minimal`, Order Import
Log, or exception `failure_reason` text:

- buyer full name
- any address (street, city, postal code — all of it)
- phone numbers
- email addresses
- payment details of any kind
- raw marketplace blobs / unparsed payload fragments

## 5. Retention

| Data | Retention |
|---|---|
| `raw_payload_redacted`, `replay_payload_minimal` | Purged **90 days** after the exception reaches a terminal status (`Resolved` or `Ignored`); open/in-flight exceptions keep them until terminal + 90 days |
| `payload_hash`, `external_payload_reference` | Retained indefinitely (no PII) |
| Order Import Log rows | Retained indefinitely (contain no payload copies, only `payload_hash`) |

ASSUMPTION (flagged): the 90-day window and the allowlist in §3 are the
conservative defaults proposed and approved with Phase 4; tightening or
loosening either is a one-line change here plus a fixture/test update.

## 6. Purge mechanics — constraint

Automated purging would require a **scheduled job, which is not approved**
(AGENTS.md scope gates). Until a purge job is explicitly scoped in a later
phase, retention is enforced operationally (manual purge procedure, documented
at go-live). The data model must still record enough to purge correctly
(terminal-status timestamp).

## 7. Enforcement

- Tests T-PII-1 and T-PII-2 (`docs/TEST-PLAN.md`) assert no unredacted payload
  and no disallowed PII in stored records.
- Code review rejects any new field that persists payload-derived data without
  an entry in §2.
- `docs/CONFIGURATION.md` §5 already forbids secrets in these records; this
  policy extends the same discipline to PII.
