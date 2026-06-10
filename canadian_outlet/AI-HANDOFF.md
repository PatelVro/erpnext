# AI-HANDOFF — Canadian Outlet ERP (`canadian_outlet`)

Audience: an AI agent (or new developer) picking up this repository with zero
prior context. Read this file first, then `AGENTS.md`, then
`docs/FLOW-DECISIONS.md`. Everything below was true at the time of the last
commit that touched this file; when in doubt, the docs win over this summary
and FLOW-DECISIONS wins over everything.

---

## 1. What this is

A custom Frappe app carrying ALL Canadian Outlet business logic on top of an
untouched upstream ERPNext (`version-15`). Canadian Outlet is a refurb/open-box
electronics retailer (single physical warehouse, "1431 Yonge") selling through
WooCommerce, Amazon (incl. FBA), and Walmart (incl. WFS), shipping SELF orders
via ShipStation. ERPNext is the quiet back office (owner's explicit choice):
staff keep working in marketplace dashboards; this system's job is to be
CORRECT about stock and money, automatically, with humans pulled in only at
deliberate stop points.

This project is a ground-up rebuild. The previous AI-built system was
destroyed by: auto-created Items rotting the catalog, unknown fulfillment
defaulting to SELF, draft documents counted as stock movements, parallel
import paths, and config-name drift. Every guardrail here exists because one
of those actually happened. Do not re-introduce them.

### Repository geography
- If you are reading this inside `PatelVro/erpnext` (an ERPNext fork): you are
  on a TRANSPORT CARRIER branch. The app lives in `canadian_outlet/`; ERPNext
  core files around it are upstream and must never be modified. Extraction to
  the standalone repo:
  `git subtree split --prefix=canadian_outlet -b canadian-outlet-main`
  then push that branch to the standalone repo's `main`.
- If this file is at the repository root: you are in the standalone app repo.

## 2. Authority hierarchy (binding)

1. `docs/FLOW-DECISIONS.md` — the owner's ten workflow decisions (D1–D10),
   captured verbatim from a discovery interview. Top business authority.
2. `docs/BUILD-CHANGE-PLAN.md` — the C1–C10 implementation plan of those
   decisions. All ten are LANDED.
3. `docs/ERP-INVARIANTS.md` (INV-1…INV-13) and the other `docs/*` — normative.
4. Code. When code and docs disagree, the docs win until a human changes them.
5. `AGENTS.md` — working discipline for agents (list files before writing,
   `git diff --stat` after, tests-first, one phase per commit, docs updated in
   the same change, no commits without approval unless the operator has
   explicitly waived it).

## 3. The invariants in one breath

INV-1 Item master is human-curated; imports NEVER create Items.
INV-2/3 Channel Listing is the ONLY external→Item mapping; exact match.
INV-4 unknown listing → review ticket (Integration Exception), never an Item.
INV-5 fulfillment only from explicit Channel Fulfillment Map rows; missing or
contradictory evidence = UNKNOWN. INV-6 UNKNOWN is never persisted and never
becomes SELF; unclear orders import QUARANTINED (draft + `co_quarantined`),
blank `co_fulfillment_type` is legal only there. INV-7 only SELF touches the
shelf; FBA/WFS lines are drop-ship rows; FBA deducts the At-FBA location only.
INV-8 stock moves only on a SUBMITTED stock document; drafts are never
deductions. INV-9 ONE shared Order Import Service; no side-channel order
paths. INV-10 fail closed, atomic imports, no guessing. INV-11 idempotent at
order (DB unique index), line, and exception levels. INV-12 availability
honesty: imported orders are submitted-on-arrival; SELF units go on hold
instantly without moving the physical count. INV-13 safe mode: the big red
switch freezes every stock/money-impacting action (automatic AND one-click)
while intake continues into quarantine.

## 4. Owner decisions condensed (D1–D10)

Back office, every order from every channel as a per-order record (D1).
Human-curated catalog, bulk Excel pre-mapping, suggest-and-confirm for unknown
SKUs (D2). Trust clean marketplace labels; unclear → quarantined real order;
same person triages everything — currently Admin (D3). Sacred shelf + REAL
At-FBA warehouse (B1): transfers in tagged with Amazon Inbound Shipment IDs,
per-order FBA deduction, periodic human true-up; WFS informational; FBA
shipments are PLANNED in Seller Central, only recorded here (D4). Hold at
import → deduct at shipped/completed, per shipment, label voids inert (D5).
STOP/WARN/SILENT table per D6; instant STOP email, daily digest, 3-day louder
escalation. ShipStation = today's shipping truth, replaceable; full tracking
detail on orders; returns restock only after human inspection (D7).
Plain-English exception statuses; fix-and-flow: confirming a mapping instantly
re-imports everything stuck on it (D8). Auto-invoice at shipment; per-order
taxes into a configured account; fees lump-later; Stripe/Klarna/Affirm/
E-Transfer recorded as money lands (D9). Manual-first launch: deduction (③)
and invoicing (④) switches OFF until trusted; reconciliation prioritized
early; big red = freeze stock+money, intake continues quarantined (D10).

## 5. Behavior map (current, all tests green)

### Import pipeline (`co_orders/import_service.py::import_order`)
kill-switch+channel check (raises ImportsDisabledError, creates nothing)
→ envelope validation (empty/None order id, qty<=0, missing/negative rate →
Exception) → per-line resolution via Channel Listing (unknown → Exception
ticket w/ suggestions) → classification (UNKNOWN → quarantined draft; safe
mode forces quarantine for ALL) → generic per-channel Customer → tax row
(Actual, configured account; tax with no account → Exception) → Sales Order
created AND SUBMITTED (the hold). SELF lines carry Settings.default_warehouse;
FBA/WFS lines are `delivered_by_supplier` rows with
Settings.marketplace_fulfillment_supplier (required, else Exception). FBA
submit triggers Material Issue from Settings.fba_warehouse (no-op if unset,
log-never-block). Duplicates: pre-check + DB unique index
`co_channel_order_unique` on (co_sales_channel, co_channel_order_id); a race
loses the insert and converts to Duplicate. Channel cancellation flag:
before-ship → cancel SO (hold released, silent); after-ship (submitted DN
exists) → Cancellation-stage Exception; cancelled-on-arrival → import then
cancel (record exists, no hold).

### Shipping (`co_shipping/shipstation.py`)
`translate_shipment` (sku+qty only; ship-to dropped) → `record_shipment_event`
(idempotent on event_hash; auto-converts when switch ③ on) →
`process_shipment_event`: shipped-only, SELF-only, resolves shipment SKUs via
Channel Listing (unknown → log + skip), caps at undelivered remainder,
creates+SUBMITS a partial Delivery Note via
`co_inventory/delivery_note_service.py::create_delivery_for_shipment`, links
it on the event (idempotency), then `_maybe_auto_invoice` (switch ④ →
create+submit Sales Invoice; failure logs, deduction stands).

### Catalog (`co_catalog/`)
`resolution.py` exact Active-listing match; `suggestions.py::suggest_matches`
token+ratio ranking over enabled Items (read-only); `bulk_mapping.py::
import_listings_csv` row-validated CSV (skip identical, reject conflicts);
Channel Listing controller refuses disabled Items and fires fix-and-flow
(`after_insert` → resolve+replay every Resolution exception on that identity).

### Quarantine (`co_orders/quarantine.py::classify_quarantined_order`)
Human verdict SELF/FBA/WFS on a quarantined draft → line config per type →
submit (hold or drop-ship). Refuses non-quarantined, garbage types, safe mode.

### Money (`co_billing/`)
`invoice_service.py::create_invoice_for_delivery` (submitted DN only, SELF
only, idempotent per DN, draft out). `payment_service.py::
record_payment_for_invoice` (submitted invoice w/ outstanding → DRAFT Payment
Entry, one open draft per invoice). `return_service.py` returns + credit notes
(drafts; restock on human submit only). `settlement.py`: Amazon settlement V2
flat-file parse → per-order match incl. invoice+outstanding (read-only) and
`confirm_settlement_payments` → draft PEs per matched invoice.

### FBA (`co_inventory/fba.py`)
`record_fba_inbound(id, items)` Material Transfer shelf→At-FBA, idempotent per
inbound id (remarks match). `issue_fba_sale` per FBA order. `true_up_fba`
Stock Reconciliation to Amazon's counts.

### Core (`co_core/`)
`settings.py` sole reader of frappe.conf (`get_required_conf` raises naming
the key). `redaction.py::scrub_secrets` masks any co_* conf value in stored
text. `scheduler.py` daily_channel_sync (2-day window, per-channel failure
isolation, no-op when imports disabled) + weekly_retention_purge.
`notifications.py` notify_stop / daily_review_digest (+3-day escalation).
`safe_mode.py` is_safe_mode/assert_not_safe_mode. `retention.py` purge of
payload copies 90 days post-terminal (keeps hash+reference).

### Scheduler set (T-PIPE-1 pins EXACTLY this; changing it = change the test
and ERP-INVARIANTS in the same commit)
daily: co_core.scheduler.daily_channel_sync,
co_core.notifications.daily_review_digest · weekly:
co_core.scheduler.weekly_retention_purge. hooks has NO doc_events and NO
override_doctype_class — automation that needs document events goes in
controller classes of OUR DocTypes only.

### Schema
Custom DocTypes (module "Canadian Outlet"): Channel, Channel Fulfillment Map,
Channel Listing, Integration Exception (statuses Open/In Review/Resolved/
Ignored/Failed Replay; NEVER "Rejected"; Ignored requires reason; dedup_key
unique; payload fields per PRIVACY-REDACTION), Canadian Outlet Settings
(single), Order Import Log (append-only, import_key NOT unique by design),
Shipment Status Event (event_hash unique, shipment_items JSON, delivery_note
link). Sales Order custom fields (fixtures, name-filtered in hooks):
co_sales_channel, co_channel_order_id, co_fulfillment_type (SELF/FBA/WFS,
blank legal only when quarantined), co_quarantined. Reports: Channel Sales
Summary, Integration Exception Aging, Channel Listing Health, Reorder Status,
Product 360. Workspace "Canadian Outlet" (Open-exception badge). Desk JS:
Replay button (Integration Exception), Draft DN button (Sales Order) — plain
JS, no build step, calls whitelisted methods only. Role "Canadian Outlet
Operations" (triage write; config/audit read-only).

### Canadian Outlet Settings fields (the control panel)
imports_enabled (switch ①, default OFF) · per-Channel `enabled` (②) ·
deduct_on_shipped_event (③, OFF) · auto_invoice_on_shipment (④, OFF) ·
safe_mode (BIG RED, OFF; INV-13) · default_warehouse · fba_warehouse ·
marketplace_fulfillment_supplier · marketplace_tax_account ·
notification_email.

### Config keys (site_config.json ONLY, read via co_core.settings; registry in
docs/CONFIGURATION.md): co_environment; co_woocommerce_{base_url,
consumer_key, consumer_secret, api_path?, webhook_secret};
co_shipstation_{api_key, api_secret, base_url?}; co_amazon_{lwa_client_id,
lwa_client_secret, lwa_refresh_token, marketplace_ids, region?};
co_walmart_{client_id, client_secret, base_url?}.

### Whitelisted API surface (operator/AI entrypoints)
adapters.woocommerce: import_woocommerce_orders, woocommerce_webhook (guest;
HMAC), setup_woocommerce_channel · adapters.amazon: import_amazon_orders,
setup_amazon_channel · adapters.walmart: import_walmart_orders,
setup_walmart_channel · co_orders.replay.replay_exception ·
co_orders.quarantine.classify_quarantined_order ·
co_shipping.shipstation.{import_shipstation_shipments, process_shipment_event}
· co_inventory.delivery_note_service.create_draft_delivery_note ·
co_inventory.fba.{record_fba_inbound, true_up_fba} ·
co_billing.invoice_service.create_invoice_for_delivery ·
co_billing.payment_service.record_payment_for_invoice ·
co_billing.return_service.* · co_billing.settlement.
{reconcile_amazon_settlement, confirm_settlement_payments} ·
co_catalog.suggestions.suggest_matches ·
co_catalog.bulk_mapping.import_listings_csv ·
co_core.retention.purge_expired_payload_copies.

## 6. Install / run / test

Fresh bench (Python 3.10+/3.11, Node 18/20+, MariaDB 10.6+, Redis):
```
bench init co-bench --frappe-branch version-15
cd co-bench && bench get-app erpnext --branch version-15
bench get-app <this-repo>          # standalone repo, or local path
bench new-site co.localhost --mariadb-root-password <pw> --admin-password <pw>
bench --site co.localhost install-app erpnext
bench --site co.localhost install-app canadian_outlet
```
Tests (the suite is the spec — ~146 tests, all green at handoff):
```
bench --site co.localhost set-config allow_tests true
bench --site co.localhost execute erpnext.setup.utils.before_tests   # REQUIRED once
bench --site co.localhost run-tests --app canadian_outlet
```
CI: `.github/workflows/ci.yml` reproduces exactly this on ubuntu-latest.
Go-live: docs/OPERATIONS.md (setup §1, checklist §8). Launch posture: ALL
switches OFF; flip ① last; promote ③ then ④ only after trusted weeks.

## 7. Hard-won internals (the traps — read before touching anything)

1. **Patches do NOT run on fresh installs** (Frappe marks them completed).
   Anything that must exist on a new site goes in the `after_sync` hook
   (`canadian_outlet/install.py`) — that's why the Operations role and the
   `co_channel_order_unique` index live there AND in patches (patches cover
   already-installed sites on migrate).
2. **ERPNext auto-fills item-default warehouses on EVERY validate** —
   clearing a Sales Order line's warehouse does not stick, and a stock item
   row without a warehouse fails submit. The only clean "no shelf contact" is
   `delivered_by_supplier=1` + a Supplier (drop-ship): core then excludes the
   row from Bin.reserved_qty AND from Delivery Note mapping. This is how
   FBA/WFS rows work; the bench caught the naive approach reserving shelf
   stock for FBA orders.
3. **Submitted Sales Order == the hold.** Bin.reserved_qty derives from
   submitted SO items with a warehouse; cancel releases it. No Stock
   Reservation Entry machinery is used.
4. **Composite uniqueness can't be declared on Custom Fields** — the
   (channel, order) idempotency is a real DB unique index added via
   `frappe.db.add_unique`; MariaDB unique indexes allow multiple NULLs, so
   manual non-channel orders are unaffected. The import path converts the
   index violation into a Duplicate outcome (race-safe; test simulates the
   TOCTOU window by patching `_find_existing_sales_order`).
5. **T-PIPE-1 pins hooks**: doc_events empty, override_doctype_class empty,
   scheduler_events EXACTLY the approved set. Fix-and-flow therefore lives in
   the ChannelListing controller (`after_insert`), not hooks.
6. **Deduct on shipped STATUS, never label creation** (owner's 1B): voided
   shipment records are recorded as events but inert; conversion is idempotent
   via the event's delivery_note link + event_hash dedup + remainder capping.
7. **Test-bench currency trap**: ERPNext's `before_tests` bootstraps company
   "Wind Power LLC" (USD) as default while `_Test Company` is INR. Synthetic
   orders must use the DEFAULT company's currency (`utils.default_currency()`)
   or every insert dies on exchange rates; the import service picks a selling
   price list matching the order currency when one exists.
8. **Warehouse picking in tests must be deterministic**: arbitrary
   `get_value("Warehouse", ...)` can return the company's Transit warehouse or
   the At-FBA warehouse → use `utils.shelf_warehouse()`.
9. **Frappe test classes do NOT fully isolate each other** — singles values
   and records leak across classes in one run. Always set the switches you
   depend on in setUp (see deduct/safe_mode/auto_invoice setUps), and use
   unique order ids per test.
10. **Email in tests**: assert via `unittest.mock.patch` on
    `canadian_outlet.co_core.notifications.frappe.sendmail` — the site has no
    outgoing account.
11. **Webhook**: guest endpoint is safe only because of constant-time HMAC
    verification + channel-type check; ONE Woo store per site is the
    documented assumption (per-channel secrets needed if a second store).
12. **Suite-as-contract**: in-test imports define the API; `tests/utils.py`
    header documents the canonical order shape. New behavior = new failing
    test FIRST, then code, then docs in the same commit.
13. **Adapters carry a `cancelled` flag** from explicit channel status lists —
    never inferred. Walmart fetch returns (orders, nextCursor); Amazon
    (orders, NextToken) and items follow their own token; Woo pages until an
    empty page. Truncating pagination loses orders silently — keep the loops.
14. **PII**: stored payload copies are allowlist-only (PRIVACY-REDACTION §3);
    `failure_reason` passes through scrub_secrets; shipment items keep sku+qty
    only; tests plant synthetic PII and assert zero leakage. Keep it that way.

## 8. Parked / open (do not build without owner input)

Off-channel sales intake (walk-in/phone/wholesale) · per-order marketplace
fees (lump-sum later, with settlements) · WFS ledger location ·
Stripe/Klarna/Affirm settlement-file ingestion (needs real export files) ·
FBA sent-vs-received report (needs Amazon receipt data) · multi-user role
rollout (Operations role exists, Admin triages today) · customer policy is
generic-per-channel (owner default; per-buyer would drag PII into Customer
master and reopen PRIVACY-REDACTION).

## 9. Working discipline for the next AI

Phase rhythm: restate goal → list exact files → failing tests from the
decision → implement → bench green → docs updated in the same change → one
commit per phase → push. Never combine planning/DocTypes/integrations/
scheduler/frontend/stock in one pass. Cite the invariant or decision (INV-x /
D-x / C-x) in every commit message and non-obvious code comment. When the
owner's words and an engineering instinct disagree, surface the conflict —
don't silently pick. The catastrophic failure mode this project guards
against is not a crash; it is a system that LOOKS fine while quietly
corrupting stock counts, the catalog, or the books. Fail closed, loudly,
every time.
