# Knowledge Base — sor_artwork

## Overview

`sor_artwork` extends Odoo's `product.template` model to represent artworks — physical unique objects that belong to the art market. It introduces a two-level product classification system (Type → Sub-type), artwork-specific metadata fields, multi-image support, and a certificate of authenticity tracker.

**What this module does:**
- Adds a `product_type` field (Level 1) with the `artwork` value to `product.template`
- Adds a `product_subtype` field (Level 2) with `painting`, `sculpture`, and `print` options
- Adds artwork metadata fields: dimensions, medium, creator, creation year, edition info, condition, provenance, certificates
- Introduces `sor.art.work.image` for managing multiple reference images per artwork
- Suppresses the native Odoo Inventory top-level menu on install and restores it on uninstall

**What this module does NOT do:**
- It does not implement location assignment for artworks — that is `sor_locations_artwork`
- It does not restrict `creator_id` to Creator-type contacts — that is `sor_artwork_contact_roles`
- It does not suppress inventory quant UI — that is `sor_asset_paradigm_artwork`
- It does not enable serial tracking — that is `sor_tracking_artwork`

**Depends on:** `product`, `sor_base`

**Bridge modules that auto-install with this module:**

| Bridge | Also requires | Feature added |
|--------|--------------|---------------|
| `sor_artwork_contact_roles` | `sor_contact_roles` | `creator_id` domain restricted to Creator contacts; `artwork_ids` and Artworks smart button on Creator partner form; creator deletion guard |
| `sor_asset_paradigm_artwork` | `sor_asset_paradigm` | Suppresses inventory quant stat buttons, qty columns, and Replenish action for `unique_object` paradigm artworks |
| `sor_locations_artwork` | `sor_locations` | `current_location_id` field on artwork; location assignment and navigation |
| `sor_tracking_artwork` | `sor_tracking` | Serial tracking; Traceability smart button on artwork form; movement line navigation to `product.template` |

---

## Key Fields and Models

### `product.template` (extended)

| Field | Type | Purpose | Notes |
|-------|------|---------|-------|
| `product_type` | `Selection` | Level 1 classification — `'artwork'` | Extended by vertical bridge modules via `selection_add`. `default_get` stamps `'artwork'` unless a different type is in context |
| `product_subtype` | `Selection` (dynamic) | Level 2 classification — `painting`, `sculpture`, `print` | Selection driven by `_get_product_subtype_selection()`; filtered in UI by `product_subtype_whitelist` |
| `product_subtype_whitelist` | `Char` (computed) | Technical field — comma-separated valid subtypes for the selected type | `store=False`; used by the filterable_selection widget |
| `dimensions_width` | `Float (10,2)` | Width — required for artwork | Validation raises if ≤ 0 or absent for `product_type='artwork'` |
| `dimensions_height` | `Float (10,2)` | Height — required for artwork | Same validation as width |
| `dimensions_depth` | `Float (10,2)` | Depth — required for sculptures, optional otherwise | Validation raises if absent or ≤ 0 for `product_subtype='sculpture'` |
| `medium` | `Char(255)` | Medium/material (e.g. "Oil on canvas", "Bronze") | Optional |
| `creator_id` | `Many2one → res.partner` | Creator/Artist — required for artwork | Domain-restricted to Creator contacts by `sor_artwork_contact_roles` when installed |
| `creation_year` | `Integer` | Year artwork was created | Must be between 1000 and 2100 |
| `edition_info` | `Text` | Edition details — for sculptures and prints only | Auto-cleared when `product_subtype` changes to `'painting'` |
| `condition` | `Text` | Condition notes | Optional |
| `provenance` | `Text` | Ownership/provenance history | Optional |
| `certificate_of_authenticity` | `Boolean` | Whether a certificate exists | Default: `False` |
| `certificate_attachment_ids` | `One2many → ir.attachment` | Certificate files | Domain filtered to `res_model='product.template'` |
| `work_image_ids` | `One2many → sor.art.work.image` | Multiple reference images | Ordered by `sequence, id` |
| `company_id` | `Many2one → res.company` | Company scoping override | Default: `env.company` (overrides the product model default) |

### `sor.art.work.image` (new model)

| Field | Type | Purpose |
|-------|------|---------|
| `work_id` | `Many2one → product.template` | Parent artwork (cascade delete) |
| `name` | `Char` | Image description (e.g. "Front view", "Detail shot") |
| `image` | `Image` (1920×1920 max) | The image file |
| `sequence` | `Integer` | Display order — lower numbers first; default 10 |

Records are ordered by `sequence, id`. Deleting the parent artwork cascades to all its images.

---

## Methods

### `default_get(fields_list)` — `product.template`

Stamps `product_type='artwork'` on new product records unless the context carries a different type.

**Logic:** if `default_product_type` is not in context, or it equals `'artwork'`, stamp `'artwork'`. If `default_product_type` is set to any other value, leave it unchanged. This allows bridge modules (e.g. `sor_asset_paradigm_baseline`) to pass `with_context(default_product_type=False)` and create non-artwork products without triggering the creator requirement constraint.

### `_get_product_subtype_selection()` — `@api.model`

Returns the full list of subtype options: `[('painting', 'Painting'), ('sculpture', 'Sculpture'), ('print', 'Print')]`. Extended by future vertical modules via `selection_add`.

### `_get_subtype_options_for_type(product_type)` — instance method

Returns the list of valid subtype codes for a given `product_type` string. Used by constraints and the `_onchange_product_type` handler.

### `_compute_product_subtype_whitelist()` — computed (`@api.depends('product_type')`)

Computes a comma-separated string of valid subtypes for the current `product_type`. Consumed by the filterable_selection widget in the view to restrict dropdown options without filtering already-assigned values.

### `_onchange_product_type()` — `@api.onchange`

When `product_type` changes: re-computes the whitelist, clears `product_subtype` if it is no longer valid for the new type, and auto-selects the first valid subtype.

### `_onchange_product_subtype()` — `@api.onchange`

When `product_subtype` changes to `'painting'`: clears `edition_info` (paintings do not have edition information).

---

## Validation Constraints

| Constraint | Model method | Rule |
|-----------|-------------|------|
| Type/subtype consistency | `_check_product_type_subtype` | `product_subtype` must be a valid subtype for `product_type` |
| Width/height required | `_check_dimensions_positive_and_required` | Both required and positive for `product_type='artwork'` |
| Depth for sculpture | `_check_depth_positive_and_required` | Required and positive when `product_subtype='sculpture'`; must be positive if provided for any other type |
| Creation year range | `_check_creation_year_range` | 1000–2100 if provided |
| Creator required | `_check_creator_required` | `creator_id` must be set for `product_type='artwork'` |

---

## Configuration

No settings page. The module installs with no user action required.

**Navigation after install:**

The native Odoo Inventory top-level menu (`stock.menu_stock_root`) is suppressed on install via `post_init_hook`. The SOR Artworks menu replaces it as the primary navigation entry for art products.

- Go to **Artworks** in the top menu bar to access the Artworks list, form, search, and any sub-menus provided by bridge modules.
- If you need to access native Inventory for testing or debugging, activate developer mode and restore the menu via Settings → Technical → User Interface → Menu Items.

---

## Install and Uninstall Hooks

| Hook | Effect |
|------|--------|
| `post_init_hook` | Calls `set_menu_active(env, 'stock.menu_stock_root', False)` — hides native Inventory |
| `uninstall_hook` | Calls `set_menu_active(env, 'stock.menu_stock_root', True)` — restores native Inventory |

Both hooks use the shared `set_menu_active` utility from `sor_technical_menu.utils`. The utility is a no-op if the target menu does not exist.

---

## Building on this Module

### Adding a new artwork sub-type

1. Add `sor_artwork` to your module's `depends`.
2. Extend `product_subtype` via `selection_add`:
   ```python
   product_subtype = fields.Selection(
       selection_add=[('photograph', 'Photograph')],
       ondelete={'photograph': 'set default'},
   )
   ```
3. Update `_get_subtype_options_for_type` in your module if the new sub-type should only appear for certain types. Use a method override returning the expanded mapping.

### Adding a new top-level product type

Use `selection_add` on `product_type` and extend `_get_subtype_options_for_type` to define which sub-types are valid for the new type. New types and their sub-types are independent — existing artwork sub-types will not appear for the new type unless you explicitly include them.

### Accessing artwork-specific fields from a bridge module

Artwork fields are on `product.template` directly. From any model that has a `product_id` Many2one to `product.template`:
```python
artwork = self.product_id
creator = artwork.creator_id
medium = artwork.medium
```

No `_inherit` required in the bridge — the fields are on the shared `product.template` model.

---

## Regression Checks

**R1 — Artworks menu visible after install**

1. Install `sor_artwork`.
2. Navigate to the top menu bar.
3. Expected: **Artworks** entry visible; no **Inventory** entry visible.

**R2 — Inventory menu restored after uninstall**

1. Uninstall `sor_artwork`.
2. Navigate to the top menu bar.
3. Expected: **Inventory** entry visible; native Inventory navigation fully restored.

**R3 — Artwork product creates successfully with required fields**

1. Navigate to **Artworks** → New.
2. Set: Name, Type = Artwork, Sub-type = Painting, Width = 60, Height = 80, Creator/Artist = any contact.
3. Save.
4. Expected: Record saves without error.

**R4 — Creator/Artist is required**

1. Navigate to **Artworks** → New.
2. Fill all required fields except Creator/Artist.
3. Attempt to save.
4. Expected: Validation error "Creator/Artist is required for artworks."

**R5 — Width and Height are required for artwork**

1. Navigate to **Artworks** → New.
2. Set Type = Artwork, Sub-type = Painting, Creator = any contact. Leave Width and Height empty.
3. Attempt to save.
4. Expected: Validation error about required width/height.

**R6 — Depth required for sculpture**

1. Navigate to **Artworks** → New.
2. Set Type = Artwork, Sub-type = Sculpture, Creator = any contact, Width and Height set.
3. Attempt to save without Depth.
4. Expected: Validation error "Depth is required for sculptures."

**R7 — Edition info cleared for paintings**

1. Navigate to **Artworks** → open an existing sculpture or print that has Edition Information set.
2. Change Sub-type to Painting.
3. Expected: Edition Information field clears automatically.

**R8 — Multiple images can be added**

1. Navigate to **Artworks** → open any artwork form.
2. Navigate to the **Images** tab.
3. Add two or more images with descriptions.
4. Save. Reload the record.
5. Expected: All images present, ordered by sequence.

**R9 — Certificate of authenticity attachment**

1. Navigate to **Artworks** → open any artwork form.
2. Navigate to the **Certificates** tab.
3. Tick Certificate of Authenticity. Add a file attachment.
4. Save and reload.
5. Expected: Checkbox remains ticked; attachment is present.

**R10 — Module survives upgrade**

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo -u sor_artwork --stop-after-init
docker exec odoo-app tail -20 /var/log/odoo/odoo-server.log
```

Expected: No `ERROR` lines. Existing artwork records intact.

---

## Interoperability

| Module | Relationship | What it adds |
|--------|-------------|-------------|
| `sor_artwork_contact_roles` | Bridge (auto with `sor_contact_roles`) | `creator_id` domain restricted to Creator contacts; `artwork_ids` and smart button on Creator partner form; creator deletion guard |
| `sor_asset_paradigm_artwork` | Bridge (auto with `sor_asset_paradigm`) | Suppresses inventory quant stat buttons and Replenish action for `unique_object` artwork paradigm |
| `sor_locations_artwork` | Bridge (auto with `sor_locations`) | `current_location_id` on artwork; location assignment in Artworks form |
| `sor_tracking_artwork` | Bridge (auto with `sor_tracking`) | Serial tracking enabled; Traceability smart button; movement line navigation to artwork form |
| `sor_technical_menu` | Dependency (via `sor_base`) | Provides `set_menu_active` utility used in `post_init_hook` / `uninstall_hook` |
