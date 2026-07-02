# Technical Architecture — sor_asset_paradigm_artwork

## Overview

`sor_asset_paradigm_artwork` is a bridge module that activates automatically when both `sor_asset_paradigm` and `sor_artwork` are installed. It is the reference implementation of the asset paradigm bridge pattern: it registers the `unique_object` paradigm value, installs 13 suppression rules covering every suppressible inventory UI element, and wires those rules to `invisible` expressions on the relevant product form, list, kanban, and variant views via per-element computed booleans.

All coupling between `sor_asset_paradigm` (mechanism) and `sor_artwork` (asset domain) is owned by this bridge. Neither parent module references the other.

```
sor_asset_paradigm           sor_artwork
        \                        /
         \                      /
    sor_asset_paradigm_artwork       ← bridge (this module)
```

---

## Module Pattern

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `True` | The bridge activates automatically when both parents are present; no manual installation required |
| `application` | `False` | Technical bridge; not a standalone app |
| `category` | `'Hidden/Technical'` | Excluded from business app listings |
| `depends` | `['sor_asset_paradigm', 'sor_artwork']` | Both parents required; the bridge has no meaning without either |
| `post_init_hook` | `'post_init_hook'` | Backfills `asset_paradigm='unique_object'` and `is_storable=True` on all pre-existing artwork products at first install |

---

## Architecture Decisions

### One boolean per element — no shared catch-all

Each suppressible element has its own named computed boolean on `product.template` (e.g. `is_forecast_btn_suppressed`, `is_inventory_tab_suppressed`). Views use these individual booleans in `invisible` expressions rather than a single shared flag. This design means:

- A developer can toggle one rule (e.g. re-enable the Forecasted Qty button) without affecting other elements.
- Each view XPath is independently readable — the intent is clear from the field name.
- Future bridges can independently suppress a subset of elements without interfering with artwork suppressions.

### `store=False` computed booleans and page-refresh requirement

All 13 suppression booleans are `store=False` with `@api.depends('asset_paradigm')`. They call `is_element_suppressed(element_key)` which in turn reads the current state of `sor.asset.paradigm.rule` records. Because the booleans are not stored, a developer can toggle a rule and see the effect immediately on the next page load — without needing to trigger an ORM recompute across all products. The trade-off is that a hard browser refresh (Cmd+Shift+R / Ctrl+Shift+R) is required after toggling a rule; an already-open product form will not update automatically.

### `product.product` related field mirrors

The stat buttons on the variant form (`product.product`) require access to suppression booleans, but those booleans live on `product.template`. Rather than duplicating the full computed logic on `product.product`, the bridge defines six `related` fields that proxy from `product_tmpl_id.*`. Only the six stat-button booleans are mirrored — the form-field and list/kanban suppression booleans are not needed at the variant level. Related fields are `store=False` by default.

### `_compute_show_qty_status_button()` ORM-level override

Odoo's stock module computes `show_on_hand_qty_status_button` and `show_forecasted_qty_status_button` on `product.template` via `_compute_show_qty_status_button()`. The bridge overrides this method on both `product.template` and `product.product`: it calls `super()` first (preserving the stock module's existing logic), then forces both flags to `False` for records where `is_element_suppressed('forecast_button')` is `True`. This means suppression operates at the ORM level — not just the view level — which is verifiable in the shell without a browser.

### Static suppression for list column headers

Odoo 19's `column_invisible` attribute is evaluated once at view parse time before any records load. It cannot reference per-record field values. The artwork list view therefore uses two approaches:

1. **Dynamic**: `invisible` on the column cell (hides cell values) — works with per-record booleans.
2. **Static**: `column_invisible="True"` on a separate dedicated view inheritance — hides the entire column including the header.

Two separate view records handle these two layers. The static suppression view (`sor_artwork_paradigm_product_list_view`) is unconditional and applies to the entire Artworks list view, which only ever shows artwork products. This is acceptable because the Artworks list is not a general product list — it is filtered to artworks by the Artworks top-level menu.

### `is_storable=True` must be backfilled alongside `asset_paradigm`

Pre-existing artwork products may have been created with `is_storable=False` (the Odoo default for consumable type products). `is_storable=False` permanently hides the stock stat buttons via stock's own `_compute_show_qty_status_button()` logic, regardless of the paradigm system. If `is_storable` is not set to `True`, there is no stat button to suppress — making it impossible for a developer to verify the toggle effect (AC9). The `post_init_hook` and both migration scripts therefore set `is_storable=True` alongside `asset_paradigm='unique_object'` on all pre-existing artworks.

### `default_get` sets `asset_paradigm` on new records before save

The `create()` override assigns `asset_paradigm='unique_object'` to new artwork products as part of `vals_list` processing. However, for a new record being filled in the UI, `create()` has not yet been called — the form renders before the user saves. To apply suppression immediately on a new artwork form (before save), `default_get()` is overridden to include `asset_paradigm='unique_object'` in the returned defaults. This means the suppression booleans evaluate correctly even on an unsaved new record.

### Replenish suppression at server-action level (functional only)

The Replenish action is suppressed by overriding the `ir.actions.server` records for both `stock.action_product_template_replenishment` (product.template) and `stock.action_product_replenishment` (product.product). The Python code in these actions checks `record.asset_paradigm == 'unique_object'` and silently returns without opening the replenishment wizard. This provides functional suppression — triggering the action on an artwork product does nothing — but does not remove the menu entry from the Action menu (⚙ gear icon). Full visual suppression is a known deferred item (see Story AC6 Developer Notes).

### `noupdate` strategy for data files

The three data files use different `noupdate` strategies:

| File | `noupdate` | Rationale |
|------|-----------|-----------|
| `paradigm_rules_data.xml` | `"0"` (updatable) | Rule record contents (paradigm, element_key, description) may be corrected on module upgrade. The `active` (Suppressed) field is what developers toggle; it is stored in the DB and not reset by upgrade because Odoo only writes fields declared in the data record. |
| `paradigm_rule_manifestations_data.xml` | `"0"` (updatable) | Manifestation records are developer documentation; they should be kept up to date with module upgrades. |
| `replenish_action_data.xml` | `"0"` (updatable) | Server action Python code may change; upgrade must apply the latest version. |

---

## Models

### `product.template` (extended)

**Field extension:**

| Field | Type | Purpose |
|-------|------|---------|
| `asset_paradigm` | `Selection(selection_add=[('unique_object', 'Unique Object')], ondelete={'unique_object': 'set default'})` | Registers the `unique_object` paradigm value. `ondelete='set default'` ensures the field reverts to `False` if the paradigm value is removed (e.g. module uninstall). |

**Computed suppression booleans (13):**

All are `store=False`, `@api.depends('asset_paradigm')`, returning `is_element_suppressed(key)`.

| Field | Element key |
|-------|-------------|
| `is_forecast_btn_suppressed` | `'forecast_button'` |
| `is_reorder_btn_suppressed` | `'reorder_button'` |
| `is_moves_btn_suppressed` | `'moves_button'` |
| `is_putaway_btn_suppressed` | `'putaway_button'` |
| `is_storage_cap_btn_suppressed` | `'storage_capacity_button'` |
| `is_qty_available_suppressed` | `'qty_available_field'` |
| `is_qty_column_suppressed` | `'qty_column'` |
| `is_operations_group_suppressed` | `'operations_group'` |
| `is_replenish_suppressed` | `'replenish_action'` |
| `is_odoo_product_type_field_suppressed` | `'odoo_product_type_field'` |
| `is_product_type_field_suppressed` | `'product_type_field'` |
| `is_track_inventory_field_suppressed` | `'track_inventory_field'` |
| `is_inventory_tab_suppressed` | `'inventory_tab'` |

**Methods:**

| Method | Purpose |
|--------|---------|
| `default_get(fields_list)` | Overridden to set `asset_paradigm='unique_object'`, `type='consu'`, `is_storable=True` for new artwork records. Applies suppression before first save. |
| `create(vals_list)` | Overridden: for each vals dict where `product_type='artwork'` and no explicit `asset_paradigm`, assigns `'unique_object'`. |
| `write(vals)` | Overridden: when `product_type='artwork'` and `asset_paradigm` is not already being set, forces `asset_paradigm='unique_object'` into `vals` before calling `super()`. |
| `_compute_show_qty_status_button()` | Overridden: calls `super()`, then forces both `show_on_hand_qty_status_button` and `show_forecasted_qty_status_button` to `False` for records where `is_element_suppressed('forecast_button')` is `True`. |

### `product.product` (extended)

Six related fields that proxy suppression booleans from the parent template for use in variant form view `invisible` expressions:

| Field | Related field |
|-------|--------------|
| `is_forecast_btn_suppressed` | `product_tmpl_id.is_forecast_btn_suppressed` |
| `is_reorder_btn_suppressed` | `product_tmpl_id.is_reorder_btn_suppressed` |
| `is_moves_btn_suppressed` | `product_tmpl_id.is_moves_btn_suppressed` |
| `is_putaway_btn_suppressed` | `product_tmpl_id.is_putaway_btn_suppressed` |
| `is_storage_cap_btn_suppressed` | `product_tmpl_id.is_storage_cap_btn_suppressed` |
| `is_qty_column_suppressed` | `product_tmpl_id.is_qty_column_suppressed` |

All are `store=False`. Only stat-button and qty-column booleans are mirrored — form-field suppression (Odoo type, SOR type, Track Inventory, Inventory tab) is not needed at the variant level because variant forms do not display those elements.

---

## Views

### `product_template_views.xml` (8 inheritance records)

| View ID | Inherits | What it does |
|---------|----------|-------------|
| `view_product_tmpl_procurement_btn_suppress` | `stock.product_template_form_view_procurement_button` | Adds `invisible` conditions to the 5 stat buttons (forecast, reorder ×2, moves, putaway, storage capacity). Injects 5 hidden boolean field declarations before the XPath patches. |
| `view_product_tmpl_property_form_suppress` | `stock.view_template_property_form` | Suppresses: Qty Available label+div, Operations group, Inventory tab. |
| `view_product_tmpl_tree_suppress` | `stock.view_stock_product_template_tree` | Adds `invisible` conditions to the qty_available and virtual_available list columns (hides cell values). See also static suppression view below. |
| `view_product_tmpl_form_type_suppress` | `product.product_template_form_view` | Suppresses: Odoo Product Type (type) radio, SOR product_type field, is_storable label+div. Also suppresses `group_general` when type field is suppressed (avoids empty fieldset). |
| `view_product_tmpl_kanban_suppress` | `stock.product_template_kanban_stock_view` | Suppresses the On Hand qty div in kanban cards using `t-if` with `raw_value` check. |
| `sor_artwork_paradigm_product_list_view` | `stock.view_stock_product_template_tree` | **Static suppression**: sets `column_invisible="True"` on qty_available and virtual_available columns to hide the column headers. Applies unconditionally to the Artworks list view. |
| `view_product_tmpl_search_type_suppress` | `product.product_template_search_view` | Removes the Goods, Services, and Combo search filters and the Product Type group-by filter using `position="replace"` with empty replacement. Static — not rule-driven. |
| `view_product_tmpl_search_product_type_groupby_suppress` | `sor_artwork.view_product_template_search_artwork` | Removes the SOR product type group-by filter from the Artworks-specific search view. Static — not rule-driven. |

### `product_views.xml` (1 inheritance record)

| View ID | Inherits | What it does |
|---------|----------|-------------|
| `view_product_procurement_btn_suppress` | `stock.product_form_view_procurement_button` | Variant-form stat button suppression using related fields mirrored from `product.product`. Mirrors the template-form suppression at the variant level. |

**Injection pattern for `invisible` expressions:**

Odoo 19's view arch parser resolves field types at parse time. Any field referenced in an `invisible` expression must be present in the combined view arch — declared as a `<field>` element — or the parser raises a runtime error. All view inheritance records inject suppression booleans as `<field name="..." invisible="1"/>` declarations before the XPath patches that use them. The injection anchor is typically `//field[@name='name']` position `before`.

---

## Module File Structure

```
sor_asset_paradigm_artwork/
├── __init__.py                                          # Imports hooks, models
├── __manifest__.py                                      # Module declaration
├── hooks.py                                             # post_init_hook: backfills paradigm + is_storable
├── models/
│   ├── __init__.py                                      # Imports product_template, product_product
│   ├── product_template.py                              # selection_add, computed booleans, create/write/default_get overrides
│   └── product_product.py                               # Related field mirrors for variant form
├── views/
│   ├── product_template_views.xml                      # 8 view inheritance records
│   └── product_views.xml                               # 1 variant form view inheritance
├── security/
│   └── ir.model.access.csv                             # Empty (no new models)
├── data/
│   ├── paradigm_rules_data.xml                         # 13 sor.asset.paradigm.rule records
│   ├── paradigm_rule_manifestations_data.xml           # 25 sor.asset.paradigm.rule.manifestation records
│   └── replenish_action_data.xml                       # 2 ir.actions.server overrides
├── migrations/
│   ├── 19.0.1.0.1/
│   │   └── post-migrate.py                             # Backfills asset_paradigm='unique_object' on upgrade
│   └── 19.0.1.0.2/
│       └── post-migrate.py                             # Backfills is_storable=True on upgrade
├── tests/
│   ├── __init__.py                                     # Imports test module
│   └── test_artwork_paradigm.py                        # Tests for all story ACs
└── doc/
    ├── KNOWLEDGE_BASE.md                               # User guides and regression checks
    └── TECHNICAL_ARCHITECTURE.md                      # This file
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/product_template.py` | Owns the full suppression logic: `selection_add`, all 13 computed booleans, `create`/`write`/`default_get` overrides, `_compute_show_qty_status_button` override. |
| `models/product_product.py` | Related field mirrors that make variant form suppression possible without duplicating compute logic. |
| `hooks.py` | `post_init_hook` that backfills `asset_paradigm` and `is_storable` on pre-existing artworks at first install. Critical for correct suppression on legacy data. |
| `data/paradigm_rules_data.xml` | Installs the 13 `sor.asset.paradigm.rule` records. These are the records that `is_element_suppressed()` looks up at runtime. |
| `data/paradigm_rule_manifestations_data.xml` | Installs 25 manifestation records for developer inspection. Not runtime-critical but part of the developer UI. |
| `data/replenish_action_data.xml` | Overrides the Replenish server actions with paradigm-aware guards. Must be loaded last in `data` list. |
| `migrations/19.0.1.0.2/post-migrate.py` | The `is_storable=True` backfill. Required for stat buttons to be visible enough to suppress on pre-existing artworks. |
| `views/product_template_views.xml` | The 8 view inheritance records that wire suppression booleans to Odoo's product UI. |

---

## Composability Boundary

| Scenario | `asset_paradigm` on artworks | Suppression active | Stat buttons hidden | Column headers hidden |
|----------|-----------------------------|-------------------|--------------------|-----------------------|
| `sor_artwork` alone | Not set | No | No | No |
| `sor_asset_paradigm` + `sor_artwork` | Not set (bridge not installed) | No | No | No |
| All three installed (this bridge active) | `'unique_object'` (auto-assigned) | Yes | Yes | Yes |
| All three, rule toggled off for one element | `'unique_object'` | Yes, except toggled element | Depends on rule | Depends on rule |
| All three, debug param = `'True'` | `'unique_object'` | No | No | No (except static) |

**Note:** Static suppressions (`column_invisible="True"` in `sor_artwork_paradigm_product_list_view`, and the search filter replacements) are **not** affected by rule toggles or the debug parameter. They are view-level rewrites applied unconditionally. This is a known limitation documented in the story AC6 Developer Notes.

---

## Special Concerns

### Two suppression layers for list columns

The qty_available and virtual_available columns in the product list are suppressed at two layers:

1. **Cell values** (`view_product_tmpl_tree_suppress`): uses `invisible="not show_on_hand_qty_status_button or is_qty_column_suppressed"` — dynamic, rule-driven.
2. **Column headers** (`sor_artwork_paradigm_product_list_view`): uses `column_invisible="True"` — static, unconditional.

A developer who toggles the `qty_column` rule off will see the cell values reappear (layer 1 responds) but the column headers will remain hidden (layer 2 is static). This is a known limitation. Full dynamic header suppression requires a different approach (e.g. a static Artworks-specific list view that omits the columns entirely rather than suppressing them).

### Search filter suppression is static

The search filter and group-by suppression views (`view_product_tmpl_search_type_suppress`, `view_product_tmpl_search_product_type_groupby_suppress`) use `position="replace"` to replace filter elements with empty content. This is static and cannot be toggled via the Paradigm Rules UI. It is appropriate here because the search view is shared with the Artworks menu, which should never expose product type filtering. The static approach is marked with `is_static=True` on the corresponding manifestation records.

### `post_init_hook` vs. `post_migrate` hooks

`post_migrate` is not a valid Odoo manifest key (`post_init_hook` and `pre_init_hook` are the only valid hooks). The first-install backfill is in `hooks.py:post_init_hook`. Subsequent upgrade paths are handled by the two migration scripts (`19.0.1.0.1` and `19.0.1.0.2`). Databases that had the module installed at a prior version will receive the migration scripts on `--update`; databases receiving their first install will receive the `post_init_hook`.

### Test environment adaptations

The test suite requires adaptations because `sor_artwork` is always active in the test environment:

1. All products created via ORM require `creator_id`, `dimensions_width`, and `dimensions_height` (enforced by `sor_artwork` constraints). A Creator-type partner is created in `setUpClass`.
2. The `create()` override assigns `asset_paradigm='unique_object'` to all new products. Test products that must have a `'standard'` paradigm must be created with `asset_paradigm='standard'` explicitly.
3. `test_post_init_hook_sets_paradigm_on_existing_artworks` clears `asset_paradigm` via raw SQL to simulate a pre-install state, then calls the hook, then uses `env.flush_all()` + `record.invalidate_recordset(['asset_paradigm'])` before asserting — the hook writes to a separate ORM recordset; `invalidate_recordset` forces the test's `record` object to re-read from the DB.

### Replenish visual suppression is deferred

The Replenish option in the Action menu (⚙ gear icon) may still appear for artwork products. `ir.actions.server.binding_domain` does not reliably filter action menu entries on a per-record basis in Odoo 19 Community. Functional suppression (the action silently skips artworks) is in place; visual removal is deferred. See `.backlog/00 Asset Paradigm/Sprint Retrospective v2.md` for the RICE-scored assessment.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init \
  --http-port=8071 \
  -u sor_asset_paradigm,sor_asset_paradigm_baseline,sor_asset_paradigm_artwork
```

All three modules are upgraded together. The artwork bridge test suite depends on both the mechanism module and the baseline bridge being present.

---

## Story Reference

Parent story: [02 Artwork Quant Suppression](../../../.backlog/00%20Asset%20Paradigm/stories/02_Artwork-Quant-Suppression.md)
