# Technical Architecture: sor_tracking_asset_paradigm

## Overview

`sor_tracking_asset_paradigm` is a **bridge module** that connects the physical movement layer (`sor_tracking`) with the asset paradigm system (`sor_asset_paradigm`). It makes the movement form paradigm-aware: when all products in a picking are unique objects, quantity UI is suppressed and automatic quantity defaulting is applied.

```
sor_tracking          sor_asset_paradigm
       \                     /
        \                   /
    sor_tracking_asset_paradigm   (auto_install=True, application=False)
```

Neither parent module is modified. The bridge activates automatically when both parents are installed.

---

## Module Pattern

**Manifest flags:**
```python
'category': 'Hidden/Technical',
'depends': ['sor_tracking', 'sor_asset_paradigm'],
'auto_install': True,
'application': False,
```

- `auto_install: True` — Odoo installs the bridge automatically when both `sor_tracking` and `sor_asset_paradigm` are present.
- `application: False` — Does not appear as a top-level App.
- `category: 'Hidden/Technical'` — Excluded from business category listings.
- No `post_init_hook` — no install-time data setup required; the bridge is purely structural.

**Why a bridge?** `sor_tracking` must work for any asset type — it has no knowledge of paradigms. `sor_asset_paradigm` has no knowledge of movement operations. The intersection behaviour (suppressing qty columns for unique objects in a movement form) belongs exclusively in a bridge.

---

## Architecture Decisions

### `sor_all_unique_objects` on both `stock.picking` and `stock.move`

The suppression logic must be available at two levels:
- `stock.picking` — needed for `column_invisible` expressions on the picking form's lines list (`parent.sor_all_unique_objects` reads from the enclosing picking)
- `stock.move` — needed for `invisible` expressions inside the Detailed Operations dialog, which renders a `stock.move` form where `parent` is `stock.move`, not `stock.picking`

The `stock.move` field is a simple delegation to `picking_id.sor_all_unique_objects`. Duplication is intentional and necessary — Odoo view expressions require the field to exist on the model the form is bound to.

### `store=False` for both fields

`sor_all_unique_objects` is `store=False` on both models. It depends on `move_ids.product_id.asset_paradigm`, a traversal across multiple records. Storing this field would require recomputing it whenever any product's paradigm changes — expensive and rarely needed. The field is cheap to recompute per-read.

### Suppression condition: all lines, not any line

The suppression activates only when **all** moves in the picking are unique objects (`all(...)` not `any(...)`). A mixed picking retains full quantity UI. This prevents confusion when a picking contains both a unique-object artwork and a supply item (e.g. framing materials).

Empty pickings return `False` — suppression does not activate for new pickings before lines are added.

### Quantity defaulting at three layers

The `product_uom_qty = 1` default for unique objects is applied at:
1. `create()` — programmatic creation; handles bulk-create via `vals_list`
2. `@api.onchange` — UI selection; sets both `product_uom_qty` and `quantity` for immediate visual feedback
3. `_action_confirm()` — safety net; catches cases where qty was cleared between create and confirm

The three-layer approach reflects the different code paths through which a `stock.move` can arrive at confirmation. The `create()` layer is the primary one; the others are defensive.

### Inheritance target: `sor_tracking`'s form, not Odoo's base form

The picking view XPath patches inherit `sor_tracking.view_picking_form_sor_tracking`, not Odoo's `stock.view_picking_form`. `sor_tracking` already inherits and extends the base form — inheriting from it ensures the `sor_movement_hint` XPath anchor exists and that the patch is applied in the correct inheritance chain.

---

## Models

### `stock.picking` (extended)

| Field/Method | Type | Depends on | Purpose |
|---|---|---|---|
| `sor_all_unique_objects` | Boolean, computed, store=False | `move_ids.product_id.asset_paradigm` | True when every move has a unique_object product |
| `_compute_sor_all_unique_objects` | Method | — | Iterates moves; filters to those with products; checks paradigm |

### `stock.move` (extended)

| Field/Method | Type | Depends on | Purpose |
|---|---|---|---|
| `sor_all_unique_objects` | Boolean, computed, store=False | `picking_id.sor_all_unique_objects` | Delegates to picking; needed for Detailed Operations dialog expressions |
| `_compute_sor_all_unique_objects_move` | Method | — | Returns picking value or False |
| `create` override | Method | — | Defaults product_uom_qty=1 for unique_object products when omitted |
| `_onchange_product_id_sor_tracking_asset_paradigm` | Onchange | `product_id` | Sets qty=1 in UI when unique_object product is selected |
| `_action_confirm` override | Method | — | Safety net: ensures qty=1 before confirmation |

---

## Views

### `view_picking_form_sor_tracking_asset_paradigm`

- **Model:** `stock.picking`
- **Inherits:** `sor_tracking.view_picking_form_sor_tracking`
- **What it does:**
  1. Declares `sor_all_unique_objects` as `invisible="1"` before `sor_movement_hint` (required for `column_invisible` expression resolution in Odoo 19)
  2. Sets `column_invisible="parent.sor_all_unique_objects"` on `product_uom_qty` (Demand column)
  3. Sets `column_invisible="parent.state == 'draft' or parent.sor_all_unique_objects"` on `quantity` (extends the existing draft-state suppression)
  4. Sets `invisible="1"` on `move_type` (Shipping Policy — not meaningful for artwork movements)

### `view_stock_move_operations_sor_tracking_asset_paradigm`

- **Model:** `stock.move`
- **Inherits:** `stock.view_stock_move_operations`
- **What it does:**
  1. Declares `sor_all_unique_objects` as `invisible="1"` before the `product_qty` group
  2. Sets `invisible="sor_all_unique_objects"` on `group[@name='product_qty']` — hides the Demand group in the Detailed Operations dialog

### `view_stock_move_line_operation_tree_sor_tracking_asset_paradigm`

- **Model:** `stock.move.line`
- **Inherits:** `stock.view_stock_move_line_operation_tree`
- **What it does:** Sets `column_invisible="parent.sor_all_unique_objects"` on the `quantity` column in the Detailed Operations inner list. `parent` here is `stock.move`, which carries `sor_all_unique_objects` via delegation.

---

## Module File Structure

```
sor_tracking_asset_paradigm/
├── __manifest__.py              — Module metadata; no post_init_hook
├── __init__.py                  — Imports models
├── models/
│   ├── __init__.py
│   ├── stock_picking.py         — sor_all_unique_objects computed field on picking
│   └── stock_move.py            — sor_all_unique_objects delegation; create/onchange/confirm overrides
├── views/
│   └── stock_picking_views.xml  — Three view inheritances: picking form, move form, move.line list
├── security/
│   └── ir.model.access.csv      — No new models; minimal CSV
├── i18n/
│   └── sor_tracking_asset_paradigm.pot — Translation template
├── tests/
│   ├── __init__.py
│   ├── test_placeholder.py      — Stub (replaced by test_sor_tracking_asset_paradigm.py)
│   └── test_sor_tracking_asset_paradigm.py — Full test suite
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | `auto_install`, `depends` — no hook |
| `models/stock_picking.py` | `sor_all_unique_objects` on picking |
| `models/stock_move.py` | Delegation field; quantity defaulting logic |
| `views/stock_picking_views.xml` | Three view patches for suppression |
| `tests/test_sor_tracking_asset_paradigm.py` | Full test suite |

---

## Composability Boundary

| Installation state | `sor_all_unique_objects` field | Qty suppression | Qty defaulting |
|-------------------|-------------------------------|-----------------|----------------|
| `sor_tracking` only | No | No | No |
| `sor_asset_paradigm` only | No | No | No |
| Both installed | Yes (always False without unique_object products) | Inactive | Active |
| + `sor_asset_paradigm_artwork` | Yes — artwork products have unique_object paradigm | Active for artwork pickings | Active for artworks |
| + `sor_tracking_artwork` | Serial tracking enabled; qty suppression unchanged | Same | Same |

---

## Special Concerns

### Module load order in `--test-enable` testing

When running `--test-enable -u sor_tracking_asset_paradigm`, this module loads before `sor_artwork` (which is not in its dependency chain). At test-run time:
- `sor_artwork`'s `product_type` NOT NULL column exists in the DB but not in the ORM
- `sor_asset_paradigm_artwork`'s `unique_object` selection value may not be in the registry

Test setup uses **raw SQL** to locate existing `unique_object` products rather than creating them via ORM. `skipTest` guards handle the case where no qualifying products exist in the test DB. See `test_sor_tracking_asset_paradigm.py` docstring.

### `stock.move` has no `name` field in Odoo 19

`stock.move._rec_name = 'reference'` in Odoo 19. Tests and any code creating `stock.move` records must not pass `'name'`. See `odoo_19_breaking_changes.md`.

### XPath disambiguator for `quantity` column

The `quantity` field appears multiple times in the `stock.picking` form's move lines. The Odoo 19 XPath rule prohibits `@string` as a selector attribute. The existing `@column_invisible` attribute on the `quantity` field is used as the disambiguation selector: `//field[@name='quantity'][@column_invisible]`. This avoids the forbidden `@string` selector while uniquely targeting the correct element.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init \
  -u sor_tracking_asset_paradigm
```

---

## Story Reference

`.backlog/current/Movement Enhancements/stories/06_Tracking-Bridge-Modules.md`
