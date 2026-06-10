# Build-Change Plan — aligning the build to FLOW-DECISIONS.md

Status: approved sequencing document. Each change is its own tests-first
phase: failing tests written from the decision, implementation until green on
the bench, affected docs rewritten in the same change, separate commit.
Nothing below is implemented until its phase begins. Ordered by dependency
and risk — stock-safety primitives first, conveniences later.

| # | Change | Decision | What it replaces in the current build |
|---|---|---|---|
| C1 ✅ LANDED | **Stock holds at import** — SELF order import places a reservation (shelf unchanged, availability down); cancellation-before-ship auto-releases; quarantined orders never hold | D5, D6 | Nothing reserves today |
| C2 ✅ LANDED | **Per-shipment deduction at shipped status** — shipped/completed event converts the hold to a real deduction box-by-box; label-creation and voids inert; behind switch ③, manual-first at launch | D5, D7, D10 | Kill-switched whole-order draft-DN auto-submit |
| C3 | **Quarantine intake** — unclear fulfillment creates a real, flagged Sales Order barred from stock/shipping/invoicing; classify action releases it; INV-6 rewritten accordingly | D3 | Unclear → exception ticket, no order |
| C4 | **Suggest-and-confirm + bulk mapping import + fix-and-flow** — suggestion list on unknown-SKU tickets; Excel/CSV mapping importer with row-level validation report; confirming a mapping auto-replays all waiting orders | D2, D8 | Strict block, manual replay button |
| C5 | **Auto-invoice at shipment + per-order taxes** — invoice created on the deduction heartbeat behind new switch ④ (manual-first); adapters carry per-order tax detail; marketplace-remitted vs self-remitted distinguishable | D9, D10 | Manual invoice button; taxes not carried |
| C6 | **At-FBA location** — "At Amazon FBA" warehouse; transfer recording tagged with Inbound Shipment ID; sent-vs-received report; FBA orders deduct At-FBA; true-up tool; WFS stays informational (OPEN) | D4 | FBA never modeled; FBA orders touch nothing |
| C7 | **Notifications** — instant email per STOP, daily WARN digest, 3-day louder escalation; system-health WARN list for sync failures | D6 | None |
| C8 | **Kill-switch completion** — switch ④ (invoice) and the BIG RED safe-mode: stock+money frozen, intake continues into quarantine | D10 | Switches ①–③ exist; no safe-mode |
| C9 | **Payment/settlement reconciliation (early)** — match Stripe/Klarna/Affirm/E-Transfer payouts and marketplace settlements to invoices; human confirms postings initially | D9, D10 | Read-only Amazon matching only |
| C10 | **Product-360 view** — per-Item: stock, cost, purchase history, sales trend, listed/selling per channel, refill hint | D4 | Partial (reorder + listing-health reports) |

## Invariant updates carried by these phases

- INV-6 (C3): "unclear fulfillment blocks import" becomes "unclear
  fulfillment imports quarantined; quarantine is enforced, classification is
  human." UNKNOWN still never silently becomes SELF.
- INV-7 (C6): "local stock" is defined as the 1431 Yonge shelf. FBA orders
  deduct the At-FBA location and only it; WFS orders deduct nothing (for
  now). The shelf remains untouchable by any marketplace event.
- INV-8 (C2): deduction remains only-on-submitted-stock-document; the
  submitter may be the shipped-event automation behind switch ③.
- New invariant (C1): availability honesty — a SELF order's units are
  unavailable from the moment of import, without moving the physical count.
- New invariant (C8): safe-mode — when the big red switch is on, no automatic
  process may create or submit any stock- or money-impacting document, while
  intake continues in quarantine.

## Standing constraints (unchanged)

Items never auto-created (INV-1) · Channel Listing is the only mapping
(INV-2/3/4) · no guessing, fail closed (INV-10) · idempotent everywhere,
DB-enforced for orders (INV-11) · payload privacy & retention
(PRIVACY-REDACTION) · ERPNext core untouched.

## Parked (explicitly not in this plan)

Off-channel sales intake · per-order marketplace fees · WFS ledger location ·
multi-user roles rollout · shipping-tool migration abstraction beyond the
existing adapter boundary.
