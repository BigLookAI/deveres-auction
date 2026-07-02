# Technical Architecture — sor_artwork

## Overview

`sor_artwork` is a **vertical SOR module** that extends Odoo's `product.template` to represent artworks. It introduces a two-level product classification hierarchy (`product_type` → `product_subtype`), artwork-specific metadata fields, a purpose-built multi-image model (`sor.art.work.image`), and hook-based suppression of the native Odoo Inventory menu.

The module sits at the base of the SOR artwork vertical. All artwork-specific bridge modules (`sor_artwork_contact_roles`, `sor_asset_paradigm_artwork`, `sor_locations_artwork`, `sor_tracking_artwork`) depend on this module as one of their two parents.

Dependency diagram:

```
product
  └── sor_base
        └── sor_artwork
                  ├── sor_artwork_contact_roles  (bridge: + sor_contact_roles)
                  ├── sor_asset_paradigm_artwork  (bridge: + sor_asset_paradigm)
                  ├── sor_locations_artwork       (bridge: + sor_locations)
                  └── sor_tracking_artwork        (bridge: + sor_tracking)
```

---

## Module Pattern

**Manifest flags:**

```python
'application': False,
'auto_install': False,
'category': 'Custom',
'depends': ['product', 'sor_base'],
'post_init_hook': 'post_init_hook',
'uninstall_hook': 'uninstall_hook',
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `application` | `False` | `sor_artwork` is a composable building block, not a standalone Odoo App |
| `auto_install` | `False` | Requires explicit install; it is not the intersection of two parents |
| `category` | `'Custom'` | Classified as custom SOR development |
| `depends` | `['product', 'sor_base']` | `product` provides `product.template`; `sor_base` pulls in `sor_asset_paradigm` and `sor_business_model` as horizontal infrastructure |
| `post_init_hook` | present | Suppresses native Inventory menu on first install |
| `uninstall_hook` | present | Restores native Inventory menu when module is removed |

---

## Architecture Decisions

**Why extend `product.template` rather than creating a new model?**

Artworks are products in the Odoo sense — they can be tracked, stored, transferred, and (in commercial contexts) sold. Using `_inherit` on `product.template` gives artworks the full Odoo product infrastructure (inventory tracking, serial numbers, images, pricelist) without duplication. Bridge modules then layer art-market-specific behaviour on top.

**Why a two-level type hierarchy (`product_type` + `product_subtype`) rather than a flat selection?**

The two levels serve different purposes. `product_type` identifies the broad kind of asset (artwork, antique, jewellery in future vertical modules). `product_subtype` refines within that kind (painting, sculpture, print). This separation allows:
- Bridge modules to target `product_type='artwork'` for all artwork logic
- View visibility rules to target `product_subtype` for sub-type-specific fields (depth for sculpture, edition info for non-paintings)
- Future vertical modules to register their own type + subtypes independently

A flat single-level selection would conflate type-level and subtype-level concerns and make the field unwieldy as the module count grows.

**Why `default_get` override instead of a `default=` on the field?**

A field-level `default=` would apply unconditionally. The `default_get` override respects context: when another module passes `with_context(default_product_type=False)` (as `sor_asset_paradigm_baseline` does when creating the Baseline Product), the override does not stamp `'artwork'`. A field-level default cannot be suppressed by context.

The guarded condition `if not ctx_type or ctx_type == 'artwork'` ensures the default stamps `'artwork'` only when no explicit type is requested — preventing the B2/C1-class demo data contamination where an ORM create for a non-artwork product inherited the `'artwork'` type from an unguarded default.

**Why hook-based menu suppression instead of data XML `active=False`?**

Data XML `active=False` is applied once on install and never reversed — Odoo's module system cannot cleanly undo it on uninstall. Hook-based suppression (`post_init_hook` to suppress, `uninstall_hook` to restore) is the only fully reversible mechanism. See `references/sor_design_patterns.md` Pattern 9.

**Why `set_menu_active` from `sor_technical_menu` rather than a local helper?**

The suppression utility is shared infrastructure owned by `sor_technical_menu`. Using it keeps the suppression registry centralised. `sor_artwork` accesses it via `sor_base` → `sor_technical_menu` in the dependency chain.

---

## Models

### `product.template` (extended via `_inherit`)

Class: `SorArtProduct` in `models/sor_art_product.py`

**Fields added:**

| Field | Type | Purpose | Constraints |
|-------|------|---------|------------|
| `product_type` | `Selection` | Level 1 type (`'artwork'`) | `selection_add`-extensible; `default_get` stamps `'artwork'` by default |
| `product_subtype` | `Selection` (dynamic) | Level 2 sub-type | Dynamic via `_get_product_subtype_selection()`; validated against type |
| `product_subtype_whitelist` | `Char` (computed, `store=False`) | Comma-separated valid subtypes | Used by filterable_selection widget |
| `dimensions_width` | `Float(10,2)` | Width | Required + positive for `product_type='artwork'` |
| `dimensions_height` | `Float(10,2)` | Height | Required + positive for `product_type='artwork'` |
| `dimensions_depth` | `Float(10,2)` | Depth | Required + positive for `product_subtype='sculpture'` |
| `medium` | `Char(255)` | Material/medium | Optional |
| `creator_id` | `Many2one → res.partner` | Creator/Artist | Required for `product_type='artwork'` |
| `creation_year` | `Integer` | Creation year | 1000–2100 if provided |
| `edition_info` | `Text` | Edition details | For sculpture/print only; cleared on subtype change to `'painting'` |
| `condition` | `Text` | Condition notes | Optional |
| `provenance` | `Text` | Provenance history | Optional |
| `certificate_of_authenticity` | `Boolean` | Certificate exists flag | Default `False` |
| `certificate_attachment_ids` | `One2many → ir.attachment` | Certificate files | Domain: `res_model='product.template'` |
| `work_image_ids` | `One2many → sor.art.work.image` | Multiple reference images | Ordered by `sequence, id` |
| `company_id` | `Many2one → res.company` | Company default override | `default=lambda self: self.env.company` |

**Methods added:**

| Method | Decorator | Purpose |
|--------|-----------|---------|
| `default_get(fields_list)` | `@api.model` | Stamps `product_type='artwork'` respecting context |
| `_get_product_subtype_selection()` | `@api.model` | Returns full subtype selection list |
| `_get_subtype_options_for_type(product_type)` | — | Returns valid subtype codes for a type |
| `_compute_product_subtype_whitelist()` | `@api.depends('product_type')` | Builds comma-separated whitelist string |
| `_onchange_product_type()` | `@api.onchange('product_type')` | Clears/auto-selects subtype; updates whitelist |
| `_onchange_product_subtype()` | `@api.onchange('product_subtype')` | Clears `edition_info` for paintings |
| `_check_product_type_subtype()` | `@api.constrains(...)` | Subtype valid for type |
| `_check_dimensions_positive_and_required()` | `@api.constrains(...)` | Width/height required + positive for artwork |
| `_check_depth_positive_and_required()` | `@api.constrains(...)` | Depth required + positive for sculpture |
| `_check_creation_year_range()` | `@api.constrains('creation_year')` | Year between 1000–2100 |
| `_check_creator_required()` | `@api.constrains('creator_id', 'product_type')` | Creator required for artwork |

### `sor.art.work.image` (new model)

Class: `SorArtWorkImage` in `models/sor_art_work_image.py`

`_order = 'sequence, id'`

| Field | Type | Purpose |
|-------|------|---------|
| `work_id` | `Many2one → product.template` (required, `ondelete='cascade'`) | Parent artwork |
| `name` | `Char` | Image description |
| `image` | `Image` (1920×1920 max) | Image file |
| `sequence` | `Integer` (default 10) | Display order |

---

## Views

Defined in `views/sor_art_product_views.xml`.

| Record | Type | Inherits | What it does |
|--------|------|----------|-------------|
| `view_sor_artwork_product_form` | `form` | `product.product_template_form_view` | Adds Product Details, Optional Information, Certificates, and Images tabs with artwork-specific fields. Dynamic visibility via `product_type` and `product_subtype` expressions. |
| `view_sor_artwork_product_list` | `list` | `product.product_template_tree_view` | Adds type, sub-type, creation year, dimensions, medium, creator columns. Most are `optional="show"` to avoid cluttering the default list. |
| `view_sor_artwork_product_search` | `search` | `product.product_template_search_view` | Adds search on type, sub-type, creator, certificate status. Includes named filters for Paintings, Sculptures, Prints, and Has Certificate. |
| `action_sor_artworks` | `ir.actions.act_window` | — | Window action opening `product.template` filtered to `product_type='artwork'` |
| `menu_sor_artworks_root` | `ir.ui.menu` | — | Top-level Artworks menu entry linked to `action_sor_artworks` |

The form view inherits the Odoo product form with `position="inside"` XPath patches, preserving all standard product fields (name, internal reference, price, inventory tracking) while adding artwork-specific tabs.

---

## Module File Structure

```
sor_artwork/
├── __manifest__.py          # depends: product, sor_base; hooks registered
├── __init__.py              # imports models, post_init_hook, uninstall_hook
├── hooks.py                 # post_init_hook / uninstall_hook — menu suppression
├── models/
│   ├── __init__.py          # imports sor_art_product, sor_art_work_image
│   ├── sor_art_product.py   # SorArtProduct — extends product.template
│   └── sor_art_work_image.py # SorArtWorkImage — sor.art.work.image model
├── views/
│   └── sor_art_product_views.xml  # Form, list, search, action, menu
├── security/
│   └── ir.model.access.csv  # CRUD for product.template and sor.art.work.image
├── demo/
│   └── demo_artworks.xml    # 15 demo artworks (5 paintings, 3 sculptures, 4 prints, 3 paintings)
├── i18n/
│   └── sor_artwork.pot      # Translatable strings
├── static/
│   └── src/scss/
│       └── artwork_images.scss  # 250px image sizing for product image and embedded list images
├── tests/
│   ├── __init__.py
│   ├── test_artwork_hooks.py    # Hook behaviour and guarded default_get tests
│   ├── test_artwork_fields_validations.py  # Constraint validation tests
│   ├── test_creator_artwork_relationship.py
│   ├── test_contact_type_system.py
│   ├── test_data_integrity.py
│   ├── test_module_installation.py
│   ├── test_workflow_integration.py
│   └── test_performance.py
└── doc/
    ├── KNOWLEDGE_BASE.md    # User-facing reference
    └── TECHNICAL_ARCHITECTURE.md  # This document
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | `depends: ['product', 'sor_base']`; hooks registered |
| `hooks.py` | Menu suppression/restoration via `set_menu_active` from `sor_technical_menu` |
| `models/sor_art_product.py` | All artwork fields, validation constraints, `default_get` override |
| `models/sor_art_work_image.py` | `sor.art.work.image` — multi-image model |
| `views/sor_art_product_views.xml` | Form, list, search views; Artworks action and menu |
| `tests/test_artwork_hooks.py` | Hook behaviour; `default_get` context guarding |

---

## Composability Boundary

| Installation state | product_type field | Artwork sub-types | Creator domain restricted | Inventory quant UI suppressed | Location field | Serial tracking |
|-------------------|--------------------|-------------------|--------------------------|-------------------------------|---------------|-----------------|
| `sor_artwork` only | Yes | Yes | No | No | No | No |
| + `sor_contact_roles` | Yes | Yes | Yes (via bridge) | No | No | No |
| + `sor_asset_paradigm` | Yes | Yes | No | Yes (via bridge) | No | No |
| + `sor_locations` | Yes | Yes | No | No | Yes (via bridge) | No |
| + `sor_tracking` | Yes | Yes | No | No | No | Yes (via bridge) |
| All bridges installed | Yes | Yes | Yes | Yes | Yes | Yes |

---

## Special Concerns

**`default_get` guard — critical for fresh-install safety**

The guarded `default_get` is a B2/C1-class fix: without the guard (`if not ctx_type or ctx_type == 'artwork'`), any ORM `create()` call on `product.template` without explicit `product_type` in `vals` — including calls from unrelated modules — would receive `product_type='artwork'` via `default_get`. This triggers `_check_creator_required`, causing a `ValidationError` on any module that creates product records without setting a creator (e.g. `sor_asset_paradigm_baseline`, demo data imports, Odoo base module seeding).

**`_check_creator_required` and the `with_context(default_product_type=False)` pattern**

Any module that creates `product.template` records programmatically (via ORM, not via the UI) and does not intend to create artworks must pass `with_context(default_product_type=False)` to suppress the `default_get` stamp. Without it, `default_get` stamps `'artwork'`, and the constraint fails because `creator_id` is absent. This is documented in `sor_asset_paradigm_baseline/hooks.py` as a concrete example.

**`product_subtype` is a dynamic selection — not a simple field**

`product_subtype` uses `selection='_get_product_subtype_selection'` (a method reference, not a static list). Odoo evaluates this at field definition time and at form load. The `product_subtype_whitelist` computed field is a workaround for the filterable_selection widget — the widget needs a comma-separated string of allowed values to restrict the visible dropdown options without hard-coding them in the field definition.

**Menu suppression is not applied on `--update`**

`post_init_hook` runs only on first install (`-i`). Running `-u sor_artwork` on an existing installation does not re-run the hook and does not re-suppress the Inventory menu. If the menu has been manually re-enabled (e.g. for debugging), it must be re-suppressed via the Odoo shell or by reinstalling the module.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_artwork
```

---

## Story Reference

`.backlog/current/Composability Enhancements/stories/`
