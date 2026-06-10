# Canadian Outlet ERP — Test Plan

Status: Phase 1 planning document. Tests are written in Phase 4, **before** the
behavior they verify is implemented (Phases 5–6). A failing-then-passing test is
the definition of done for each behavior.

Each test maps to an invariant in `docs/ERP-INVARIANTS.md`. An invariant without
a test is a documentation bug; a behavior without an invariant is out of scope.

---

## 1. Test infrastructure

- Framework: Frappe's built-in test runner
  (`bench --site <test-site> run-tests --app canadian_outlet`), which provides a
  real site, database, and DocType layer. Pure-logic units (e.g. classifier rule
  matching) should be factored so they are also testable without a site.
- Fixtures: synthetic Channels, Channel Listings, Items, and payloads only.
  **No real marketplace payloads, no real customer data, no real credentials**
  (see `docs/CONFIGURATION.md` §5).
- CI: a containerized site running this suite is a Phase 2/3 deliverable; until
  it exists, the suite runs on the development bench (acknowledged risk — see
  Phase 0 risk list).

## 2. Test matrix

IDs are stable and referenced from code review.

### Item resolution (Phases 4–5)

| ID | Test | Invariant |
|---|---|---|
| T-RES-1 | Known (channel, external_identity) with Active Channel Listing resolves to the mapped Item | INV-2, INV-3 |
| T-RES-2 | Unknown external identity creates an Integration Exception with failure_stage = Resolution | INV-4 |
| T-RES-3 | Unknown external identity does **not** create an Item (Item count unchanged) | INV-1, INV-4 |
| T-RES-4 | Inactive Channel Listing does not resolve; fails closed to Integration Exception | INV-2, INV-10 |
| T-RES-5 | External identity matching an existing item_code but with no Channel Listing still fails closed (no convention-based resolution) | INV-2 |

### Fulfillment classification (Phases 4–5)

| ID | Test | Invariant |
|---|---|---|
| T-FUL-1 | Mapped evidence classifies correctly: Woo→SELF, Amazon AFN→FBA, Amazon MFN→SELF, Walmart WFS→WFS, Walmart seller-fulfilled→SELF | INV-5 |
| T-FUL-2 | Missing/unmapped evidence yields UNKNOWN; order is blocked and an Integration Exception (failure_stage = Classification) is created | INV-5, INV-6, INV-10 |
| T-FUL-3 | UNKNOWN never becomes SELF: no Sales Order with co_fulfillment_type = SELF exists after an unmapped-evidence import | INV-5, INV-6 |
| T-FUL-4 | No import path can produce a Sales Order with blank co_fulfillment_type | INV-6 |

### Idempotency (Phases 4–6)

| ID | Test | Invariant |
|---|---|---|
| T-IDEM-1 | Importing the same order twice creates exactly one Sales Order; second attempt logs outcome = Duplicate | INV-11A |
| T-IDEM-2 | Re-processing an order never duplicates Sales Order Items or doubles quantities | INV-11B |
| T-IDEM-3 | Repeated failure of the same order for the same cause yields exactly one open Integration Exception (dedup_key) | INV-11C |
| T-IDEM-4 | After a human fixes the cause (e.g. adds the missing Channel Listing) and sets the exception to Resolved, replay creates the Sales Order (log outcome = Created) and the exception remains Resolved; replaying again is a no-op duplicate | INV-11A, INV-11C |
| T-IDEM-5 | Setting an exception to Ignored requires ignored_reason; an Ignored exception is never replayed automatically | INV-10 |

### Atomicity (Phases 4–6)

| ID | Test | Invariant |
|---|---|---|
| T-ATOM-1 | Multi-line order with one unresolvable line creates **no** Sales Order (not a partial one) and one Integration Exception | INV-10 |
| T-ATOM-2 | After a failed import, no orphan Customers or other partial records remain | INV-10 |

### Stock safety (Phase 4, against the data model + standard ERPNext behavior)

| ID | Test | Invariant |
|---|---|---|
| T-STK-1 | A draft Delivery Note causes no stock ledger entry; any "deduction exists?" logic counts only docstatus = 1 | INV-8 |
| T-STK-2 | Submitting the Delivery Note for a SELF order deducts stock at the default warehouse exactly once | INV-7, INV-8 |
| T-STK-3 | Importing FBA and WFS orders creates no stock-impacting document and no stock ledger entry, ever | INV-7 |
| T-STK-4 | The import pipeline itself never creates or submits any stock-impacting document (V1) | INV-8, V1 scope |

### Pipeline exclusivity (Phases 4–6)

| ID | Test | Invariant |
|---|---|---|
| T-PIPE-1 | The only public entry point for order creation is the Order Import Service; adapters expose no Frappe-writing functions | INV-9 |
| T-PIPE-2 | Disabled Channel or imports_enabled = 0 (kill switch) blocks imports, fail closed | INV-9, INV-10 |

### Payload / PII safety (with Integration Exception implementation)

| ID | Test | Invariant |
|---|---|---|
| T-PII-1 | An Integration Exception created from an import failure stores no full unredacted payload: raw_payload_redacted and replay_payload_minimal contain only fields on the PRIVACY-REDACTION.md §3 allowlist (unknown payload fields are stripped) | PRIVACY-REDACTION.md, INV-10 |
| T-PII-2 | Disallowed PII (name, any address part, phone, email, payment data) planted in a synthetic payload appears nowhere in the stored Integration Exception or Order Import Log record, including failure_reason text | PRIVACY-REDACTION.md |

### Configuration (Phase 5+)

| ID | Test | Invariant |
|---|---|---|
| T-CFG-1 | Missing required config key raises a clear error naming the key; no silent default | CONFIGURATION.md §2 |
| T-CFG-2 | Secrets never appear in logs, exceptions, or Integration Exception records (assert on captured output for a synthetic credential) | CONFIGURATION.md §5 |

## 3. Coverage check (invariant → tests)

- INV-1: T-RES-3 · INV-2: T-RES-1/4/5 · INV-3: T-RES-1 · INV-4: T-RES-2/3
- INV-5: T-FUL-1/2/3 · INV-6: T-FUL-2/3/4 · INV-7: T-STK-2/3
- INV-8: T-STK-1/2/4 · INV-9: T-PIPE-1/2 · INV-10: T-ATOM-1/2, T-RES-4, T-FUL-2, T-PIPE-2
- INV-11A: T-IDEM-1/4 · INV-11B: T-IDEM-2 · INV-11C: T-IDEM-3/4
- PRIVACY-REDACTION.md: T-PII-1/2 (plus T-IDEM-5 for the Ignored-reason rule)

Every invariant has at least one test. Maintaining this section is part of the
definition of done for any test or invariant change.
