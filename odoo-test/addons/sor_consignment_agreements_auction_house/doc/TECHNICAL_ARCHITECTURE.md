# SOR Consignment Agreements × Auction House — Technical Architecture

## 1. Overview

`sor_consignment_agreements_auction_house` is a purely additive bridge. It adds four fields to `sor.agreement` and an Auction Terms PDF section. No lifecycle logic is modified.

```
sor_consignment_agreements ─────┐
                                 ├─ sor_consignment_agreements_auction_house
sor_commercial_auction_house ────┘
```

---

## 2. Module pattern

```python
'depends': ['sor_consignment_agreements', 'sor_commercial_auction_house'],
'auto_install': True,
'application': False,
'category': 'Hidden/Technical',
```

No hooks. No sequences. No provisioning.

---

## 3. Architecture decisions

**`currency_id` added by the bridge:** Neither `sor_legal_agreement` nor `sor_consignment_agreements` add a `currency_id` field to `sor.agreement`. The bridge adds it as a `related='company_id.currency_id'` Many2one, `store=False`, so the four Monetary fields have a valid `currency_field`. It is declared `invisible="1"` in the form view.

**Auction Terms page only visible for `consignment_in`:** The form view page carries `invisible="agreement_type != 'consignment_in'"`. Auction consignments are always Consignment In — the vendor consigns the artwork to the house. The page does not appear on Consignment Out agreements.

**`vendor_commission_amount` is 0.0 at MVP:** The computed field always returns 0.0. Full computation requires linking the agreement to a sold lot and reading `hammer_price` — D2 scope. The field is not rendered in the PDF at MVP.

**PDF section guard:** The Auction Terms section in the PDF is wrapped in `t-if="doc.agreement_type == 'consignment_in' and (doc.catalogue_estimate or doc.reserve_price or doc.vendor_commission_pct)"`. If none of the three user-editable fields have values, the section is omitted entirely (AC 9). Individual rows have their own `t-if` guards so rows with zero values are skipped.

---

## 4. Models

### `sor.agreement` (extended)

| Field | Type | Details |
|-------|------|---------|
| `currency_id` | Many2one → `res.currency` | `related='company_id.currency_id'`, `store=False` |
| `catalogue_estimate` | Monetary | `currency_field='currency_id'` |
| `reserve_price` | Monetary | `currency_field='currency_id'` |
| `vendor_commission_pct` | Float | `digits=(5, 2)` |
| `vendor_commission_amount` | Monetary (computed) | `store=False`; `@api.depends('vendor_commission_pct')`; always 0.0 at MVP |

---

## 5. Views

| File | Description |
|------|------------|
| `views/sor_agreement_views.xml` | Inherits `sor_consignment_agreements` form view; adds "Auction Terms" notebook page via `position="inside"` on `//notebook`; declares `currency_id` invisible; `readonly` on terminal states `revoked` / `closed` |
| `report/sor_agreement_report_bridge.xml` | Inherits `sor_consignment_agreements.report_sor_agreement_consignment`; XPath anchor `//h3[normalize-space()='Terms and Conditions']` position="before"; conditional table with `t-if` row guards |

---

## 6. Module file structure

```
sor_consignment_agreements_auction_house/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── sor_agreement.py           # four auction fields + _compute_vendor_commission_amount
├── views/
│   └── sor_agreement_views.xml    # Auction Terms notebook page
├── report/
│   └── sor_agreement_report_bridge.xml  # Auction Terms PDF section
├── security/
│   └── ir.model.access.csv
├── i18n/
│   └── sor_consignment_agreements_auction_house.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_consignment_agreements_auction_house.py
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## 7. Critical files

| File | Purpose |
|------|---------|
| `models/sor_agreement.py` | All four field definitions; `_compute_vendor_commission_amount` marked as MVP stub |
| `report/sor_agreement_report_bridge.xml` | PDF section — XPath anchor targets `//h3[normalize-space()='Terms and Conditions']`; do not change without reading parent template first |

---

## 8. Composability boundary

| Installation | Behaviour |
|-------------|-----------|
| `sor_consignment_agreements` alone | Standard consignment agreement form; no Auction Terms page |
| `sor_commercial_auction_house` alone | Commercial fee features; no Auction Terms on agreements (bridge absent) |
| Both installed | Bridge auto-installs; Auction Terms page appears on `consignment_in` agreements; PDF section rendered |

---

## 9. Special concerns

**`auto_install` with pre-existing parents:** If both parents were already installed before this bridge was introduced, use `-i sor_consignment_agreements_auction_house` explicitly. Auto-install only triggers at install time of the last parent.

**`vendor_commission_amount` D2 scope:** When lot-linking is implemented, `_compute_vendor_commission_amount` will need to depend on the lot's `hammer_price`. At that point, ensure the field remains `store=False` — a stored computed field reading lot data would go stale when hammer price changes.

---

## 10. Running the tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_consignment_agreements_auction_house
```

---

## 11. Story reference

Story 04 — `sor_consignment_agreements_auction_house`: `.backlog/current/Auction House Invoice/stories/04_Consignment-Agreements-Auction-House-Bridge.md`
