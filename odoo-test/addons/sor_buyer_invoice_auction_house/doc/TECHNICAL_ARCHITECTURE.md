# SOR Buyer Invoice × Auction House — Technical Architecture

## 1. Overview

`sor_buyer_invoice_auction_house` is the auction-house-specific invoice bridge. It activates when `sor_buyer_invoice` and `sor_commercial_auction_house` are both installed. `sor_bidding` is **not** a hard dependency — the module works in both bidding and non-bidding deployments, routing to the appropriate buyer data source at runtime.

```
sor_buyer_invoice ──────────────────────────┐
sor_commercial_auction_house ───────────────┴─ sor_buyer_invoice_auction_house
```

**Dual buyer data source:** When `sor_bidding` is installed, buyer identity is derived from `sor.bid` records with `is_winning_bid=True`. When it is absent, buyer identity is derived from `sor.lot` records with `state='sold'` and `buyer_id` set (the Story 01 fallback field). Detection uses `'sor.bid' in self.env.registry` — a registry check, not a database module-state query.

---

## 2. Module pattern

```python
'depends': ['sor_buyer_invoice', 'sor_commercial_auction_house'],
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

**Payment methods live on the Bank journal, not AUC (Story 04):** The original plan attached the four incoming payment methods to the AUC journal. Confirmed unworkable by reading Odoo 19 source: `AccountPaymentRegister._get_batch_available_journals()` hard-filters the payment registration wizard's journal picker to `journal.type in ('bank', 'cash', 'credit')` — a `type='sale'` journal (AUC) is never offered, not as a default and not as a manual selection. AUC also cannot be changed to `type='bank'`/`'cash'` — `AccountMove._check_journal_move_type()` raises a `ValidationError` on any customer invoice whose journal is not `type='sale'`. `_ensure_auction_payment_methods` therefore operates entirely on the company's own `type='bank'` journal (the one the chart template already provisions) and does not touch or depend on AUC at all. See `odoo_conventions/orm_and_field_patterns.md` — "`account.payment` goes straight to Paid only when its liquidity account is `reconcile=False`."

**Going-forward-only provisioning:** The idempotency check for the four payment method lines is a name match only (`journal.inbound_payment_method_line_ids.mapped('name')`), not an account-correctness check. A company with a pre-existing line under one of the four names (e.g. a real client environment configured manually before this story) is left untouched, even if that line's account is wrong (e.g. still pointing at Outstanding Receipts). This is a deliberate scope boundary, not an oversight — reconfiguring pre-existing lines is a manual step this provisioning does not perform.

**Bulk-send needs a dedicated template — the native `account.email_template_edi_invoice` cannot be reused for mass-mail (Auction Documents and Invoice Email Behaviour sprint):** The original plan was to reuse Odoo's native invoice template directly for the bulk-send composer, on the theory that it's the same template individual "Send & Print" already uses. Confirmed unworkable by reading Odoo source before any code was written: (1) `account.email_template_edi_invoice.report_template_ids` is `eval="[]"` — empty, so it carries no report to auto-attach; (2) `mail.thread._process_attachments_for_template_post()` (the hook that would otherwise auto-attach something during mass-mail send) is a no-op in base `mail.thread`, only overridden by `account_edi`, which is not a dependency of any `sor_buyer_invoice*` module; (3) individual "Send & Print" doesn't go through `mail.compose.message` mass-mail mode at all — it uses a dedicated `account.move.send` wizard that generates and attaches the PDF itself, bypassing the generic template-attachment mechanism entirely. Reusing the native template in mass-mail mode would send an email with **no PDF attached** — worse than the pre-sprint behaviour. The correct design is a new, SOR-owned `mail.template` (`mail_template_sor_buyer_invoice_bulk`) whose `report_template_ids` references `account.account_invoices` — the same native report action individual send resolves to (the bespoke SOR/auction-house layout is dispatched internally within that one action via `_get_name_invoice_report()`, not via a separate action per module), so the bulk path picks up the correct bespoke PDF automatically. Individual "Send & Print" is completely untouched by this change.

**Three defects found and fixed at Show & Tell — shared with the equivalent `sor_auction_documents` fix, since both modules hit the identical Odoo mechanisms:**

1. `mail_template_sor_buyer_invoice_bulk` initially omitted `use_default_to eval="False"` — `use_default_to` defaults to `True` on `mail.template` and, left at that default, silently discards `partner_to` in mass-mail mode, producing a `mail.mail` with zero recipients while `action_bulk_send_sor_invoice()`'s own logic still (correctly) decided the buyer had a valid email. Fixed by adding the field.
2. `action_server_bulk_send_buyer_invoice`'s `code` field called `records.action_bulk_send_sor_invoice()` as a bare expression instead of `action = records.action_bulk_send_sor_invoice()` — the returned `display_notification` was silently discarded by the `ir.actions.server` execution model.
3. The `display_notification` action returned by `action_bulk_send_sor_invoice()` lacked `'next': {'type': 'ir.actions.act_window_close'}` — the invoice list never reloaded or cleared its selection after the action completed.

See `odoo_conventions/orm_and_field_patterns.md` for the full mechanism behind all three — the same fixes were applied in lockstep to `sor_auction_documents`'s PSA/POSA/VSS bulk-send paths.

---

## 4. Models

### `account.move` (extended)

| Field | Type | Details |
|-------|------|---------|
| `sor_lot_ids` | Many2many → `sor.lot` | Relation table `sor_buyer_invoice_lot_rel` |
| `action_bulk_send_sor_invoice()` | Method | List bulk action (Actions menu → "Send to Buyers"). Filters to `move_type == 'out_invoice'` with a partner — records excluded here are counted as `not_eligible_count` (BUG-04) rather than silently dropped; splits the remainder by email presence; sends via mass-mail using `mail_template_sor_buyer_invoice_bulk`; chatter note on skip; returns `display_notification` reporting sent/skipped/not-eligible, chained with `'next': {'type': 'ir.actions.act_window_close'}` |

### `account.move.line` (extended)

| Field | Type | Details |
|-------|------|---------|
| `sor_lot_id` | Many2one → `sor.lot` | `ondelete='set null'` |
| `sor_line_type` | Selection | `hammer` / `buyers_premium` |
| `sor_buyers_premium_pct` | Float | `digits=(10, 1)` — rate at invoice generation time |

### `sor.event` (extended)

| Method | Description |
|--------|-------------|
| `action_generate_buyer_invoices()` | Full generation flow: compute `already_invoiced_lot_ids` from `account.move.sor_lot_ids` at (event, buyer, **lot**) granularity (BUG-05, not (event, buyer)) → detect `sor_bidding` presence → find buyers with at least one not-yet-invoiced lot (winning bids or sold lots with `buyer_id`) → group by buyer → create one move per buyer covering only their unbilled lots. Raises only when no lot remains to invoice. |
| `_prepare_buyer_invoice_lines(lots, buyer)` | Returns command tuples for hammer + premium lines |

### `res.company` (extended)

| Method | Description |
|--------|-------------|
| `create()` override | Calls `_ensure_auction_journal` and `_ensure_buyer_invoice_sequence` for each new company |

### `account.chart.template` (extended)

| Method | Description |
|--------|-------------|
| `_post_load_data()` override | Re-provisions AUC journal and the four payment method lines after each chart load |

### `hooks.py` (module-level functions, not model methods)

| Function | Description |
|----------|-------------|
| `_ensure_auction_journal(env, company)` | Idempotent AUC journal provisioning |
| `_ensure_auction_payment_methods(env, company)` | Idempotent (by name) provisioning of Debit Card, Bank Transfer, Cheque, Bank Draft on the company's `type=bank` journal, each with `payment_account_id` explicitly set to that journal's own account |
| `_ensure_buyer_invoice_sequence(env, company)` | Idempotent per-company invoice sequence provisioning |
| `_find_income_account(env, company)` | Raw SQL lookup for the company's income account (used by `_ensure_auction_journal` only) |

---

## 5. Views

| File | Description |
|------|------------|
| `views/sor_event_views.xml` | Adds "Generate Buyer Invoices" button to event form |
| `views/account_move_views.xml` | Adds `sor_lot_ids` widget to invoice form |
| `report/account_invoice_report_bridge.xml` | Inherits `sor_buyer_invoice.report_invoice_document_sor_buyer_invoice` (Auction MVP Refinements Story 03 rebuild — now a fully standalone base, not inherit-and-patch of native Odoo); `position="replace"` on `//div[@name='sor_invoice_line_table']` swaps the base's generic fallback table for the lot breakdown table, VAT columns, and statutory notice; the base's own `sor_invoice_payment_status` block (a sibling div) is untouched by this replace |
| `data/server_actions.xml` | `action_server_bulk_send_buyer_invoice` — `ir.actions.server` bound to `account.move` list view (Actions menu → "Send to Buyers"); `code` field must assign to `action` (`action = records.action_bulk_send_sor_invoice()`) or the returned notification is silently discarded |

---

## 6. Module file structure

```
sor_buyer_invoice_auction_house/
├── __manifest__.py
├── __init__.py
├── hooks.py                         # _ensure_auction_journal, _ensure_auction_payment_methods,
│                                     # _ensure_buyer_invoice_sequence, post_init_hook
├── models/
│   ├── __init__.py
│   ├── account_chart_template.py    # _post_load_data override — re-provisions AUC journal + payment methods
│   ├── account_move.py              # sor_lot_ids field, action_bulk_send_sor_invoice()
│   ├── account_move_line.py         # sor_lot_id, sor_line_type, sor_buyers_premium_pct fields
│   ├── res_company.py               # create() override for new-company provisioning
│   └── sor_event.py                 # action_generate_buyer_invoices, _prepare_buyer_invoice_lines
├── data/
│   ├── sor_buyer_invoice_auction_house_sequence.xml
│   ├── mail_template_data.xml       # mail_template_sor_buyer_invoice_bulk; noupdate=1
│   └── server_actions.xml           # action_server_bulk_send_buyer_invoice
├── migrations/
│   └── 19.0.1.1.0/
│       └── post-migrate.py          # provisions payment methods on -u upgrade (post_init_hook only fires on -i)
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
| `hooks.py` | `_ensure_auction_journal`, `_ensure_auction_payment_methods`, `_ensure_buyer_invoice_sequence` — all three must be idempotent (search before create) |
| `models/account_chart_template.py` | Prevents AUC journal deletion on chart load and re-provisions payment methods after — do not remove |
| `migrations/19.0.1.1.0/post-migrate.py` | Provisions payment methods for already-installed companies on `-u` upgrade — `post_init_hook` alone does not reach them |
| `models/sor_event.py` | `_prepare_buyer_invoice_lines` is the designated extension point for future invoice bridges |
| `data/mail_template_data.xml` | `use_default_to eval="False"` on `mail_template_sor_buyer_invoice_bulk` is load-bearing — without it, bulk send silently produces recipient-less mail (see Architecture Decisions) |

---

## 8. Composability boundary

| Installation | Behaviour |
|-------------|-----------|
| `sor_buyer_invoice` alone | Event field on invoice; smart button; regulatory footer; no generate button |
| + `sor_buyer_invoice_auction_house` (no `sor_bidding`) | AUC journal; four payment methods on the Bank journal; generate button driven by sold lots with `buyer_id`; lot breakdown PDF; buyer's premium; VAT columns if `vat_margin_scheme` |
| + `sor_buyer_invoice_auction_house` + `sor_bidding` | As above, but generate button driven by winning bids; `buyer_id` on lot hidden by `sor_bidding` view override |
| Without `sor_commercial_auction_house` | Bridge not installed; `sor_buyer_invoice` behaves as standalone |

---

## 9. Special concerns

**`auto_install` with pre-existing parents:** If both parent modules were already installed before this bridge was introduced to the codebase, Odoo does not auto-install it retroactively. Use `-i sor_buyer_invoice_auction_house` explicitly in the dev environment.

**AUC journal `default_account_id` provisioning:** `_ensure_auction_journal` sets `default_account_id` using `_find_income_account(env, company)` — a raw SQL lookup via `account_account_res_company_rel` (required because `account.account` uses a Many2many `company_ids` in Odoo 19, not a simple `company_id`). If the company has no income account (e.g. no chart of accounts applied), the journal is created without a `default_account_id` and invoice generation will fail with "Missing required account". This only affects installations where the chart of accounts is not applied to the company. Fixed in BUG-05 (UAT).

**"M-" VAT indicator label:** The Irish Margin Scheme notation "M-" is hardcoded in the PDF template. For future jurisdictions this may need to be configurable.

**Payment method provisioning depends on the chart being applied:** `_ensure_auction_payment_methods` looks up the company's `type=bank` journal and is a no-op if none exists yet. On a genuinely fresh company this is fine — `_post_load_data` re-runs the provisioning after the chart (and its journals) are in their final state. But the function itself performs no retry/deferred logic; if called in a context where the chart has not yet been applied and is never re-triggered, no payment methods will exist. This mirrors the same constraint already documented for `_ensure_auction_journal`.

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

Story 03 — `sor_buyer_invoice_auction_house`: `.backlog/previous/` (Auction House Invoice — see the archived sprint for the original bridge delivery)

Story 04 — Payment Method Line Provisioning: `.backlog/previous/` (Auction Refinements 01)

Auction MVP Refinements Story 03 — Bespoke Buyer Invoice PDF (bridge template rebuild against the new standalone base): `.backlog/current/Auction MVP Refinements/stories/03_Bespoke-Buyer-Invoice-PDF.md`

Auction Documents and Invoice Email Behaviour, Story 03 — VSS and Buyer Invoice Bulk Send Rewrite (dedicated bulk-send template; `action_bulk_send_sor_invoice()` rewrite): `.backlog/current/Auction Documents and Invoice Email Behaviour/stories/03_VSS-and-Buyer-Invoice-Bulk-Send-Rewrite.md`
