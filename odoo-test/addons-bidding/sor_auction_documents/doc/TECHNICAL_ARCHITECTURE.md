# Technical Architecture: sor_auction_documents

## Overview

`sor_auction_documents` is a **non-auto-install feature module** delivering the complete document production layer for auction houses: Pre-Sale Advice, Post-Sale Advice, and Vendor Settlement Statement. It adds three new models (`sor.pre.sale.advice`, `sor.post.sale.advice`, `sor.vendor.settlement`), three QWeb PDF templates, batch generation logic on `sor.event`, email send actions built on three editable `mail.template` records (individual and bulk, via a shared mass-mail helper), a four-state VSS lifecycle, and per-company sequence provisioning.

```
sor_commercial_auction_house
          |
         sor_auction_documents        (auto_install=False)
                    |
          sor_consignment_auction     (auto_install=True, bridge)
```

---

## Module Pattern

```python
'category': 'Hidden/Technical',
'depends': ['sor_commercial_auction_house', 'mail'],
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

### Content-block scheme (Top/Bottom per document) plus native report_footer for shared content

Auction Refinements 01 replaced four rigid fields (`auction_sale_terms`, `auction_bank_details`, `auction_licence_ref`, `auction_director_signature`) with six per-document Html fields (`psa/posa/vss_content_top/bottom`) plus reuse of Odoo's native `res.company.report_footer` for content shared across all three documents.

A seventh field, `auction_document_footer`, was originally planned to hold that shared content as a `sor_auction_documents`-owned field, rendered as trailing page-body content "distinct from the standard page footer" (per the original AC). It was implemented, then **dropped entirely** during the same Show & Tell session once the PO clarified the shared content should render in the *real* per-page footer (the region with page numbers, repeating on every page). Achieving that with a custom field would require inheriting all 7 of Odoo's `web.external_layout_*` layout variant templates (Standard, Boxed, Bold, Folder, Wave, Bubble, Striped), each of which defines its own footer markup independently — a company can pick any one of them, and there is no single shared hook point across all 7. Rather than take on that maintenance burden, `auction_document_footer` was removed and Odoo's native `company.report_footer` field is used instead — already Html, already rendering correctly in the real footer across every layout variant, with zero new template code.

**Trade-off accepted:** `report_footer` is company-global, not scoped to any report type — it now also appears on Buyer Invoices and every other document type for the company. This is intentional (PO-confirmed): a company that wants document-specific exclusion still has the six Top/Bottom fields available.

**Migration handling:** `migrations/19.0.1.2.0/post-migrate.py` (same version, amended in place rather than bumped, since the dropped field never shipped to a customer install) carries `auction_licence_ref`/`auction_director_signature` content into `report_footer` — appending to (not overwriting) whatever content already exists there.

### Mail template adoption (Auction Documents and Invoice Email Behaviour sprint)

Individual send (`action_send_by_email()`) and bulk send (`action_bulk_send()`, renamed from `action_bulk_mark_sent()`) on all three document models were rewired from hardcoded `default_subject` strings and manual `_render_qweb_pdf()`/`ir.attachment.create()` code to three editable `mail.template` records (`data/mail_template_data.xml`), one per document type, each reused by both send paths (mirroring the native `account.email_template_edi_invoice` pattern). Each template's `report_template_ids` field drives automatic PDF rendering/attachment at send time — this eliminated all of the manual attachment boilerplate that previously existed at each call site.

A shared helper module, `models/mail_bulk_send_utils.py` (plain functions, not a model), factors the common mass-mail-mode send + email-presence split + chatter-on-skip + notification-summary logic used by all three PSA/POSA/VSS `action_bulk_send()` methods, including the `not_eligible_count` reporting (BUG-04, see item 4 below). `sor_buyer_invoice_auction_house` duplicates a small version of the same pattern in its own `account_move.py` rather than depend on this module — that would create a base-to-base module dependency, prohibited by `sor_composability.md`.

**Four defects found across Show & Tell and UAT, none catchable by a Development-stage unit test that only asserts on `state`:**

1. **`use_default_to` defaulting to `True`** on all four new templates silently discarded `partner_to` in mass-mail mode, producing a `mail.mail` with zero recipients while the calling code still (correctly, per its own logic) transitioned `state` to `'sent'`. Individual/comment-mode send was unaffected — only bulk/mass-mail mode hits this code path. Fixed by adding `use_default_to eval="False"` to all four templates. See `odoo_conventions/orm_and_field_patterns.md` for the full mechanism.
2. **`ir.actions.server` `code` field calling the bulk-send method as a bare expression** (`records.action_bulk_send()`) instead of assigning to `action` discarded the returned `display_notification` action entirely — the summary notification never reached the browser, even though state and chatter both worked correctly.
3. **`display_notification` action missing `'next': {'type': 'ir.actions.act_window_close'}`** meant the calling list view never reloaded or cleared its row selection after the action completed, even once (2) was fixed — state changes were only visible after a manual page refresh.
4. **Records excluded by the eligible-starting-state filter (e.g. an already-`sent` PSA in a mixed-state selection) never appeared in the sent/skipped summary at all** (BUG-04, UAT Issue Log #1) — they were dropped before the sent/skipped split ran, indistinguishable from records never selected. Fixed by computing `not_eligible_count = len(self) - len(to_send)` in each `action_bulk_send*` method and threading it through `bulk_send_notification()` as a third, independent segment ("N not eligible (wrong state)"). `sor_buyer_invoice_auction_house`'s `action_bulk_send_sor_invoice()` mirrors the same three-segment logic locally rather than importing the helper (see composability note above).

Defects 1–3 were caught only by live PO testing against a real mail server (Mailhog) during Show & Tell — a Development-stage unit test asserting `psa.state == 'sent'` after `action_bulk_send()` passes regardless of whether the underlying `mail.mail` genuinely has a recipient, since the state write and the mail-generation correctness are two independent code paths. Phase 2 tests added `assertIn(consignor, mail.recipient_ids)` on the created `mail.mail` record specifically to close this gap — `mail.mail._send()`'s actual SMTP dispatch is skipped entirely during `--test-enable` runs (`IrMailServer._disable_send()`), but recipient resolution happens at `mail.mail` *creation* time, before that skip, so it is safely and deterministically testable in `TransactionCase`. Defect 4 was caught at Show & Tell as a design-feedback finding (Category 1) and fixed during UAT triage; the UAT Round 2 post-fix audit added regression tests asserting the notification message content for a mixed-state selection on all four bulk-send call sites (PSA/POSA/VSS/Buyer Invoice).

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
| `action_send_by_email()` | Opens `mail.compose.message` | Sets `default_template_id` to `mail_template_sor_pre_sale_advice`; template's `report_template_ids` drives PDF attachment — no manual render/attach code |
| `action_bulk_send()` | Returns `display_notification` | List bulk action; mass-mail via `mail_bulk_send_utils.bulk_send_via_template()`; chatter on skip; not-eligible count for non-`draft` selections (BUG-04); renamed from `action_bulk_mark_sent()` |

Inherits `mail.thread`, `mail.activity.mixin`. `_check_company_auto = True`.

### sor.post.sale.advice (`models/sor_post_sale_advice.py`)

Same structure as `sor.pre.sale.advice` with:
- `name` format: `PSA-POST/{sale_number}/{consignor.ref or id}`
- `lot_ids` via `post_sale_advice_id`
- Lots filtered to `state in ('sold', 'passed')` at generation time
- `action_send_by_email()`/`action_bulk_send()` identical pattern, using `mail_template_sor_post_sale_advice`

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
| `total_fixed_charges` | Monetary, computed, stored | `sum(lot_ids.mapped('fixed_charge_ids.amount'))` — `fixed_charge_ids` defined in `sor_commercial_auction_house`. `@api.depends` includes `lot_ids.fixed_charge_ids.amount` so the total recomputes when charge lines are added/removed/edited on any lot in the settlement. |
| `net_proceeds` | Monetary, computed, stored | `total_hammer - total_commission - total_fixed_charges` |
| `action_confirm_payment()` | — | `draft` → `payment_confirmed` |
| `action_send_by_email()` | Opens wizard | `payment_confirmed` → `sent`; sets `default_template_id` to `mail_template_sor_vendor_settlement`; safe to call again from `sent` (resend, no-op on state) |
| `action_cancel()` | — | `draft` → `cancelled`; button labelled **Void** with `confirm=`; irreversible from UI |
| `action_bulk_send()` | Returns `display_notification` | List action; filters to `payment_confirmed`; mass-mail via `mail_bulk_send_utils.bulk_send_via_template()`; chatter on skip; not-eligible count for non-`payment_confirmed` selections (BUG-04); renamed from `action_bulk_mark_sent()` |

Inherits `mail.thread`, `mail.activity.mixin`. `_check_company_auto = True`.

### Extensions to sor.lot (`models/sor_lot_auction_docs.py`, `models/sor_lot_pre_sale.py`)

| Field | Type | Notes |
|-------|------|-------|
| `consignor_id` | Many2one `res.partner` | Optional; `check_company=True`; `readonly="state not in ('draft', 'catalogued')"` in view |
| `vat_margin_scheme` | Boolean | Defaults from `company.vat_margin_scheme`. The leftover `column_name='hammer_price_vat_included'` kwarg from a prior rename (Sprint D5) — never valid on `fields.Boolean` in Odoo 19, silently ignored, logged an `unknown parameter` warning on every startup — was removed in Auction MVP Refinements Story 02. No behavioural change: the DB column was always actually named `vat_margin_scheme`. |
| `pre_sale_advice_id` | Many2one `sor.pre.sale.advice` | Back-reference; `copy=False` |
| `post_sale_advice_id` | Many2one `sor.post.sale.advice` | Back-reference; `copy=False` |
| `vendor_settlement_id` | Many2one `sor.vendor.settlement` | Back-reference; `copy=False` |

### Extensions to sor.event (`models/sor_event_auction_docs.py`)

Adds `pre_sale_advice_count`, `post_sale_advice_count`, `vendor_settlement_count` (computed `store=False`); all six action methods; three `action_view_*` smart button methods.

### Extensions to res.company (`models/res_company.py`)

Adds `psa_content_top`, `psa_content_bottom`, `posa_content_top`, `posa_content_bottom`, `vss_content_top`, `vss_content_bottom` (all Html). `create()` override provisions `sor.vendor.settlement` sequence for new companies. Does **not** add a shared-footer field — see "Content-block scheme" under Architecture Decisions above for why `report_footer` (native, defined in Odoo core) is used instead.

### Extensions to res.config.settings (`models/res_config_settings.py`)

Related fields surfacing the six content-block fields plus `vat_margin_scheme` and `auction_vat_notice` (both defined in `sor_commercial_auction_house`). No related field for shared footer content — that's native `report_footer`, already exposed by Odoo core's own settings, not re-declared here.

---

## Views

### `views/sor_lot_auction_docs_views.xml`

- **Form view** — inherits `sor_lotting.sor_lot_view_form`. XPath: `//field[@name='company_id'][@groups='base.group_multi_company']` (structural selector; `string` selectors rejected in Odoo 19). Inserts `consignor_id` and `vat_margin_scheme`.
- **List view** — inherits `sor_lotting.sor_lot_view_list`. Adds `consignor_id` as `optional="hide"` after `reserve_price`.

### `views/sor_event_auction_docs_views.xml`

Inherits `sor_events.sor_event_view_form`. Inserts `is_commercial` as invisible declaration field (required by Odoo 19 FormArchParser) and four action buttons (Pre-Sale Advice generate, Post-Sale generate, Vendor Settlements generate — plus the smart-button count views). The event-level "Send All Pre-Sale/Post-Sale Advices" batch methods and the hidden "Send Post-Sale Advices" button that used to live here were **deleted** in the Auction Documents and Invoice Email Behaviour sprint — unreachable dead code, superseded entirely by the list-level bulk-send Actions-menu mechanism (see `sor_pre_sale_advice_views.xml`/`sor_post_sale_advice_views.xml` below).

### `views/sor_pre_sale_advice_views.xml`

List view, form view (with Lots notebook page), window action, smart button inheritance on `sor.event`. The list's bulk-send `ir.actions.server` record (`action_server_bulk_send_pre_sale_advice`) must assign its `code` field's result to a variable literally named `action` (`action = records.action_bulk_send()`) — a bare expression statement silently discards the returned notification (see Architecture Decisions above). Form header has two `action_send_by_email` buttons sharing the same `name=` (purple `invisible="state != 'draft'"`; grey `invisible="state != 'sent'"`) rather than one button with a dynamic class — Odoo form buttons do not support state-bound `class=` expressions.

### `views/sor_post_sale_advice_views.xml`

Same pattern as PSA, including the two-button colour-toggle and the `action =` assignment requirement on its bulk-send server action. No longer contains a second `sor.event` form view inheritance for a "Send Post-Sale Advices" batch button — that view record was deleted along with the dead event-level method it called (see `sor_event_auction_docs_views.xml` above); its removal required a `pre-migrate.py` script since the stale DB view record failed combined-arch validation before the data file could reload it (see Migrations below).

### `views/sor_vendor_settlement_views.xml`

List view with state badge widget, form view with statusbar + lifecycle buttons + Lots/Totals notebook (Totals tab shows `total_hammer`, `total_commission`, `total_fixed_charges`, `net_proceeds` in that order), window action, bulk-send server action (`ir.actions.server` with `binding_model_id` and `binding_view_types = 'list'` — same `action = records.action_bulk_send()` assignment requirement as PSA/POSA), smart button inheritance on `sor.event`. Form header has two `action_send_by_email` buttons: purple `invisible="state != 'payment_confirmed'"`, grey `invisible="state != 'sent'"` — both absent in `draft`/`cancelled`.

### `views/res_config_settings_views.xml`

Four `<block>` elements (not `<app>`) inserted at the same xpath anchor (after `sor_fee_schedules_container`), all `invisible="business_model != 'auction_house'"`, in display order:
1. `sor_auction_documents_container` ("Auction Documents: Margin Scheme") — `vat_margin_scheme`, `auction_vat_notice`, both `<setting class="col-lg-12">` (full width)
2. `sor_psa_content_container` ("Auction Documents: Pre-Sale Advice Content") — Top, Bottom
3. `sor_posa_content_container` ("Auction Documents: Post-Sale Advice Content") — Top, Bottom
4. `sor_vss_content_container` ("Auction Documents: Vendor Settlement Content") — Top, Bottom

Restructured from a single flat block during Show & Tell (BUG-S05) — the PO found six same-block fields differentiated only by their own `string=` labels hard to scan, and separately requested block #1 be reordered to appear first (below Business Model/Fee Schedules, above the three per-document blocks). Splitting into multiple titled `<block>` elements matches the native Odoo settings pattern (see `base_setup`'s Users/Languages/Companies/Contacts blocks) — a `<block title="...">` renders as a bold section header, which a shared block with per-field labels cannot replicate.

Block titles renamed to the "Auction Documents: ..." prefix at UAT (BUG-U01) so all four read as a related group. `vat_margin_scheme` and `auction_vat_notice` given `col-lg-12` and `auction_vat_notice` converted from `Text` to `Html` at UAT (BUG-U02) — the field previously had no full-width class, so it inherited the settings app's default 50%-width two-column grid, and as a `Text` field it rendered as a plain textarea rather than a rich-text editor. A `post-migrate.py` (module bumped to `19.0.1.5.0`) converts pre-existing `\n` line breaks to `<br/>` so content entered before the type change keeps its formatting. **Gotcha confirmed during this fix:** a Python field-type change requires a full server restart (`docker compose restart odoo`, or `docker restart <container>` if compose's restart silently no-ops) in addition to the `-u` module upgrade — the upgrade alone updates `ir_model_fields` in the database correctly, but the live, already-running server process keeps serving the old field type to the browser until restarted. See `docker_dev_workflow.md` for the full write-up.

---

## Module File Structure

```
sor_auction_documents/
├── __manifest__.py                     — dependencies; post_init_hook
├── __init__.py                         — imports models and post_init_hook
├── hooks.py                            — post_init_hook; _ensure_vss_sequence; res.company.create override
├── models/
│   ├── __init__.py
│   ├── sor_lot_auction_docs.py         — consignor_id, vat_margin_scheme on sor.lot
│   ├── sor_lot_pre_sale.py             — pre_sale_advice_id, post_sale_advice_id, vendor_settlement_id on sor.lot
│   ├── sor_pre_sale_advice.py          — sor.pre.sale.advice model + individual/bulk template-based email send
│   ├── sor_post_sale_advice.py         — sor.post.sale.advice model + individual/bulk template-based email send
│   ├── sor_vendor_settlement.py        — sor.vendor.settlement model + lifecycle + template-based individual/bulk send + Fixed Charges deduction
│   ├── sor_event_auction_docs.py       — batch generation + smart button methods on sor.event (event-level "Send All" methods deleted this sprint)
│   ├── mail_bulk_send_utils.py         — shared plain-function helper: bulk_send_via_template(), bulk_send_notification()
│   ├── res_company.py                  — psa/posa/vss_content_top/bottom (six Html fields; no shared-footer field)
│   └── res_config_settings.py         — related fields surfacing the six content-block fields
├── report/
│   ├── sor_pre_sale_advice_report.xml  — ir.actions.report record + QWeb template; Top/Bottom content render points
│   ├── sor_post_sale_advice_report.xml — ir.actions.report record + QWeb template (margin scheme branching); Top/Bottom content render points
│   └── sor_vendor_settlement_report.xml — ir.actions.report record + QWeb template (commission + Fixed Charges calc; totals; Top/Bottom content render points)
├── migrations/
│   ├── 19.0.1.1.0/pre-migrate.py       — deletes stale view records referencing a removed field before data files reload (Odoo 19 view-validator catch-22 pattern)
│   ├── 19.0.1.2.0/post-migrate.py      — carries auction_sale_terms/auction_bank_details into the new content-block fields; auction_licence_ref/auction_director_signature into native report_footer
│   └── 19.0.1.3.0/pre-migrate.py       — deletes the stale "Send Post-Sale Advices" hidden-button view record before data files reload (same catch-22 pattern as 19.0.1.1.0)
├── data/
│   ├── sor_vendor_settlement_sequence.xml — ir.sequence for main_company; noupdate=1
│   └── mail_template_data.xml          — three mail.template records (PSA/POSA/VSS), noupdate=1
├── security/
│   ├── ir.model.access.csv             — access rules for three new models
│   └── sor_auction_documents_rules.xml — multi-company ir.rule for sor.vendor.settlement
├── views/
│   ├── menu_views.xml                  — Auction House Documents menu grouping (PSA/POSA/VSS)
│   ├── sor_lot_auction_docs_views.xml
│   ├── sor_event_auction_docs_views.xml
│   ├── sor_pre_sale_advice_views.xml
│   ├── sor_post_sale_advice_views.xml
│   ├── sor_vendor_settlement_views.xml — includes bulk-send server action; Totals tab with Fixed Charges
│   └── res_config_settings_views.xml   — four titled Settings blocks (Auction Documents, PSA/POSA/VSS Content)
├── static/src/css/
│   └── sor_auction_documents.css       — PDF table styling
├── i18n/
│   └── sor_auction_documents.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_auction_documents.py   — 78 tests; TransactionCase; setUpClass
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/sor_vendor_settlement.py` | Four-state lifecycle; computed totals incl. Fixed Charges deduction; bulk-send list action |
| `models/sor_event_auction_docs.py` | All batch generation logic; idempotency; state gate enforcement |
| `report/sor_vendor_settlement_report.xml` | Commission + Fixed Charges calculation in QWeb; margin scheme branching; content-block render points; totals row |
| `hooks.py` | Per-company VSS sequence provisioning — must use `sudo()` |
| `views/sor_vendor_settlement_views.xml` | Bulk-send server action binding; badge widget on state; Totals tab field order |
| `views/res_config_settings_views.xml` | Four titled Settings blocks; the anchor/gating both bridge modules and future stories must preserve |
| `migrations/19.0.1.2.0/post-migrate.py` | One-time content-preserving migration; the reference pattern for reading removed-field values via raw SQL before a schema change |
| `data/mail_template_data.xml` | Three `mail.template` records driving both individual and bulk send for all three document types; `use_default_to eval="False"` on all three is load-bearing — see Architecture Decisions |
| `models/mail_bulk_send_utils.py` | Shared mass-mail + partial-success + chatter helper used by all three models' `action_bulk_send()` |

---

## Composability Boundary

| Installation | Lot form | Event form | Document generation |
|---|---|---|---|
| `sor_auction_documents` alone | `consignor_id` editable Draft/Catalogued; `vat_margin_scheme` visible | Pre-Sale/Post-Sale/VSS buttons visible (commercial events only) | Staff set consignor manually; batch generates documents |
| + `sor_consignment_auction` | `consignor_id` read-only; Fetch Consignor / Refresh buttons present | Document buttons unchanged | Consignor auto-populated from intake picking before document creation |

**Buyer Invoice footer exposure (not a bridge — a shared native field):** Once an administrator sets `company.report_footer` via Settings → Companies → Configure Document Layout, that content renders on Buyer Invoice PDFs too, alongside the three documents this module owns — `report_footer` is company-global in Odoo core, not scoped by any `sor_*` module. This is a deliberate trade-off (see Architecture Decisions), not a composability gap to fix.

---

## Special Concerns

### Manifest data load order — reports before views

View XML that references a report action via `%(action_report_xxx)d` interpolation (e.g. Print buttons) requires the report XML to load before the view XML. The manifest lists `report/` before `views/`. Placing `views/` first causes a `ParseError` at install time (forward reference to an unresolved XML ID).

### is_commercial arch declaration required in Odoo 19

The event form buttons use `invisible="not is_commercial"`. Odoo 19's `FormArchParser` resolves field types from the combined arch at parse time. `is_commercial` must be declared as `<field name="is_commercial" invisible="1"/>` in the same XPath insertion, or the parser raises `Cannot read properties of undefined (reading 'type')`.

### VSS sequence requires sudo() in hooks

`post_init_hook` and `res.company.create` override must call `sudo()` on the `ir.sequence` recordset before creating sequences. Companies being processed may not be in the current user's `allowed_company_ids` — without `sudo()`, `_check_company_auto` rejects the create.

### _render_qweb_pdf integer ID pattern

Use `report._render_qweb_pdf(report.id, [record.id])` — not `report._render_qweb_pdf(report, [record.id])` and not `report._render_qweb_pdf([record.id])`. The account module's `_pre_render_qweb_pdf` override calls `_get_report(report_ref)` which uses `env.ref()` as a final fallback. Passing a list raises `TypeError: unhashable type: 'list'`. Passing the record object did not trigger the `isinstance(models.Model)` branch reliably. The integer ID path is unconditional and safe.

### ORM cache and server restart after raw SQL changes

Odoo's ORM caches `ir.config_parameter` and company field values at startup. Raw SQL changes (e.g. setting `report.url` or `company_details` via `psql`) are not visible to the running server until it is restarted. Always run `docker compose restart odoo` after any raw SQL changes to these tables.

### Field removal requires both a module upgrade AND a server restart

Removing a field from a model (as this sprint did with `auction_document_footer`) drops the underlying DB column on the next `-u` upgrade. If the persistent Odoo server process serving the browser session is not also restarted afterward, it continues running with the old Python model class (still declaring the removed field) against a DB schema that no longer has the column — producing `psycopg2.errors.UndefinedColumn` on any request that touches that model (e.g. rendering the company logo in `web.frontend_layout`, which reads several `res.company` fields at once). This is the standard "Python change → restart" rule from `docker_dev_workflow.md`, but it is easy to forget specifically for field *removals*, since the one-off `-u` upgrade process appears to succeed with no errors — the mismatch only surfaces on the next live HTTP request.

### 7 independent Odoo layout templates — no single hook point for "the real page footer"

Odoo ships 7 page-layout variants a company can select (`web.external_layout_standard`, `_boxed`, `_bold`, `_folder`, `_wave`, `_bubble`, `_striped`), each defining its own footer `<div>` markup independently — there is no shared template all 7 inherit from that could be XPath-extended once. This is why the shared-footer content in this module uses Odoo's native `company.report_footer` (already wired into all 7 variants) rather than a custom SOR field: building the equivalent from scratch would mean maintaining XPath inheritance against all 7 templates, keyed to each one's specific footer markup.

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

Expected: 0 failed, 0 errors of 78 tests (plus cumulative totals for all loaded modules).

---

## Story Reference

- Story 01: `.backlog/previous/Track A/19 Auction House Documents/stories/01_Pre-Sale-Advice.md`
- Story 02: `.backlog/previous/Track A/19 Auction House Documents/stories/02_Post-Sale-Advice.md`
- Story 03: `.backlog/previous/Track A/19 Auction House Documents/stories/03_Vendor-Settlement-Statement.md`
- Auction Refinements 01, Story 03: `.backlog/current/Auction Refinements 01/stories/03_Fixed-Charges-And-VSS-Deduction.md` (Fixed Charges deduction)
- Auction Refinements 01, Story 04: `.backlog/current/Auction Refinements 01/stories/04_Payment-Method-Line-Provisioning.md` (VAT notice help text fix only)
- Auction Refinements 01, Story 05: `.backlog/current/Auction Refinements 01/stories/05_Auction-Document-Content-Blocks.md` (content-block scheme; see BUG-S05 and BUG-S05-2 in that story's bugs folder for the settings-grouping and native-footer decisions)
- Auction MVP Refinements Story 02 — Remove Dead Column Name Kwarg: `.backlog/current/Auction MVP Refinements/stories/02_Remove-Dead-Column-Name-Kwarg.md`
- Auction Documents and Invoice Email Behaviour, Story 01 — Mail Template Parity: `.backlog/current/Auction Documents and Invoice Email Behaviour/stories/01_Mail-Template-Parity.md`
- Auction Documents and Invoice Email Behaviour, Story 02 — PSA/POSA Bulk Send Rewrite: `.backlog/current/Auction Documents and Invoice Email Behaviour/stories/02_PSA-POSA-Bulk-Send-Rewrite.md`
- Auction Documents and Invoice Email Behaviour, Story 03 — VSS and Buyer Invoice Bulk Send Rewrite: `.backlog/current/Auction Documents and Invoice Email Behaviour/stories/03_VSS-and-Buyer-Invoice-Bulk-Send-Rewrite.md`
- Auction Documents and Invoice Email Behaviour, Story 04 — Resend Capability: `.backlog/current/Auction Documents and Invoice Email Behaviour/stories/04_Resend-Capability.md`
