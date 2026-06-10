# Canadian Outlet ERP — Configuration Contract

Status: Phase 1 planning document. Normative once approved.

The previous system failed here in a specific way: `secrets/.env.example`, the
config loader, scripts, and adapters each used **different key names and different
loading mechanisms**, so a correctly filled `.env` could still be invisible to the
app. This document exists to make that impossible: there is exactly one contract
and exactly one loading mechanism, and every adapter, script, and doc must agree
with it.

---

## 1. Platform pins

| Component | Pin | Notes |
|---|---|---|
| Frappe | `version-15` branch | Upstream, unmodified |
| ERPNext | `version-15` branch | Upstream, unmodified |
| Custom app | `canadian_outlet` | Own private repository |

- Upgrades are deliberate: `bench update --patch` within version-15 on a chosen
  schedule; a major-version move (e.g. v16) is its own scoped project.
- PROVISIONAL (Phase 0 question 1): version-15 is the working assumption until
  explicitly confirmed.

## 2. The single loading mechanism

**All runtime configuration and secrets are read from the Frappe site config**
(`site_config.json` / `common_site_config.json`) via `frappe.conf`.

Rules:

- The app reads configuration **only** through one module:
  `canadian_outlet.co_core.settings` (created in Phase 2+). No other module reads
  `frappe.conf`, environment variables, or files directly.
- The app does **not** read `.env` files. If the hosting setup uses env files or
  container secrets, the deployment tooling is responsible for materializing them
  into `site_config.json` — the app never knows or cares.
- Missing **required** configuration fails loudly at the point of use with a clear
  error naming the exact missing key (fail closed, INV-10). No silent defaults for
  credentials or endpoints.
- Business toggles that belong to operators (not deployments) live in the
  **Canadian Outlet Settings** DocType instead (see `docs/DATA-MODEL.md`), never in
  site config. Rule of thumb: secrets and infrastructure → site config; business
  behavior → Settings DocType.
- PROVISIONAL (Phase 0 question 2): site-config-as-source assumes self-managed
  bench or frappe_docker hosting. If Frappe Cloud is chosen, this section is
  re-validated (Frappe Cloud also exposes site config, so the contract likely
  stands).

## 3. Key naming convention

- All keys are lower_snake_case and prefixed `co_<domain>_`.
- One domain prefix per integration. The exact key set for an integration is added
  to the registry below **in the phase that builds that integration** — never
  earlier, never ad hoc in code.

## 4. Configuration key registry

This registry is the contract. A key not listed here must not be read by app code;
a key listed here must be read with exactly this name.

### 4.1 Core (Phase 2+)

| Key | Required | Purpose |
|---|---|---|
| `co_environment` | yes | `dev`, `staging`, or `production`. Guards anything that must not run outside production and enables dev-only affordances. |

### 4.2 WooCommerce (Phase 13 — final)

| Key | Required | Purpose |
|---|---|---|
| `co_woocommerce_base_url` | yes | Store base URL (no trailing slash needed) |
| `co_woocommerce_consumer_key` | yes | Woo REST API consumer key |
| `co_woocommerce_consumer_secret` | yes | Woo REST API consumer secret |
| `co_woocommerce_api_path` | no | API path prefix; defaults to `/wp-json/wc/v3` |

### 4.3 ShipStation (Phase 14 — final)

| Key | Required | Purpose |
|---|---|---|
| `co_shipstation_api_key` | yes | ShipStation API key |
| `co_shipstation_api_secret` | yes | ShipStation API secret |
| `co_shipstation_base_url` | no | Defaults to `https://ssapi.shipstation.com` |

### 4.4 Amazon SP-API (Phase 15 — final)

The LWA-vs-SPAPI naming confusion of the old repo is resolved by fiat here:

| Key | Required | Purpose |
|---|---|---|
| `co_amazon_lwa_client_id` | yes | Login-with-Amazon client ID |
| `co_amazon_lwa_client_secret` | yes | LWA client secret |
| `co_amazon_lwa_refresh_token` | yes | LWA refresh token |
| `co_amazon_marketplace_ids` | yes | Comma-separated marketplace IDs |
| `co_amazon_region` | no | `na` (default), `eu`, or `fe` |

### 4.5 Walmart (Phase 16 — final)

| Key | Required | Purpose |
|---|---|---|
| `co_walmart_client_id` | yes | Marketplace API client ID |
| `co_walmart_client_secret` | yes | Marketplace API client secret |
| `co_walmart_base_url` | no | Defaults to `https://marketplace.walmartapis.com` |

## 5. Secrets handling rules

- Secrets never appear in: the git repository, fixtures, test code, log output,
  error messages, Integration Exception records, or Order Import Log records.
- Test suites use synthetic credentials and recorded/synthetic payloads only.
- `site_config.json` is never committed anywhere (it is outside the app repo by
  construction; it must also never be copied into it).
- When an error involves a credential (e.g. 401 from a channel), the log records
  *which key* was used by name, never its value.

## 6. Change control

Adding, renaming, or removing a key requires updating this registry in the same
change as the code that uses it. Code review rejects any `frappe.conf` access
outside `co_core.settings` and any key not present in this file.
