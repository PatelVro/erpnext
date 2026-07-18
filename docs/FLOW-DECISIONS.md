# Canadian Outlet ERP — Flow Decisions (Discovery Board v8, FINAL)

Status: **the top business authority for this system.** Decided by the owner in
the workflow discovery session of 2026-06-10. Where any other document in
docs/ contradicts this one, THIS document wins until the owner changes it.
Each implementation phase that lands a decision below must rewrite the
affected sections of the other docs in the same change.

The flow in one paragraph: Orders from every channel flow into ERPNext
automatically, as individual records, while the team keeps working in the
marketplace tools and ShipStation — ERPNext is the quiet system of truth.
Products exist only when a human creates them; every channel SKU is
pre-mapped in bulk before go-live, and the rare unknown SKU waits as a ticket
with system-suggested matches a human confirms — confirming instantly
releases every order stuck on it. Clean marketplace labels classify orders;
unclear ones become real-but-quarantined orders, counted in sales but unable
to touch stock. The 1431 Yonge shelf is sacred: nothing any marketplace does
moves it. Stock sent to FBA transfers to a real "At Amazon FBA" location, and
FBA sales deduct THAT location. For self-shipped orders: units go on hold the
second the order imports, and the hold becomes a real deduction — per
shipment — when the shipping system reports shipped, with the invoice created
in the same heartbeat and taxes recorded per order. Returns restock only
after human inspection. Admin is notified instantly on stops, daily on
warnings, louder after three days. Four kill switches; the big red one
freezes stock-and-money while intake keeps flowing into quarantine.

---

## D1 — Order intake: back office, everything, per-order

- ERPNext receives EVERY order from EVERY channel automatically, as an
  individual order record (including each FBA/WFS order, for lookup during
  returns/disputes).
- Staff keep working in marketplace dashboards and the shipping tool; ERPNext
  is not their daily cockpit. Its job is to be correct.
- Off-channel sales (walk-in, phone, wholesale): PARKED — exists, not yet
  scoped.

## D2 — Product matching: human-curated, suggest-and-confirm

- Items are created only by humans (purchase orders, invoices, manual, Excel
  import), with full specifications, supplier history, and cost prices. The
  system never creates an Item. (Unchanged: INV-1.)
- Before go-live (and as standing practice), ALL channel SKUs are pre-mapped
  to Items in bulk — Excel import of mappings is a required tool. SKUs are
  messy; mapping is the human's judgment.
- When an unknown SKU arrives, the order waits as a review TICKET. The system
  SUGGESTS likely Item matches; a human confirms. Never auto-confirmed.
- Bundles: not sold (not modeled).

## D3 — Fulfillment classification: trust clean labels; quarantine the unclear

- Clean marketplace markers classify instantly (Amazon AFN→FBA, MFN→SELF;
  Walmart WFS→WFS, seller→SELF; Woo→SELF). Marketplace data is mostly clean;
  unknown markers should be rare.
- An order with unclear fulfillment becomes a REAL Sales Order immediately —
  visible, counted in sales — but QUARANTINED: it cannot hold stock, deduct
  stock, ship, or invoice until a human classifies it. (Supersedes the old
  rule that unclear orders never become Sales Orders.)
- Unknown-SKU orders cannot quarantine (no Item for the line): those remain
  tickets per D2.
- The same person handles both queues (Admin for now).

## D4 — Inventory ownership: sacred shelf + real At-FBA location

- The 1431 Yonge shelf count is sacred: NOTHING a marketplace does ever
  changes it.
- Amazon FBA stock is REAL ledger stock in an "At Amazon FBA" location:
  outbound boxes to Amazon are recorded transfers (shelf down, At-FBA up),
  tagged with the Amazon Inbound Shipment ID; sent-vs-received gaps visible.
  FBA orders deduct the At-FBA location per order; a periodic human true-up
  reconciles against Amazon's reported counts. Value of FBA stock sits on the
  books (accountant requirement). FBA shipments are PLANNED in Seller
  Central; ERPNext records them.
- Walmart WFS stock: informational/read-only for now (no ledger location) —
  OPEN: promote to a WFS location if/when volume justifies it.
- The analytics goal everything serves — per-product 360: how many, what
  cost, purchase history, sales trend, listed-where, selling-where, refill
  recommendation and price.

## D5 — Stock deduction timing: hold at import, deduct at shipped

- The moment a SELF order imports, its units go ON HOLD: shelf count
  unchanged, availability reduced (protects qty-1 open-box units across
  channels; quantities range 1–2000).
- The hold converts to a REAL deduction automatically when the shipping
  system reports the shipment SHIPPED/COMPLETED — per shipment (partial
  orders deduct box-by-box). Label creation alone does NOT deduct (voided
  labels never touch the books).
- Quarantined orders hold NO stock until classified SELF.
- ShipStation is today's shipping system, treated as replaceable.

## D6 — Human review points (STOP / WARN / SILENT)

| Situation | Behavior |
|---|---|
| Unknown SKU | STOP — ticket with suggestions (D2) |
| Unclear fulfillment | quarantined order (D3) |
| Hold would exceed available stock | WARN (sale already happened; flag fast) |
| Marketplace price differs from expected | SILENT — record their price (it is the sale's truth) |
| Duplicate delivery | SILENT — recognized and skipped |
| Cancellation before ship | SILENT — auto-release hold; visible in order history |
| Cancellation after ship | STOP — return/dispute case |
| Address/shipping problems | Not ERPNext's job (shipping tool / marketplace) |
| Import/sync failure | WARN on a system-health list |

- Triage owner: Admin (roles later; operations role exists).
- Notifications: INSTANT email per STOP; DAILY digest of WARNs; LOUDER email
  if a ticket sits untouched 3 days.

## D7 — Shipping flow

- Deduction trigger is the SHIPPED/COMPLETED status, not label creation (1B).
- Partial shipments deduct per shipment.
- ERPNext orders carry maximum shipment detail (carrier, tracking, dates) —
  the one-stop dispute lookup.
- Returns to the building NEVER auto-restock: receiving is recorded, but
  stock re-enters the shelf only after human inspection (refurb gear may
  return unsellable).

## D8 — Exceptions and replay

- Plain-English statuses: New → Being handled → Fixed / Ignored (reason
  required) ; Re-import failed returns to the top.
- FIX-AND-FLOW: confirming a mapping (or classifying a quarantined order)
  immediately re-imports/releases every order waiting on that fix. One
  action. (Supersedes deliberate-replay-click.)

## D9 — Payments and invoices

- Invoice is created AUTOMATICALLY at shipment — same heartbeat as the
  deduction. (Manual-first at launch; see D10.)
- Taxes recorded PER ORDER on the invoice; marketplace-remitted vs
  self-remitted must remain distinguishable.
- Marketplace fees: NOT per-order for now; lump-sum later with settlements.
- Website payments: Stripe, Klarna, Affirm, manual E-Transfers — recorded as
  money lands; reconciliation automation is prioritized early (D10).

## D10 — Automation ledger and kill switches

- AUTOMATIC in V1: intake (scheduled + webhook), holds, classification,
  hold→deduction at shipped (per shipment), FBA-location deduction, invoice
  at shipment, tracking sync, duplicate handling, cancellation hold-release,
  fix-and-flow, notifications/escalation.
- LAUNCH EXCEPTION (manual-first, promoted after a few trusted weeks):
  auto-invoicing and the hold→deduction conversion start as one-click human
  actions behind their switches.
- MANUAL in V1: Item creation, mapping confirmation, quarantine
  classification, inspect-first restocking, FBA inbound recording, payment
  recording, FBA true-up.
- AUTOMATE SOONER than "later": payment/settlement reconciliation.
- KILL SWITCHES: ① all intake ② per-channel intake ③ hold→deduction
  automation ④ auto-invoice automation. BIG RED BUTTON = freeze everything
  that touches stock and money while intake continues INTO QUARANTINE
  (orders keep arriving safely; nothing moves a number until released).
