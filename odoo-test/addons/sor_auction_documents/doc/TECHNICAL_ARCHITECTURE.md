# Technical Architecture: sor_auction_documents

## Overview

`sor_auction_documents` is a **non-auto-install feature module** delivering the complete document production layer for auction houses: Pre-Sale Advice, Post-Sale Advice, and Vendor Settlement Statement. It adds three new models (`sor.pre.sale.advice`, `sor.post.sale.advice`, `sor.vendor.settlement`), three QWeb PDF templates, batch generation logic on `sor.event`, email send actions, a four-state VSS lifecycle, and per-company sequence provisioning.

```
sor_commercial_auction_house   sor_bidding
          \                      /
           \                    /
         sor_auction_documents        (auto_install=False)
                    |
          sor_consignment_auction     (auto_install=True, bridge)
```

---

## Module Pattern

```python
'category': 'Hidden/Technical',
'depends': ['sor_commercial_auction_house', 'sor_bidding'],
'auto_install': False,
'application': False,
'post_init_hook': 'post_init_hook',
```

- `auto_install: False` — installed explicitly by the auction house operator.
- `post_init_hook` — provisions a per-company `sor.vendor.settlement` sequence for all existing companies at install time. `res.company.create` override provisions the sequence for companies added after install.

---

## Architecture Decisions

### Three document models rather than one polymorphic model

Pre-Sale Advice, Post-Sale Advice, and Vendor Settlement Statement have different lot filter criteria, different PDF layouts, and VSS has a state machine the others lack. A single polymorphic model with a `doc_type` field would produce a tangled state machine and complex view logic. Three independent models with a shared pattern are preferred.

### Lot back-references (pre_sale_advice_id, post_sale_advice_id, vendor_settlement_id) on sor.lot

Document → lot relationship uses One2many (document → lots via back-reference on `sor.lot`). This enables:
- Batch generation to assign lots to documents via `lot.write({'pre_sale_advice_id': advice.id})`
- Re-run idempotency by reassigning back-references without creating new document records
- Direct lot-to-document traceability without a Many2many join table

`copy=False` on all three fields — document assignments belong to the specific historical lot record, not a copy.

### _render_qweb_pdf called with report.id (integer)

`report._render_qweb_pdf(report.id, [record.id])` uses the integer ID as `report_ref`. The `_get_report` fast path for integers (`isinstance(report_ref, int)` → `browse(report_ref)`) is the most reliable resolution path in Odoo 19. The `isinstance(report_ref, models.Model)` branch in the same function did not trigger reliably when the account module override of `_pre_render_qweb_pdf` called `_get_report` in a secondary context.

### VSS sequence format: combined `{seq}/{sale_number}` stored in name field at creation

`sor.vendor.settlement.name` stores the combined reference at create time: `{seq_number}/{sale_number}` (e.g. `100001/A133`). The `create()` override fetches the next sequence number, then browses `event_id` to read `sale_number`, and builds the combined string before calling `super().create()`. If `event_id` is absent or `sale_number` is empty at creation time, the name falls back to the raw sequence number only. The PDF template reads `name` directly — it does not re-combine at render time.

### auction_licence_ref and auction_director_signature on sor_auction_documents, not sor_commercial_auction_house

These two fields are specific to the consignor-facing document layer introduced in this sprint. `sor_buyer_invoice_auction_house` (buyer-facing) does not need them. Adding them here avoids polluting the commercial module with document-specific configuration.

---

## Models

### sor.pre.sale.advice (`models/sor_pre_sale_advice.py`)

| Field/Method | Type/Return | Notes |
|---|---|---|
| `name` | Char, computed+stored | `PSA/{sale_number}/{consignor.ref or id}` |
| `event_id` | Many2one `sor.event` | Required; `check_company=True`; `ondelete='cascade'` |
| `consignor_id` | Many2one `res.partner` | Required; `check_company=True` |
| `company_id` | Many2one `res.company` | Required; default lambda |
| `lot_ids` | One2many `sor.lot` via `pre_sale_advice_id` | Catalogued/live lots for this event+consignor |
| `action_send_by_email()` | Opens `mail.compose.message` | Renders PDF, creates attachment, pre-populates composer with consignor email |

Inherits `mail.thread`, `mail.activity.mixin`. `_check_company_auto = True`.

### sor.post.sale.advice (`models/sor_post_sale_advice.py`)

Same structure as `sor.pre.sale.advice` with:
- `name` format: `PSA-POST/{sale_number}/{consignor.ref or id}`
- `lot_ids` via `post_sale_advice_id`
- Lots filtered to `state in ('sold', 'passed')` at generation time

### sor.vendor.settlement (`models/sor_vendor_settlement.py`)

| Field/Method | Type/Return | Notes |
|---|---|---|
| `name` | Char, required, readonly | Combined reference `{seq}/{sale_number}` built at creation by `create()` override; falls back to raw sequence number if `sale_number` absent; default `'New'` |
| `state` | Selection | `draft` / `payment_confirmed` / `sent` / `cancelled`; tracking=True |
| `event_id` | Many2one `sor.event` | Required; `check_company=True`; `ondelete='restrict'` |
| `consignor_id` | Many2one `res.partner` | Required; `check_company=True` |
| `company_id` | Many2one `res.company` | Required; default lambda |
| `currency_id` | Related `company_id.currency_id` | Stored; used by Monetary widgets |
| `lot_ids` | One2many `sor.lot` via `vendor_settlement_id` | |
| `total_hammer` | Monetary, computed, stored | `sum(lot_ids.mapped('hammer_price'))` |
| `total_commission` | Monetary, computed, stored | `sum(l.hammer_price * l.sellers_commission_pct / 100)` |
| `net_proceeds` | Monetary, computed, stored | `total_hammer - total_commission` |
| `action_confirm_payment()` | — | `draft` → `payment_confirmed` |
| `action_send_by_email()` | Opens wizard | `payment_confirmed` → `sent`; renders PDF, opens email wizard |
| `action_cancel()` | — | `draft` → `cancelled`; irreversible from UI |
| `action_bulk_mark_sent()` | — | List action; filters to `payment_confirmed`; renders PDF per VSS; `message_post()`; transitions to `sent` |

Inherits `mail.thread`, `mail.activity.mixin`. `_check_company_auto = True`.

### Extensions to sor.lot (`models/sor_lot_auction_docs.py`, `models/sor_lot_pre_sale.py`)

| Field | Type | Notes |
|-------|------|-------|
| `consignor_id` | Many2one `res.partner` | Optional; `check_company=True`; `readonly="state not in ('draft', 'catalogued')"` in view |
| `hammer_price_vat_included` | Boolean | Defaults from `company.hammer_price_vat_included` |
| `pre_sale_advice_id` | Many2one `sor.pre.sale.advice` | Back-reference; `copy=False` |
| `post_sale_advice_id` | Many2one `sor.post.sale.advice` | Back-reference; `copy=False` |
| `vendor_settlement_id` | Many2one `sor.vendor.settlement` | Back-reference; `copy=False` |

### Extensions to sor.event (`models/sor_event_auction_docs.py`)

Adds `pre_sale_advice_count`, `post_sale_advice_count`, `vendor_settlement_count` (computed `store=False`); all six action methods; three `action_view_*` smart button methods.

### Extensions to res.company (`models/res_company.py`)

Adds `auction_sale_terms` (Html), `auction_bank_details` (Text), `auction_licence_ref` (Char), `auction_director_signature` (Text). `create()` override provisions `sor.vendor.settlement` sequence for new companies.

### Extensions to res.config.settings (`models/res_config_settings.py`)

Related fields surfacing all four new company fields plus `hammer_price_vat_included` and `auction_vat_notice` (defined in `sor_commercial_auction_house`).

---

## Views

### `views/sor_lot_auction_docs_views.xml`

- **Form view** — inherits `sor_lotting.sor_lot_view_form`. XPath: `//field[@name='company_id'][@groups='base.group_multi_company']` (structural selector; `string` selectors rejected in Odoo 19). Inserts `consignor_id` and `hammer_price_vat_included`.
- **List view** — inherits `sor_lotting.sor_lot_view_list`. Adds `consignor_id` as `optional="hide"` after `reserve_price`.

### `views/sor_event_auction_docs_views.xml`

Inherits `sor_events.sor_event_view_form`. Inserts `is_commercial` as invisible declaration field (required by Odoo 19 FormArchParser) and five action buttons (Pre-Sale Advice generate/send, Post-Sale generate, Vendor Settlements generate). Post-Sale send button is in `sor_post_sale_advice_views.xml` to separate concerns.

### `views/sor_pre_sale_advice_views.xml`

List view, form view (with Lots notebook page), window action, smart button inheritance on `sor.event`.

### `views/sor_post_sale_advice_views.xml`

Same pattern as PSA. Also contains a second `sor.event` form view inheritance adding the "Send Post-Sale Advices" batch button (inherited from `view_sor_event_form_inherit_auction_docs_buttons`, not from the base event form, to place it adjacent to the Post-Sale generate button).

### `views/sor_vendor_settlement_views.xml`

List view with state badge widget, form view with statusbar + lifecycle buttons + Lots/Totals notebook, window action, bulk-send server action (`ir.actions.server` with `binding_model_id` and `binding_view_types = 'list'`), smart button inheritance on `sor.event`.

### `views/res_config_settings_views.xml`

`<block>` (not `<app>`) placed after `sor_fee_schedules_container`. `invisible="business_model != 'auction_house'"`.

---

## Module File Structure

```
sor_auction_documents/
├── __manifest__.py                     — dependencies; post_init_hook
├── __init__.py                         — imports models and post_init_hook
├── hooks.py                            — post_init_hook; _ensure_vss_sequence; res.company.create override
├── models/
│   ├── __init__.py
│   ├── sor_lot_auction_docs.py         — consignor_id, hammer_price_vat_included on sor.lot
│   ├── sor_lot_pre_sale.py             — pre_sale_advice_id, post_sale_advice_id, vendor_settlement_id on sor.lot
│   ├── sor_pre_sale_advice.py          — sor.pre.sale.advice model + email send
│   ├── sor_post_sale_advice.py         — sor.post.sale.advice model + email send
│   ├── sor_vendor_settlement.py        — sor.vendor.settlement model + lifecycle + bulk-send
│   ├── sor_event_auction_docs.py       — batch generation + send + smart button methods on sor.event
│   ├── res_company.py                  — auction_sale_terms, auction_bank_details, auction_licence_ref, auction_director_signature
│   └── res_config_settings.py         — related fields surfacing company settings
├── report/
│   ├── sor_pre_sale_advice_report.xml  — ir.actions.report record + QWeb template
│   ├── sor_post_sale_advice_report.xml — ir.actions.report record + QWeb template (margin scheme branching)
│   └── sor_vendor_settlement_report.xml — ir.actions.report record + QWeb template (commission calc; totals; bank details)
├── data/
│   └── sor_vendor_settlement_sequence.xml — ir.sequence for main_company; noupdate=1
├── security/
│   ├── ir.model.access.csv             — access rules for three new models
│   └── sor_auction_documents_rules.xml — multi-company ir.rule for sor.vendor.settlement
├── views/
│   ├── sor_lot_auction_docs_views.xml
│   ├── sor_event_auction_docs_views.xml
│   ├── sor_pre_sale_advice_views.xml
│   ├── sor_post_sale_advice_views.xml
│   └── sor_vendor_settlement_views.xml — includes bulk-send server action
├── static/src/css/
│   └── sor_auction_documents.css       — PDF table styling
├── i18n/
│   └── sor_auction_documents.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_auction_documents.py   — 20 tests; TransactionCase; setUpClass
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/sor_vendor_settlement.py` | Four-state lifecycle; computed totals; bulk-send list action |
| `models/sor_event_auction_docs.py` | All batch generation logic; idempotency; state gate enforcement |
| `report/sor_vendor_settlement_report.xml` | Commission calculation in QWeb; margin scheme branching; bank details; totals row |
| `hooks.py` | Per-company VSS sequence provisioning — must use `sudo()` |
| `views/sor_vendor_settlement_views.xml` | Bulk-send server action binding; badge widget on state |

---

## Composability Boundary

| Installation | Lot form | Event form | Document generation |
|---|---|---|---|
| `sor_auction_documents` alone | `consignor_id` editable Draft/Catalogued; `hammer_price_vat_included` visible | Pre-Sale/Post-Sale/VSS buttons visible (commercial events only) | Staff set consignor manually; batch generates documents |
| + `sor_consignment_auction` | `consignor_id` read-only; Fetch Consignor / Refresh buttons present | Document buttons unchanged | Consignor auto-populated from intake picking before document creation |

---

## Special Concerns

### Manifest data load order — reports before views

View XML that references a report action via `%(action_report_xxx)d` interpolation (e.g. Print buttons) requires the report XML to load before the view XML. The manifest lists `report/` before `views/`. Placing `views/` first causes a `ParseError` at install time (forward reference to an unresolved XML ID).

### is_commercial arch declaration required in Odoo 19

The event form buttons use `invisible="not is_commercial"`. Odoo 19's `FormArchParser` resolves field types from the combined arch at parse time. `is_commercial` must be declared as `<field name="is_commercial" invisible="1"/>` in the same XPath insertion, or the parser raises `Cannot read properties of undefined (reading 'type')`.

### Send Post-Sale Advices button in a separate view inheritance

The "Send Post-Sale Advices" button inherits from `view_sor_event_form_inherit_auction_docs_buttons` (defined in `sor_event_auction_docs_views.xml`) rather than from the base event form. This places it adjacent to the Post-Sale generate button without needing a second XPath into the base form.

### VSS sequence requires sudo() in hooks

`post_init_hook` and `res.company.create` override must call `sudo()` on the `ir.sequence` recordset before creating sequences. Companies being processed may not be in the current user's `allowed_company_ids` — without `sudo()`, `_check_company_auto` rejects the create.

### _render_qweb_pdf integer ID pattern

Use `report._render_qweb_pdf(report.id, [record.id])` — not `report._render_qweb_pdf(report, [record.id])` and not `report._render_qweb_pdf([record.id])`. The account module's `_pre_render_qweb_pdf` override calls `_get_report(report_ref)` which uses `env.ref()` as a final fallback. Passing a list raises `TypeError: unhashable type: 'list'`. Passing the record object did not trigger the `isinstance(models.Model)` branch reliably. The integer ID path is unconditional and safe.

### ORM cache and server restart after raw SQL changes

Odoo's ORM caches `ir.config_parameter` and company field values at startup. Raw SQL changes (e.g. setting `report.url` or `company_details` via `psql`) are not visible to the running server until it is restarted. Always run `docker compose restart odoo` after any raw SQL changes to these tables.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  --http-port=8072 \
  -d odoo --test-enable --stop-after-init -u sor_auction_documents
```

Expected: 0 failed, 0 errors of 20 tests (plus 50 cumulative for all loaded modules).

---

## Story Reference

- Story 01: `.backlog/current/Auction House Documents/stories/01_Pre-Sale-Advice.md`
- Story 02: `.backlog/current/Auction House Documents/stories/02_Post-Sale-Advice.md`
- Story 03: `.backlog/current/Auction House Documents/stories/03_Vendor-Settlement-Statement.md`
