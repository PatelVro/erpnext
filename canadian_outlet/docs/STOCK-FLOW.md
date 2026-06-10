# Canadian Outlet ERP — Stock Flow

Status: Phase 1 planning document. Normative once approved.
Governing invariants: INV-7, INV-8.

> **Precedence note (2026-06-10):** the owner's workflow decisions in
> `docs/FLOW-DECISIONS.md` are the top business authority. Sections of this
> document that conflict with it are superseded; each implementation phase of
> `docs/BUILD-CHANGE-PLAN.md` rewrites the affected sections here in the same
> change.

The previous system's most dangerous defect lived here: a draft Delivery Note
could be mistaken for a posted stock deduction, and an automated shipment event
could then skip the real deduction. This document defines a stock model where
that confusion cannot exist.

---

## 1. Warehouse model

- One physical warehouse: **1431 Yonge**. All local sellable stock lives there.
  - PROVISIONAL (Phase 0 question 4): canonical for V1 pending explicit
    confirmation. The design does not otherwise depend on warehouse count.
- ERPNext stock represents **Canadian Outlet's own physical inventory only**.
- FBA and WFS are **fulfillment classifications, not warehouses**. No ERPNext
  warehouse is created to mirror Amazon or Walmart facilities, and no local
  stock ledger entry ever represents marketplace-held inventory.

## 2. The one and only deduction rule

> Local stock decreases **only** when a human submits a stock-impacting ERPNext
> document (V1: a Delivery Note) for a **SELF** order.

Spelled out:

- **SELF orders (INV-7):** eligible for local stock deduction — and only via the
  flow in §3.
- **FBA / WFS orders (INV-7):** never deduct local stock. No Delivery Note, no
  Stock Entry, no automation of any kind against local warehouses. How FBA/WFS
  Sales Orders are administratively closed in ERPNext without stock movement is
  specified in Phase 3 (data model/fixtures) — whatever the mechanism, it must
  not touch the stock ledger.
- **Draft ≠ deduction (INV-8):** a draft Delivery Note is a staging artifact for
  human review. It must never be counted as a deduction by any code, report,
  reconciliation, or "already deducted?" check. Any existence check for a
  deduction must test for **submitted** documents (`docstatus = 1`) only.

## 3. V1 SELF order flow

```
Sales Order (created AND submitted by the Order Import Service — C1/INV-12:
             submission is the availability hold, not a stock movement)
        │
        ▼  human creates Delivery Note from Sales Order (standard ERPNext flow)
Delivery Note (draft)            ← no stock impact (INV-8)
        │
        ▼  human verifies physical picking/shipment
Delivery Note submitted (human)  ← stock deducts at 1431 Yonge, exactly once
```

- Both submissions are human actions in V1. The app adds **no automation** here.
- Exactly-once is guaranteed by ERPNext's own document model (a Delivery Note
  submits once) plus the per-order review discipline; the app must not add a
  second, parallel deduction path that would re-introduce double-counting risk.

## 4. Explicitly not in V1

- **No ShipStation stock automation.** ShipStation arrives (Phase 7) as shipment
  *status sync only* — it records tracking/status, it never creates or submits
  stock documents.
- **No auto-created draft Delivery Notes on import** (OPEN — Phase 0 question 6;
  see `docs/ORDER-FLOW.md` §6). If later approved, the scoped change is limited
  to *creating a draft*; submission remains human.
- **No Stock Entry / Material Issue paths** for sales fulfillment. The old
  system's parallel "Material Issue on shipped event" model is retired entirely.
- **No scheduled jobs** touching stock.

## 5. Hold→deduction at shipped (C2 — supersedes the Phase 18 draft-submit design)

Per FLOW-DECISIONS D5/D7: a recorded "shipped" event (never label creation —
voids stay inert, 1B) converts the order's hold into a real deduction by
**creating and submitting a partial Delivery Note for exactly that shipment's
quantities**, box by box for partial orders.

Constraints (enforced in `co_shipping.shipstation.process_shipment_event` and
pinned by `tests/test_c2_deduction.py`):

- **Switch ③:** `Canadian Outlet Settings.deduct_on_shipped_event`, OFF by
  default (D10 manual-first) — while off, the operator converts each recorded
  event with one click; the switch automates the identical call.
- SELF orders only (INV-7); FBA/WFS events deduct nothing; voids are inert.
- Shipment items resolve through Channel Listing (INV-2); unknown SKUs or
  missing item data fail closed — no deduction, event kept for the queue.
- Quantities cap at the order's undelivered remainder; over-shipments are
  logged, never deducted past the order.
- Idempotent: duplicate events dedup on event_hash; a converted event carries
  its Delivery Note link and is a no-op thereafter.
- A failed conversion is logged and the event stays unconverted for retry —
  the human queue remains the backstop.

## 6. Operational ownership

V1 depends on a human owning the review queue (un-submitted Sales Orders and
draft Delivery Notes for SELF orders). If nobody owns it, orders ship physically
while stock never deducts — the precise failure this rebuild exists to prevent.
Assigning that owner is an operational prerequisite for go-live, tracked as a
Phase 6 launch checklist item.
