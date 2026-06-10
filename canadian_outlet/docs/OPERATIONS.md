# Canadian Outlet ERP — Operations Runbook

Status: living operations document. Audience: the humans running the system.
The rules behind every step live in `docs/ERP-INVARIANTS.md`; when this
runbook and the invariants disagree, the invariants win.

---

## 1. One-time setup (per site)

1. **Site config** (`site_config.json`): set the keys for each integration you
   use, exactly as named in `docs/CONFIGURATION.md` §4. Missing required keys
   fail loudly at the point of use — that is by design.
2. **Canadian Outlet Settings**: set `default_warehouse` (canonical: 1431
   Yonge). Leave `imports_enabled` OFF until go-live.
3. **Channels**: create one Channel per marketplace instance, with a
   `default_customer` (generic per-channel customer policy). Channels are
   created disabled; enable deliberately.
4. **Fulfillment rules** (one explicit call per channel, from the desk console
   or `bench execute`):
   - WooCommerce: `canadian_outlet.co_orders.adapters.woocommerce.setup_woocommerce_channel`
   - Amazon: `canadian_outlet.co_orders.adapters.amazon.setup_amazon_channel`
   - Walmart: `canadian_outlet.co_orders.adapters.walmart.setup_walmart_channel`
5. **Channel Listings**: map every external SKU/ASIN/item ID to its ERPNext
   Item. Unmapped listings do not import — they become Integration Exceptions
   (INV-4). That is the system working, not failing.

## 2. Importing orders (daily scheduled sync once enabled, plus operator-triggered runs)

A daily scheduled sync (Phase 24) imports the last 2 days from every ENABLED
channel — it no-ops entirely while `imports_enabled` is off. Manual runs for
backfill or testing:

```text
woocommerce.import_woocommerce_orders(channel, statuses=..., modified_after=...)
amazon.import_amazon_orders(channel, created_after=...)
walmart.import_walmart_orders(channel, created_start_date=...)
```

Each returns `{created, duplicate, exception}` counts. Re-running with
overlapping windows is safe — imports are idempotent (INV-11).

## 3. Exception triage (the review queue)

Work the Integration Exception list, oldest `Open` first:

1. Read `failure_stage` + `failure_reason`.
   - `Resolution` → create/fix the Channel Listing.
   - `Classification` → inspect the evidence; if a new legitimate marketplace
     value appeared, add the Channel Fulfillment Map row deliberately. Never
     map something to SELF just to make the error go away (INV-5).
   - `Customer` / `Creation` → fix the named master data (default customer,
     price list, exchange rate).
2. Set the exception to **Resolved**, then run
   `canadian_outlet.co_orders.replay.replay_exception(name)`.
   - Success → order imports; exception stays Resolved.
   - Same failure again → status flips to **Failed Replay**; back to triage.
3. Only use **Ignored** (reason required) for cancelled source orders, test
   payloads, or confirmed non-actionable duplicates.

## 4. SELF order fulfillment (stock moves only here)

```text
Sales Order (draft, SELF) → human reviews → human submits SO
  → create draft Delivery Note:
      standard ERPNext flow, or
      canadian_outlet.co_inventory.delivery_note_service.create_draft_delivery_note(so)
  → human verifies physical pick/ship → human SUBMITS the Delivery Note
  → stock deducts at 1431 Yonge, exactly once
```

- A draft Delivery Note is NOT a deduction (INV-8).
- FBA/WFS orders never get Delivery Notes; close them administratively.
- **This queue must have a named owner.** If nobody owns it, orders ship
  physically while stock never deducts — the exact failure this system was
  rebuilt to prevent.

## 5. Shipment status (ShipStation)

`canadian_outlet.co_shipping.shipstation.import_shipstation_shipments(channel, ship_date_start=...)`
records Shipment Status Events. By default a "shipped" event is informational
only. With the STOCK-FLOW §5 kill switch ON
(`auto_submit_delivery_note_on_shipped`), a shipped event SUBMITS the existing
draft Delivery Note of the matching SELF order — it never creates documents,
never touches FBA/WFS, and a failed submit leaves the draft in the human
queue.

## 5A. Reports, workspace, settlement

- **Canadian Outlet workspace** (desk): shortcuts to the triage queues and the
  reports below.
- Reports: *Integration Exception Aging* (work oldest first), *Channel Sales
  Summary*, *Channel Listing Health* (fix inactive/disabled mappings before
  they become exceptions), *Reorder Status* (items below their human-set
  reorder levels — purchasing stays a human decision).
- **Amazon settlement check** (read-only, writes nothing):
  `canadian_outlet.co_billing.settlement.reconcile_amazon_settlement(channel, file_content)`
  — review Unmatched rows; GL posting decisions stay human.

## 6. Retention purge

`canadian_outlet.co_core.retention.purge_expired_payload_copies()` clears
stored payload copies on terminal exceptions older than 90 days
(docs/PRIVACY-REDACTION.md §5). It runs weekly as a Phase 24 scheduled job
and can also be invoked manually.

## 7. Kill switches (fail closed)

- Global: Canadian Outlet Settings → `imports_enabled` off.
- Per channel: Channel → `enabled` off.
Both make import runs raise immediately and create nothing.

## 8. Go-live checklist

- [ ] Real `canadian_outlet` repo is the deployed source (not a carrier copy)
- [ ] CI green on the target commit
- [ ] Site config keys set for every enabled integration
- [ ] 1431 Yonge confirmed and set as default warehouse
- [ ] Channels created, rules installed, listings mapped for live SKUs
- [ ] Draft-DN review queue owner named
- [ ] Scheduler enabled on the site (runs the daily sync and weekly purge)
- [ ] `imports_enabled` turned on last
