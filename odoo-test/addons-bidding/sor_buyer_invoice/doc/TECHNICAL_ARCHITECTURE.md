# SOR Buyer Invoice — Technical Architecture

## 1. Overview

`sor_buyer_invoice` is the event-invoice link layer. It adds `sor_event_id` to `account.move`, exposes an invoice count stat button on `sor.event`, restricts the "Payments" smart button to a no-create view once 2+ payments exist, and renders a fully bespoke, standalone invoice PDF (title logic, generic fallback line-items table, payment-status block, regulatory footer). It owns no invoice generation logic — that is bridge scope.

```
sor_accounting ─────┐
                     ├─ sor_buyer_invoice
sor_events ──────────┘
                              │
                              └─ sor_buyer_invoice_auction_house (bridge)
```

---

## 2. Module pattern

```python
'depends': ['sor_accounting', 'sor_events'],
'auto_install': False,
'application': False,
'category': 'Hidden/Technical',
```

No hooks. No sequences. No company-scoped records.

---

## 3. Architecture decisions

**`sor_event_id` as a plain Many2one (not required):** The field is nullable so that standard Odoo invoices created outside the auction context can exist alongside event-linked invoices in the same database. The regulatory PDF footer is conditionally rendered only when `sor_event_id` is set.

**Composability boundary — no generate action in base module:** Invoice generation logic (lot fields, buyer's premium, journal selection, sequencing) is in `sor_buyer_invoice_auction_house`. The base module intentionally contains only the link field and the PDF footer anchor, so a future gallery invoice bridge can depend on `sor_buyer_invoice` without inheriting any auction-specific behaviour.

**`sor_auction_footer` anchor in PDF:** The div `name="sor_auction_footer"` in the base PDF template provides a stable XPath anchor for bridge modules to insert content before the regulatory footer. Bridge modules use `position="before"` at this anchor.

**Fully standalone PDF template, not inherit-and-patch (Auction MVP Refinements Story 03):** `report_invoice_document_sor_buyer_invoice` has no `inherit_id` — it does not extend `account.report_invoice_document`. The previous design inherited the native template and then suppressed most of its own behaviour (title, native line table, native totals) via XPath, which was fragile since nearly everything inherited was being overridden away anyway. The rebuild follows the same `web.html_container` → `web.external_layout` pattern already proven by `sor_auction_documents`'s PSA/POSA/VSS templates. Dispatch to this template happens via `_get_name_invoice_report()` + a `t-elif` extension on the `account.report_invoice` dispatcher template — Odoo's own documented extension point (see `l10n_ar` for a native example of the identical pattern). This is a pure additive `t-elif`; the native branch and every other localization's branch are untouched.

**`sor_invoice_line_table` as the bridge replacement point:** The base template's generic fallback line-items table lives in a `<div name="sor_invoice_line_table">`. `sor_buyer_invoice_auction_house` replaces this div wholesale (`position="replace"`) with its lot breakdown table. The fallback table exists only to cover the Group 1 standalone composability case — in the real deVeres deployment the bridge is always installed, so the fallback never renders in production.

**`sor_invoice_payment_status` as a sibling, not nested, anchor (BUG-01):** The payment-status block (Paid on / Amount Due, mirroring native Odoo's own `print_with_payments` logic) is a sibling `<div>` immediately after `sor_invoice_line_table`, not nested inside it. This is deliberate: a bridge's `position="replace"` on `sor_invoice_line_table` only touches that div — content placed as a sibling survives untouched regardless of which downstream bridge is installed. Placing new content inside `sor_invoice_line_table` would have it silently deleted whenever a bridge replaces that div.

**`open_payments()` override (Story 01):** `account.move.open_payments()` (native) returns a dynamically-built action dict — there is no static `ir.actions.act_window` XML record to patch. The override substitutes the dedicated no-create view (`sor_buyer_invoice.view_account_payment_list_no_create`) only for the `'list'` entry in `action['views']`; the `'form'` entry is untouched so existing payment records remain fully readable/editable/reconcilable. The dedicated view itself follows the same pattern as Odoo core's own `account.view_account_supplier_payment_tree` — `mode='primary'` as a field value (not a record attribute) plus a positional XPath patch, producing an independent, standalone view derived from the native arch.

---

## 4. Models

### `account.move` (extended)

| Field / Method | Type | Details |
|-------|------|---------|
| `sor_event_id` | Many2one → `sor.event` | `ondelete='set null'`, `index=True` |
| `partner_ref` | Char (related) | `related='partner_id.ref'`, `store=False` |
| `open_payments()` | Method | Overrides native; substitutes no-create list view once 2+ payments |
| `_get_name_invoice_report()` | Method | Report-dispatch override; returns SOR template name when `sor_event_id` set |

### `sor.event` (extended)

| Field / Method | Type | Details |
|----------------|------|---------|
| `invoice_count` | Integer (computed) | `store=False`; `@api.depends()` empty tuple |
| `action_view_buyer_invoices()` | Method | Returns `act_window` domain-filtered to `sor_event_id = self.id` |

### `res.company` (extended)

| Field | Type | Details |
|-------|------|---------|
| `auction_psra_number` | Char | PSRA Licence Number for regulatory footer |

---

## 5. Views

| File | Description |
|------|------------|
| `views/sor_event_views.xml` | Adds "Buyer Invoices" stat button to `sor.event` form; uses `type="object"` → `action_view_buyer_invoices` |
| `views/account_move_views.xml` | Adds `sor_event_id` field to `account.move` form; adds `partner_ref` column to invoice list; also declares `view_account_payment_list_no_create` — a standalone `account.payment` list view (`mode='primary'` + `create="0"` XPath patch), derived from `account.view_account_payment_tree` |
| `report/account_invoice_report.xml` | Fully standalone template (no `inherit_id`) — title logic, customer block, generic fallback line table (`sor_invoice_line_table`), payment-status block (`sor_invoice_payment_status`), regulatory footer (`sor_auction_footer`); plus the `report_invoice` dispatcher extension |

---

## 6. Module file structure

```
sor_buyer_invoice/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── account_move.py        # sor_event_id, partner_ref fields
│   ├── res_company.py         # auction_psra_number field
│   └── sor_event.py           # invoice_count, action_view_buyer_invoices
├── views/
│   ├── sor_event_views.xml    # smart button
│   └── account_move_views.xml # event field, customer code column, no-create payments view
├── report/
│   └── account_invoice_report.xml  # standalone PDF template + report_invoice dispatch extension
├── security/
│   └── ir.model.access.csv
├── migrations/
│   └── 19.0.1.1.0/
│       └── pre-migrate.py     # deletes stale view + descendants before the inherit_id→standalone rebuild
├── i18n/
│   └── sor_buyer_invoice.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_buyer_invoice.py
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## 7. Critical files

| File | Purpose |
|------|---------|
| `report/account_invoice_report.xml` | Defines `sor_invoice_line_table` (bridge replacement point), `sor_invoice_payment_status`, and `sor_auction_footer` — do not rename any of these divs; bridge modules depend on them |
| `models/account_move.py` | `open_payments()` override and `_get_name_invoice_report()` report-dispatch extension point |
| `models/sor_event.py` | `action_view_buyer_invoices` extension point used by the smart button |
| `views/account_move_views.xml` | `view_account_payment_list_no_create` xmlid — referenced directly by `open_payments()` |

---

## 8. Composability boundary

| Installation | Behaviour |
|-------------|-----------|
| `sor_buyer_invoice` alone | Event field on invoice; smart button on event; no-create Payments restriction; standalone PDF with generic fallback table, payment status, and regulatory footer; no generate button; no lot breakdown |
| + `sor_buyer_invoice_auction_house` | Adds AUC journal, generate button, lot fields, lot breakdown PDF (replacing the fallback table), buyer's premium, VAT margin scheme columns/notice |

---

## 9. Special concerns

**`@api.depends()` empty tuple on `invoice_count`:** In Odoo 19, `@api.depends('id')` raises `NotImplementedError`. An empty `@api.depends()` means the field is always recomputed on access — correct for a `store=False` aggregate count.

**Redefining a template from `inherit_id` to standalone requires a pre-migrate (Story 03):** Changing `report_invoice_document_sor_buyer_invoice` from an `account.report_invoice_document`-inheriting view to a fully standalone one (same xmlid) is not a clean in-place upgrade — the existing DB view record still carries the stale `inherit_id`, so Odoo tries to locate the new standalone content inside the *old* parent's arch and raises `ParseError`. Fixed with `migrations/19.0.1.1.0/pre-migrate.py`, which deletes the stale view and its descendants before data files reload — the same class of problem (and same fix pattern) documented in `odoo_conventions/odoo_19_breaking_changes.md` for renamed-field view staleness, just triggered by an `inherit_id` change rather than a field rename.

**`docker compose restart` changing `StartedAt` is not always sufficient proof of a full restart for QWeb template changes:** discovered during this same story's Show & Tell — see `docker_dev_workflow.md`. A `docker compose restart odoo` that changed `StartedAt` still left the browser-facing worker serving a stale, pre-rebuild template; only a forceful `docker restart odoo-app` picked up the fix. When a report/view fix doesn't appear in the browser after a soft restart, verify the underlying content via a fresh shell process first before assuming the fix itself is wrong.

---

## 10. Running the tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_buyer_invoice
```

---

## 11. Story reference

Story 02 — `sor_buyer_invoice`: `.backlog/previous/` (Auction House Invoice — see the archived sprint for the original base module delivery)

Auction MVP Refinements:
- Story 01 — Restrict Payments List Create: `.backlog/current/Auction MVP Refinements/stories/01_Restrict-Payments-List-Create.md`
- Story 03 — Bespoke Buyer Invoice PDF: `.backlog/current/Auction MVP Refinements/stories/03_Bespoke-Buyer-Invoice-PDF.md`
