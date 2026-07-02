# SOR Buyer Invoice × Auction House — Technical Architecture

## 1. Overview

`sor_buyer_invoice_auction_house` is the auction-house-specific invoice bridge. It activates when `sor_buyer_invoice`, `sor_commercial_auction_house`, and `sor_bidding` are all installed.

```
sor_buyer_invoice ──────────────────────────┐
sor_commercial_auction_house ───────────────├─ sor_buyer_invoice_auction_house
sor_bidding ─────────────────────────────────┘
```

---

## 2. Module pattern

```python
'depends': ['sor_buyer_invoice', 'sor_commercial_auction_house', 'sor_bidding'],
'auto_install': True,
'application': False,
'category': 'Hidden/Technical',
'post_init_hook': 'post_init_hook',
```

No `uninstall_hook` needed — the module only creates records (journal, sequence) which are cleaned up by Odoo on cascade uninstall.

---

## 3. Architecture decisions

**Separate invoice lines for buyer's premium:** Buyer's premium is stored as a separate `account.move.line` per lot (not as a field on the hammer line). This keeps Odoo accounting correct — invoice total = sum of all line `price_unit` values. The PDF template groups hammer and premium lines by `sor_lot_id` to render a single table row per lot.

**`_prepare_buyer_invoice_lines` as extension point:** Invoice line preparation is extracted into a named method so future bridges (e.g. gallery invoice) can override it via `_inherit` without modifying `action_generate_buyer_invoices`. The method returns `(0, 0, {...})` command tuples.

**`buyers_premium_pct` from `sor.lot` at generation time:** The bridge reads `lot.buyers_premium_pct` — a stored Float set when the lot was created via `default_get` from the company's premium tiers. This is intentional: the rate applicable at lot creation is the binding rate, not the rate at invoice generation time.

**Invoice number assignment after `account.move.create`:** Odoo assigns the sequence number when the move transitions to `posted`. To override with `{sequential}/{sale_number}` format, the bridge sets `move.name` immediately after create (while the move is still in `draft` state).

**`_post_load_data` override for chart of accounts compatibility:** The AUC journal must survive localization chart loading, which deletes all journals before recreating them from the chart template. `AccountChartTemplate._post_load_data` is overridden to re-provision the AUC journal after each chart load. See `sor_multi_company.md` — "Provisioning account.journal when a localization module is in the dependency chain."

---

## 4. Models

### `account.move` (extended)

| Field | Type | Details |
|-------|------|---------|
| `sor_lot_ids` | Many2many → `sor.lot` | Relation table `sor_buyer_invoice_lot_rel` |

### `account.move.line` (extended)

| Field | Type | Details |
|-------|------|---------|
| `sor_lot_id` | Many2one → `sor.lot` | `ondelete='set null'` |
| `sor_line_type` | Selection | `hammer` / `buyers_premium` |
| `sor_buyers_premium_pct` | Float | `digits=(10, 1)` — rate at invoice generation time |

### `sor.event` (extended)

| Method | Description |
|--------|-------------|
| `action_generate_buyer_invoices()` | Full generation flow: idempotency guard → find winning bids → group by buyer → create moves |
| `_prepare_buyer_invoice_lines(lots, buyer)` | Returns command tuples for hammer + premium lines |

### `res.company` (extended)

| Method | Description |
|--------|-------------|
| `create()` override | Calls `_ensure_auction_journal` and `_ensure_buyer_invoice_sequence` for each new company |

### `account.chart.template` (extended)

| Method | Description |
|--------|-------------|
| `_post_load_data()` override | Re-provisions AUC journal after each chart load |

---

## 5. Views

| File | Description |
|------|------------|
| `views/sor_event_views.xml` | Adds "Generate Buyer Invoices" button to event form |
| `views/account_move_views.xml` | Adds `sor_lot_ids` widget to invoice form |
| `report/account_invoice_report_bridge.xml` | Inherits `sor_buyer_invoice.report_invoice_document_sor_buyer_invoice`; inserts lot breakdown table and VAT notice before `sor_auction_footer` |

---

## 6. Module file structure

```
sor_buyer_invoice_auction_house/
├── __manifest__.py
├── __init__.py
├── hooks.py                         # _ensure_auction_journal, _ensure_buyer_invoice_sequence, post_init_hook
├── models/
│   ├── __init__.py
│   ├── account_chart_template.py    # _post_load_data override for chart-safe journal provisioning
│   ├── account_move.py              # sor_lot_ids field
│   ├── account_move_line.py         # sor_lot_id, sor_line_type, sor_buyers_premium_pct fields
│   ├── res_company.py               # create() override for new-company provisioning
│   └── sor_event.py                 # action_generate_buyer_invoices, _prepare_buyer_invoice_lines
├── data/
│   └── sor_buyer_invoice_auction_house_sequence.xml
├── views/
│   ├── sor_event_views.xml
│   └── account_move_views.xml
├── report/
│   └── account_invoice_report_bridge.xml
├── security/
│   └── ir.model.access.csv
├── i18n/
│   └── sor_buyer_invoice_auction_house.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_buyer_invoice_auction_house.py
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## 7. Critical files

| File | Purpose |
|------|---------|
| `hooks.py` | `_ensure_auction_journal` and `_ensure_buyer_invoice_sequence` — both must be idempotent (search before create) |
| `models/account_chart_template.py` | Prevents AUC journal deletion on chart load — do not remove |
| `models/sor_event.py` | `_prepare_buyer_invoice_lines` is the designated extension point for future invoice bridges |

---

## 8. Composability boundary

| Installation | Behaviour |
|-------------|-----------|
| `sor_buyer_invoice` alone | Event field on invoice; smart button; regulatory footer; no generate button |
| + `sor_buyer_invoice_auction_house` | AUC journal; generate button; lot breakdown PDF; buyer's premium; VAT columns if `hammer_price_vat_included` |
| Without `sor_commercial_auction_house` | Bridge not installed; `sor_buyer_invoice` behaves as standalone |

---

## 9. Special concerns

**`auto_install` with pre-existing parents:** If all three parent modules were already installed before this bridge was introduced to the codebase, Odoo does not auto-install it retroactively. Use `-i sor_buyer_invoice_auction_house` explicitly in the dev environment.

**AUC journal `default_account_id` provisioning:** `_ensure_auction_journal` sets `default_account_id` using `_find_income_account(env, company)` — a raw SQL lookup via `account_account_res_company_rel` (required because `account.account` uses a Many2many `company_ids` in Odoo 19, not a simple `company_id`). If the company has no income account (e.g. no chart of accounts applied), the journal is created without a `default_account_id` and invoice generation will fail with "Missing required account". This only affects installations where the chart of accounts is not applied to the company. Fixed in BUG-05 (UAT).

**"M-" VAT indicator label:** The Irish Margin Scheme notation "M-" is hardcoded in the PDF template. For future jurisdictions this may need to be configurable.

---

## 10. Running the tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_buyer_invoice_auction_house
```

---

## 11. Story reference

Story 03 — `sor_buyer_invoice_auction_house`: `.backlog/current/Auction House Invoice/stories/03_Buyer-Invoice-Auction-House-Bridge.md`
