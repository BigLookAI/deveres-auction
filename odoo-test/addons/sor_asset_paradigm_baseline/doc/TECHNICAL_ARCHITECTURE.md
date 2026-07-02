# Technical Architecture — sor_asset_paradigm_baseline

## Overview

`sor_asset_paradigm_baseline` is a single-parent companion module to `sor_asset_paradigm`. It registers the `standard` paradigm value and creates a persistent archived developer reference product (the "Baseline Product") that carries `standard` paradigm with zero suppression rules — exposing the full OOTB Odoo inventory UI. The module is hidden, non-application, and auto-installs whenever `sor_asset_paradigm` is installed.

```
sor_asset_paradigm
       |
sor_asset_paradigm_baseline   ← auto_install companion
```

---

## Module Pattern

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `True` | Should always be present when `sor_asset_paradigm` is installed; the developer reference is meaningless without the mechanism it demonstrates |
| `application` | `False` | Technical companion; not a standalone app |
| `category` | `'Hidden/Technical'` | Excluded from business app listings; surfaced only in developer mode |
| `depends` | `['sor_asset_paradigm']` | Single dependency — this module is a companion, not a bridge across two independent modules |
| `post_init_hook` | `'post_init_hook'` | Creates the Baseline Product via ORM with `with_context(default_product_type=False)` (see Architecture Decisions) |

Note: `auto_install: True` with a single dependency means this module installs automatically whenever `sor_asset_paradigm` is installed, with no second parent required. This is atypical for bridge modules but correct here — the baseline is always relevant when the paradigm mechanism is present.

---

## Architecture Decisions

### ORM create with `with_context(default_product_type=False)`

The Baseline Product is created in `post_init_hook` using the Odoo ORM (`env['product.template'].sudo().with_context(default_product_type=False).create({...})`), not raw SQL.

**Why `with_context(default_product_type=False)`:** When `sor_artwork` is installed alongside this module, `sor_artwork`'s `default_get` override stamps `product_type='artwork'` on every ORM `create()` call unless the context explicitly overrides it. This would trigger `sor_artwork`'s `_check_creator_required` constraint (creator is required for artworks), causing a `ValidationError` because the Baseline Product create call does not supply a `creator_id`.

Passing `with_context(default_product_type=False)` prevents `default_get` from stamping `'artwork'`. The Baseline Product's `product_type` column is left at its DB default — `None` — because `sor_artwork` is not the owner of the column and may not even be installed. What matters for paradigm suppression is `asset_paradigm='standard'`, not `product_type`.

**Why ORM rather than SQL:** The original implementation used raw `env.cr.execute()` SQL to bypass ORM constraints. The context override approach achieves the same goal (no `product_type` stamped, no creator constraint fired) while using the ORM correctly. This eliminates the maintenance risk of the SQL approach (schema dependency on hardcoded column names) and stays consistent with Odoo patterns.

### `ir.model.data` registration

The Baseline Product is registered in `ir.model.data` via ORM:

```python
env['ir.model.data'].sudo().create({
    'module': 'sor_asset_paradigm_baseline',
    'name': 'baseline_product',
    'model': 'product.template',
    'res_id': product.id,
    'noupdate': True,
})
```

This gives the record an external ID (`sor_asset_paradigm_baseline.baseline_product`) so the view action can reference it via `ref('baseline_product')`. The `noupdate=True` flag ensures the hook's idempotency check (`env['ir.model.data'].search([...])`) prevents duplicate creation on subsequent `--update` runs.

### `standard` paradigm value registered in models layer, not data

The `standard` paradigm value is registered via `selection_add` in `models/product_template.py`, not as an XML data record. This is the correct Odoo pattern: selection values are part of the model definition and must be in Python to participate in ORM validation. Rule records for the `standard` paradigm are intentionally absent — the absence of rules is what makes `standard` a "no suppression" paradigm.

### Baseline Product is archived (`active=False`)

The Baseline Product is deliberately archived so it does not appear in production product lists or affect inventory reports. It is surfaced exclusively through the developer menu action, which passes `context={'active_test': False}`. This prevents the reference product from contaminating operational data while keeping it accessible for debugging.

---

## Models

### `product.template` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `asset_paradigm` | `Selection` (`selection_add=[('standard', 'Standard')]`) | Registers `standard` as a valid paradigm value. No new fields, constraints, or methods added. |

---

## Views

### `action_baseline_product` (`ir.actions.act_window`)

| Property | Value |
|----------|-------|
| Model | `product.template` |
| View mode | `list, form` |
| Domain | `[('asset_paradigm', '=', 'standard')]` |
| Context | `{'active_test': False}` — required to surface the archived record |
| Purpose | Opens the single Baseline Product record in the standard product form; provides the developer reference for full OOTB inventory UI |

### `menu_sor_baseline_product` (`ir.ui.menu`)

| Property | Value |
|----------|-------|
| Parent | `sor_asset_paradigm.menu_sor_technical_root` |
| Groups | `base.group_no_one` — developer mode only |
| Sequence | `20` |
| Action | `action_baseline_product` |

The menu item is hidden from non-developer users via `groups="base.group_no_one"`. It appears as **Settings → Technical → SOR → Baseline Product** when developer mode is active.

---

## Module File Structure

```
sor_asset_paradigm_baseline/
├── __init__.py                        # Empty (no models package import needed)
├── __manifest__.py                    # Module declaration; post_init_hook registered here
├── hooks.py                           # post_init_hook: ORM creation of Baseline Product via with_context(default_product_type=False)
├── models/
│   ├── __init__.py                    # Imports product_template
│   └── product_template.py            # Registers 'standard' via selection_add
├── views/
│   └── baseline_product_views.xml     # Action + developer menu item
├── data/
│   └── baseline_product_data.xml      # Intentionally empty; product created by hook
├── security/
│   └── ir.model.access.csv            # No new models; header row only
├── tests/
│   ├── __init__.py                    # Empty
│   └── test_placeholder.py            # Stub; tests written at Show & Tell
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | Declares `auto_install`, `depends`, and `post_init_hook` |
| `hooks.py` | Creates Baseline Product via ORM with `with_context(default_product_type=False)`; registers external ID; idempotent |
| `models/product_template.py` | Registers `standard` paradigm value via `selection_add` |
| `views/baseline_product_views.xml` | Developer menu and action for the Baseline Product |

---

## Composability Boundary

| Scenario | Result |
|----------|--------|
| `sor_asset_paradigm` installed alone | `sor_asset_paradigm_baseline` auto-installs; `standard` paradigm available; Baseline Product created |
| `sor_artwork` added | No change to this module; Baseline Product already exists (hook is idempotent); artwork bridge adds `unique_object` paradigm independently |
| `sor_asset_paradigm_artwork` added | No interaction; `standard` paradigm unaffected by artwork suppression rules |
| Any future paradigm bridge added | No interaction; `standard` remains a zero-suppression reference |

---

## Special Concerns

### Hook idempotency

The `post_init_hook` checks `ir.model.data` before inserting to prevent duplicate records on module upgrade (`-u sor_asset_paradigm_baseline`). The check is by external ID (`module='sor_asset_paradigm_baseline'`, `name='baseline_product'`), not by product name, so a renamed record would not prevent re-creation. Do not rename or delete the `ir.model.data` row.

### UoM resolution

The hook resolves the default Unit of Measure via `ir.model.data` (`uom.product_uom_unit`). If the UoM module is not installed, it falls back to the first row in `uom_uom`. If no UoM exists at all, the hook exits without creating the product. In practice, `uom` is a core Odoo dependency and will always be present.

### `noupdate=True` on the `ir.model.data` row

The `noupdate=True` flag is set on the `ir_model_data` registration. This means Odoo's `--update` mechanism will not attempt to re-create or modify the product record. Combined with the existence check at hook entry, the hook is fully idempotent.

### `product_type` column is `None` on the Baseline Product

The ORM create does not pass `product_type` in `vals`, and `with_context(default_product_type=False)` prevents `sor_artwork`'s `default_get` from stamping `'artwork'`. The `product_type` column is therefore `NULL` in the database. This is intentional — the Baseline Product is a developer reference artefact, not an artwork. What matters for paradigm suppression is `asset_paradigm='standard'`, not `product_type`. The product is archived (`active=False`) so it never surfaces in artwork lists or inventory reports.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init \
  -u sor_asset_paradigm_baseline
```

Tests for the baseline module are exercised as part of `sor_asset_paradigm`'s test suite (`test_baseline_product_has_standard_paradigm`, `test_baseline_product_is_inactive`, `test_baseline_product_is_not_suppressed`), since both modules are always installed together.

---

## Story Reference

Parent story: [01 Asset Paradigm Foundation](../../../.backlog/00%20Asset%20Paradigm/stories/01_Asset-Paradigm-Foundation.md) — AC7: Baseline Bridge.
