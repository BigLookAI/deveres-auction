# Technical Architecture: sor_lotting_contact_roles

## 1. Overview

Bridge module delivering lot-to-contact-role linkage — the composable intersection of lot cataloguing and contact role management. When both `sor_lotting` and `sor_contact_roles` are installed, the bridge activates automatically and:

- Extends `res.partner` with a consigned lot count (smart button) and inline lot history (notebook tab), both scoped to the active company.
- Extends `sor.lot.create/write` to assign the Consignor earned sub-type to the consignor partner when `consignor_id` is set.
- Retroactively backfills the Consignor sub-type for all partners already set as consignors on existing lots, via `post_init_hook`.

Neither parent module is modified. The bridge is additive only.

```
sor_lotting             sor_contact_roles
      \                       /
       \                     /
  sor_lotting_contact_roles  (auto_install=True, application=False)
```

---

## 2. Module Pattern

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `True` | Bridge activates when both parents are present — no manual install required |
| `application` | `False` | Not a top-level App — hidden from App Store |
| `category` | `'Hidden/Technical'` | Excluded from business category listings |
| `post_init_hook` | registered | Retroactive Consignor sub-type backfill for existing lots at install time |
| `uninstall_hook` | not present | No native Odoo surfaces suppressed; no records to restore on uninstall |

---

## 3. Architecture Decisions

**1. `consigned_lot_count` is `store=False` with empty `@api.depends()`.**
The count must always reflect the live DB state. A `store=True` computed field on `res.partner` would require `sor.lot.consignor_id` changes to trigger recomputation — which is not guaranteed for One2many inverse triggers. The `store=False` + empty depends approach recomputes on every access, which is correct for a stat button count.

**2. `consigned_lot_ids` One2many is for display only.**
The One2many exists solely to power the inline list view in the notebook tab. Do not use it in search domains or filters — use `self.env['sor.lot'].search([('consignor_id','=',partner.id)])` instead, which is reliably ORM-filtered.

**3. Sub-type assignment via `[(4, id)]` command.**
Using the `(4, id)` M2M command links the sub-type without removing other sub-types already on the partner. This preserves staff-assigned roles and other earned sub-types. The `if consignor_subtype not in partner.contact_subtypes` guard makes the call idempotent.

**4. `write()` override only fires on `consignor_id` changes.**
The check `if 'consignor_id' in vals` prevents unnecessary sub-type lookups on every write to `sor.lot`. Only the specific field change triggers the assignment.

**5. `post_init_hook` iterates all lots without company scoping.**
Sub-type assignment is partner-level (global) — a partner's contact sub-types are shared across companies. Scoping the hook query to a specific company would leave other companies' consignors unbackfilled. The hook correctly searches `[('consignor_id','!=',False)]` without a company filter.

**6. Silent skip when sub-type code not found.**
If `sor_contact_roles` demo data is not loaded and no `sor.contact.type` with `code='consignor'` exists, `_assign_consignor_subtype` returns without error. This prevents install failures on blank instances. Tests use `skipTest` to handle this gracefully.

---

## 4. Models

### `res.partner` (inherited)

| Field / Method | Type | Description |
|----------------|------|-------------|
| `consigned_lot_count` | `Integer`, computed, `store=False` | Live count of lots with `consignor_id = self`, filtered to `env.company` |
| `consigned_lot_ids` | `One2many` → `sor.lot` | Inverse of `sor.lot.consignor_id`; used in notebook tab list |
| `_compute_consigned_lot_count()` | method | Computes count via `search_count` |
| `action_view_consigned_lots()` | method | Returns `act_window` filtered to this consignor + company |

### `sor.lot` (inherited)

| Field / Method | Type | Description |
|----------------|------|-------------|
| `_assign_consignor_subtype()` | method | Idempotent Consignor sub-type assignment for all lots in `self` |
| `_assign_buyer_subtype()` | method | Idempotent Buyer sub-type assignment for all lots in `self` where `buyer_id` is set (BUG-U17) |
| `create()` | override | Calls `_assign_consignor_subtype()` and `_assign_buyer_subtype()` after super |
| `write()` | override | Calls `_assign_consignor_subtype()` if `consignor_id` in vals; calls `_assign_buyer_subtype()` if `buyer_id` in vals |

---

## 5. Views

### `view_partner_form_inherit_lotting_contact_roles`

- **Model:** `res.partner`
- **Inherits:** `base.view_partner_form`
- **Mode:** Extension (XPath)

| XPath | Position | Purpose |
|-------|----------|---------|
| `//field[@name='name']` | before | Declares `consigned_lot_count invisible="1"` — required in arch for `invisible=` expressions on button and tab |
| `//div[@name='button_box']` | inside | Adds gavel stat button (`action_view_consigned_lots`, `invisible="not consigned_lot_count"`) |
| `//notebook` | inside | Adds "Consigned Lots" page (`invisible="not consigned_lot_count"`) with inline `consigned_lot_ids` list |

**Inline list columns:** `currency_id` (`column_invisible="1"` — required for the Monetary widget on `hammer_price` to resolve currency, not shown), `lot_reference` (Lot Reference), `lot_number` (Lot No.), `lot_item_name` (Item), `state` (State), `hammer_price` (default-visible, added Auction Refinements 01 Story 2 — this list previously had no `currency_id`/`hammer_price` at all). Corrected from a stale pre-existing entry that listed `lot_title`/`company_id`, neither of which is actually in the current arch.

---

## 6. Module File Structure

```
sor_lotting_contact_roles/
├── __manifest__.py              — bridge manifest: auto_install=True, post_init_hook
├── __init__.py                  — imports models; imports post_init_hook
├── hooks.py                     — post_init_hook: retroactive Consignor sub-type backfill
├── models/
│   ├── __init__.py              — imports res_partner, sor_lot
│   ├── res_partner.py           — consigned_lot_count, consigned_lot_ids, action methods
│   └── sor_lot.py               — _assign_consignor_subtype; create/write overrides
├── views/
│   └── res_partner_views.xml    — partner form: smart button + Consigned Lots tab
├── security/
│   └── ir.model.access.csv      — empty (no new models introduced)
├── demo/
│   └── demo_lot_partners.xml    — demo partners pre-linked as consignors
├── tests/
│   ├── __init__.py
│   └── test_sor_lotting_contact_roles.py — 5 TransactionCase tests
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## 7. Critical Files

| File | Purpose |
|------|---------|
| `hooks.py` | `post_init_hook` — retroactive Consignor sub-type backfill across all existing lots |
| `models/res_partner.py` | `consigned_lot_count` computed field; `action_view_consigned_lots` stat button action |
| `models/sor_lot.py` | `_assign_consignor_subtype`; `create`/`write` overrides for ongoing sub-type assignment |
| `views/res_partner_views.xml` | Smart button + Consigned Lots tab on partner form |

---

## 8. Composability Boundary

| Installation | Features present |
|-------------|-----------------|
| `sor_lotting` only | Lots with `consignor_id` field; no sub-type assignment; no partner stats button |
| `sor_contact_roles` only | Contact roles and sub-types UI; no lot-specific features |
| Both installed (this bridge auto-installs) | Consignor sub-type assigned on lot create/write; smart button on partner form; Consigned Lots notebook tab |
| + `sor_lotting_tracking` | No interaction; tracking bridge operates independently |
| + `sor_commercial_auction_house` | No interaction; `consignor_id` ownership remains with `sor_lotting` |

---

## 9. Special Concerns

**1. `consigned_lot_count` is company-scoped.**
The count is filtered to `self.env.company.id`. A partner who consigns lots across multiple companies will show only the count for the active company in the current session. This is correct multi-company behaviour — staff see their company's lot history.

**2. Consignor sub-type is never removed.**
Once assigned by this bridge, the Consignor sub-type persists on the partner even if they are removed as consignor from all lots. This is the activity-earned pattern (Design Pattern 6): consignor status reflects historical participation, not current assignment.

**3. Sub-type code hardcoded as `'consignor'`.**
`_assign_consignor_subtype` searches for `code='consignor'`. If the `sor_contact_roles` demo data is not loaded (blank install without demo), no sub-type is found and the assignment silently skips. The test `skipTest` guards handle this cleanly.

**4. The `consigned_lot_ids` One2many bypasses the field's domain filter.**
The One2many uses `inverse_name='consignor_id'` with no additional domain. All lots for the partner across all states are included in the notebook tab. This is intentional — consignors should see their full lot history regardless of state.

---

## 10. Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_lotting_contact_roles
```

Seven tests: `test_module_installs`, `test_consigned_lot_count_zero_for_new_partner`, `test_consigned_lot_count_increments_on_lot_create`, `test_consignor_subtype_assigned_on_lot_create`, `test_consignor_subtype_assigned_on_lot_write`, `test_buyer_subtype_assigned_on_lot_create`, `test_buyer_subtype_assigned_on_lot_write`.

---

## 11. Story Reference

Parent story: `.backlog/current/Auction Completions/stories/02_Consignor-Lots-Bridge.md`
