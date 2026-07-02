# SOR Buyer Invoice — Technical Architecture

## 1. Overview

`sor_buyer_invoice` is the event-invoice link layer. It adds `sor_event_id` to `account.move`, exposes an invoice count stat button on `sor.event`, and extends the invoice PDF with a regulatory footer. It owns no invoice generation logic — that is bridge scope.

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

---

## 4. Models

### `account.move` (extended)

| Field | Type | Details |
|-------|------|---------|
| `sor_event_id` | Many2one → `sor.event` | `ondelete='set null'`, `index=True` |
| `partner_ref` | Char (related) | `related='partner_id.ref'`, `store=False` |

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
| `views/account_move_views.xml` | Adds `sor_event_id` field to `account.move` form; adds `partner_ref` column to invoice list |
| `report/account_invoice_report.xml` | Inherits `account.report_invoice_document`; appends `sor_auction_footer` div with bank/PSRA/reg/VAT — only when `o.sor_event_id` is set |

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
│   └── account_move_views.xml # event field, customer code column
├── report/
│   └── account_invoice_report.xml  # regulatory footer
├── security/
│   └── ir.model.access.csv
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
| `report/account_invoice_report.xml` | Defines `sor_auction_footer` anchor — do not rename this div; bridge modules depend on it |
| `models/sor_event.py` | `action_view_buyer_invoices` extension point used by the smart button |

---

## 8. Composability boundary

| Installation | Behaviour |
|-------------|-----------|
| `sor_buyer_invoice` alone | Event field on invoice; smart button on event; regulatory footer on PDF; no generate button; no lot breakdown |
| + `sor_buyer_invoice_auction_house` | Adds AUC journal, generate button, lot fields, lot breakdown PDF, buyer's premium |

---

## 9. Special concerns

**`@api.depends()` empty tuple on `invoice_count`:** In Odoo 19, `@api.depends('id')` raises `NotImplementedError`. An empty `@api.depends()` means the field is always recomputed on access — correct for a `store=False` aggregate count.

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

Story 02 — `sor_buyer_invoice`: `.backlog/current/Auction House Invoice/stories/02_Buyer-Invoice-Base.md`
