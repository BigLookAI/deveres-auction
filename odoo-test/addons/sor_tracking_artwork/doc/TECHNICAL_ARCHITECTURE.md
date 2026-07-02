# Technical Architecture: sor_tracking_artwork

## Overview

`sor_tracking_artwork` is a **bridge module** that connects the physical movement layer (`sor_tracking`) with the artwork product domain (`sor_artwork`). It delivers five features: serial tracking defaults for artwork products; a dual-column serial number UI on the main movement form (editable text in Draft, lot tag in Ready+); unique-object serial integrity (one serial per artwork, forever); a Traceability smart button on artwork product forms; and a navigation fix that ensures artwork product forms open correctly from movement line links.

```
sor_tracking          sor_artwork
       \                   /
        \                 /
    sor_tracking_artwork   (auto_install=True, application=False)
```

Neither parent module is modified. The bridge activates automatically when both parents are installed.

---

## Module Pattern

**Manifest flags:**
```python
'category': 'Hidden/Technical',
'depends': ['sor_tracking', 'sor_artwork'],
'auto_install': True,
'application': False,
'post_init_hook': 'post_init_hook',
```

- `auto_install: True` — Odoo installs the bridge automatically when both `sor_tracking` and `sor_artwork` are present.
- `application: False` — Does not appear as a top-level App.
- `category: 'Hidden/Technical'` — Excluded from business category listings.
- `post_init_hook` — Enables the serial tracking group and migrates existing artwork products on first install.

**Why a bridge?** `sor_tracking` must be installable without artwork-specific behaviour (e.g. for a non-artwork asset type). `sor_artwork` must be installable without movement tracking (e.g. for metadata-only catalogue use). Placing the serial tracking defaults, serial column surfacing, Traceability button, or navigation override in either parent would introduce coupling that prevents independent installation.

---

## Architecture Decisions

### Serial tracking via `default_get`, not a constraint

Serial tracking is set as a default for new artwork products via `default_get`. The design alternatives were:

| Approach | Why rejected |
|----------|-------------|
| `@api.constrains` on `tracking` | Would block creating artwork products with `tracking = 'none'` — valid if the module is installed but the user intends a different tracking mode (e.g. migrated data) |
| `@api.onchange` only | Onchange fires in the UI but not when products are created via code or import |
| `default_get` (chosen) | Fires for all programmatic creation through `default_get`; only sets the value when not already overridden; does not constrain post-creation edits |

The migration hook (`_migrate_existing_artworks`) writes `tracking = 'serial'` to all existing artwork products on install. This is a one-time migration — idempotent and safe.

### Dual-column serial number UI — `sor_draft_lot_name` (Draft) + `lot_ids` (non-Draft)

The serial number column on the movement Operations list uses two fields that swap based on picking state:

| State | Column | Field | Reason |
|-------|--------|-------|--------|
| Draft | Editable text | `sor_draft_lot_name` (Char on `stock.move`) | Creating a `stock.move.line` in Draft triggers Odoo's `_recompute_state()` → auto-advance to Ready. Using a Char field on the move avoids creating any ML in Draft. |
| Ready or later | Lot tag | `lot_ids` (One2many → `stock.lot` on `stock.move`) | Native Odoo field; already carries the assigned lot after `action_confirm()` pre-creates it. |

The `column_invisible` attribute controls visibility. `sor_draft_lot_name` uses `column_invisible="parent.state != 'draft'"`. The native `lot_ids` column retains its native `column_invisible="parent.state == 'draft'"` expression unchanged — the XPath only changes `optional` and `options`.

**Critical constraint:** In Odoo 19, `MovesListRenderer.evalColumnInvisible` evaluates `column_invisible` against a limited context that supports only static values and `parent.*` references (to the parent `stock.picking`). Bare field references on `stock.move` (e.g. `state`, `has_tracking`) raise `EvalError: Name not defined`. All `column_invisible` expressions on the Operations list must use `parent.<field>` form.

### `sor_draft_lot_name` → `stock.lot` conversion at `action_confirm()`

When staff click Mark as Todo, `action_confirm()` pre-creates the `stock.lot` from `sor_draft_lot_name` **before** calling `super()`. This ensures that when Odoo's `_action_assign` creates `stock.move.line` records, the `create()` override's existing-lot lookup finds the staff-specified lot and reuses it — the staff-entered name is honoured, not overwritten by the auto-sequence.

### Unique-object serial integrity — existing-lot lookup

A unique-object artwork has exactly one `stock.lot` record, forever. Any movement for the same artwork must reuse the existing lot. The existing-lot search runs in `stock.move.line.create()` and `_onchange_sor_artwork_serial` before any call to `ir.sequence.next_by_code`. If a lot is found for `(product_id, company_id)`, it is assigned — no sequence value is consumed.

### Traceability button — `sor_movement_count` + `action_view_traceability` on `product.template`

The native "Lot/Serial Numbers" smart button (which opens a kanban of `stock.lot` records) is replaced by a Traceability smart button that opens a list of **completed movement lines** (`stock.move.line`, `state='done'`). This view is operationally correct for the art market: staff want to see where an artwork has been, not manage its lot records.

`sor_movement_count` is a `store=False` computed Integer on `product.template`. It counts `stock.move.line` records where `product_id.product_tmpl_id = self` and `state = 'done'`. The native "Lot/Serial Numbers" button is suppressed via view inheritance using `invisible="1"`.

### Navigation fix — `get_formview_action` override on `product.product`

`stock.move.line.product_id` is a `Many2one('product.product')` — Odoo's variant model. When staff click the product link in a movement's Operations tab, Odoo calls `get_formview_action()` on the `product.product` record. Natively this opens the `product.product` form view, which does not carry SOR artwork customisations (those live on `product.template`). This bridge overrides `get_formview_action()` on `product.product` to redirect artwork navigation to `product.template`, returning the correct `res_id` of the template. Non-artwork `product.product` records fall through to Odoo's standard implementation.

---

## Models

### `product.template` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `default_get` override | Method | Sets `tracking = 'serial'` when `product_type` context defaults to `'artwork'` |
| `sor_movement_count` | `Integer`, computed (`store=False`) | Count of `stock.move.line` records with `product_id.product_tmpl_id = self` and `state = 'done'`. Drives the Traceability smart button. |
| `action_view_traceability` | Method | Returns `ir.actions.act_window` for `stock.move.line` filtered to completed movements for this artwork. Name: `'Traceability'`. |

### `product.product` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `get_formview_action` override | Method | Redirects navigation to `product.template` for artwork variants. Non-artwork products fall through to standard Odoo behaviour. |

### `stock.move` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `sor_draft_lot_name` | `Char` | Temporary serial name for Draft-state manual entry. Not visible once picking leaves Draft. Cleared by `action_confirm()` after lot pre-creation. |

### `stock.move.line` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `create()` override | Method | Existing-lot lookup → reuse or auto-assign. See Architecture Decisions for full logic. |
| `_onchange_sor_artwork_serial` | Method | Reactive assignment in the Detailed Operations dialog (fires on `product_id`/`picking_id` change). Same existing-lot logic as `create()`. |

### `stock.picking` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `action_confirm()` override | Method | (1) Delete ghost MLs; (2) pre-create `stock.lot` from `sor_draft_lot_name`; (3) call `super()`; (4) post-confirm ML creation for manual-reservation-type moves. |

### `stock.lot` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `default_get` override | Method | Pre-populates the `name` field with the next `sor.artwork.serial` sequence value when a `stock.lot` is created via the UI (context `default_product_id` set and product is `unique_object` serial-tracked artwork). Provides a sensible default if staff open the lot creation dialog manually. |

### `res.company` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `create` override | Method | Passthrough stub — serial tracking groups are instance-wide, not per-company |

---

## Views

### `view_stock_move_line_operation_tree_sor_tracking_artwork`

- **Model:** `stock.move.line`
- **Inherits:** `stock.view_stock_move_line_operation_tree`
- **Inheritance mode:** Non-primary (XPath patch)
- **What it does:** Relabels `lot_id` and `lot_name` columns from "Lot/Serial Number" to "Serial Number" in the Detailed Operations dialog inner list.
- **Why:** `lot` terminology is reserved for `sor.lot` auction catalogue lots in SOR. The native label creates a terminology collision when staff view artwork movements.

### `product_template_form_view_procurement_button_sor_tracking_artwork`

- **Model:** `product.template`
- **Inherits:** `stock.product_template_form_view_procurement_button`
- **Inheritance mode:** Non-primary (XPath patch)
- **What it does:** Suppresses the native "Lot/Serial Numbers" smart button (`invisible="1"`) and adds a **Traceability** smart button displaying `sor_movement_count`. Also adds the `sor_movement_count` field declaration to the arch (required for the invisible expression on the button count).
- **Why:** The native Lot/Serial Numbers button opens a kanban of `stock.lot` records — unsuitable for the art market. Traceability shows the history of completed movements instead.

### `stock_picking_form_sor_tracking_artwork`

- **Model:** `stock.picking`
- **Inherits:** `stock.view_picking_form`
- **Inheritance mode:** Non-primary (XPath patch)
- **What it does:** Adds the `sor_draft_lot_name` column (string "Serial Number", `column_invisible="parent.state != 'draft'"`) before `lot_ids` in the Operations (`stock.move`) list. Also patches `lot_ids`: changes `optional` from `hide` to `show` and adds `options="{'no_create': True}"`. The native `column_invisible` and `invisible` on `lot_ids` are intentionally left at their native values (`parent.state == 'draft'` and `not show_details_visible or has_tracking == 'none'`).
- **Why:** Unique-object artworks need serial number entry directly on the main movement form. In Draft, an editable text cell avoids creating MLs (which would auto-advance the picking to Ready). In Ready+, the native `lot_ids` tag column shows the assigned serial. The two-column swap uses `parent.state` throughout — required because `MovesListRenderer.evalColumnInvisible` only supports `parent.*` references in dynamic expressions.

---

## Module File Structure

```
sor_tracking_artwork/
├── __manifest__.py              — Module metadata; declares post_init_hook
├── __init__.py                  — Imports models; imports post_init_hook from hooks
├── hooks.py                     — post_init_hook: enables serial groups + migrates artworks
├── models/
│   ├── __init__.py
│   ├── product_template.py      — default_get, sor_movement_count, action_view_traceability
│   ├── product_product.py       — get_formview_action override (artwork → product.template)
│   ├── stock_lot.py             — default_get: pre-populates name from sor.artwork.serial sequence
│   ├── stock_move.py            — sor_draft_lot_name Char field for Draft serial entry
│   ├── stock_move_line.py       — create() override (existing-lot lookup + auto-assign); _onchange_sor_artwork_serial
│   ├── stock_picking.py         — action_confirm() override (ghost ML deletion + sor_draft_lot_name pre-creation)
│   └── res_company.py           — Passthrough create() stub
├── views/
│   ├── stock_move_views.xml     — Relabels lot fields; sor_draft_lot_name (Draft) + lot_ids (non-Draft) dual columns
│   └── product_template_views.xml — Traceability smart button; suppresses Lot/Serial Numbers button
├── security/
│   └── ir.model.access.csv      — No new models; CSV is minimal (required by Odoo)
├── i18n/
│   └── sor_tracking_artwork.pot — Translation template
├── tests/
│   ├── __init__.py
│   ├── test_placeholder.py      — Stub (retained)
│   └── test_sor_tracking_artwork.py — Full test suite
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | `post_init_hook` key; `auto_install`, `depends` |
| `hooks.py` | Install-time serial group enablement and artwork migration |
| `models/product_template.py` | Serial tracking default (`default_get`); `sor_movement_count`; `action_view_traceability` |
| `models/product_product.py` | `get_formview_action` override — redirects artwork navigation to `product.template` |
| `models/stock_lot.py` | `default_get` override — pre-populates `name` from `sor.artwork.serial` sequence when creating a lot via UI |
| `models/stock_move.py` | `sor_draft_lot_name` Char field — Draft-state manual serial entry without creating MLs |
| `models/stock_move_line.py` | `create()` override (existing-lot lookup + auto-assign); `_onchange_sor_artwork_serial` |
| `models/stock_picking.py` | `action_confirm()` override — ghost ML deletion + `sor_draft_lot_name` pre-creation + post-confirm ML loop |
| `views/stock_move_views.xml` | "Serial Number" relabelling; dual-column: `sor_draft_lot_name` (Draft) + `lot_ids` (non-Draft) |
| `views/product_template_views.xml` | Traceability smart button; suppresses native Lot/Serial Numbers button |
| `tests/test_sor_tracking_artwork.py` | Full test suite |

---

## Composability Boundary

| Installation state | Serial tracking default | Dual serial column on form | Unique-object integrity | Traceability button | Navigation fix | Migration |
|-------------------|------------------------|---------------------------|------------------------|--------------------|----|---|
| `sor_tracking` only | No | No | No | No | No | No |
| `sor_artwork` only | No | No | No | No | No | No |
| Both installed | Yes | Yes | Yes | Yes | Yes | Yes (on install) |
| + `sor_tracking_asset_paradigm` | Yes | Yes | Yes | Yes | Yes | Yes + qty column suppression |

---

## Special Concerns

### `post_init_hook` vs `post_migrate`

The serial tracking migration only runs on first install (`post_init_hook`), not on upgrade. This is intentional — the migration sets a one-time default and should not overwrite manual tracking mode changes made after initial setup. If a future sprint requires re-running the migration on upgrade, a migration script in `migrations/` must be used (not `post_migrate` — which is not a valid Odoo manifest key, see `odoo_19_breaking_changes.md`).

### `res.config.settings.execute()` in the hook

Enabling serial tracking uses `env['res.config.settings'].create({}).execute()` with `group_stock_production_lot = True`. This is the Odoo-idiomatic way to activate feature groups — it handles all side-effects (access rules, field visibility) that direct `ir.group` manipulation would miss. The settings object is not stored; it is created solely to call `execute()`.

### `has_group` unreliable in TransactionCase tests

`env.user.has_group('stock.group_stock_production_lot')` returns `False` in `TransactionCase` even after the `post_init_hook` activates the group, because group membership is checked against a different cache layer. Tests for serial tracking correctness use ORM field assertions rather than `has_group` checks.

### `column_invisible` in `MovesListRenderer` — only `parent.*` references work

Odoo 19's `MovesListRenderer` evaluates `column_invisible` expressions against a restricted context that contains only static values (`True`/`False`/`1`/`0`) and `parent.*` references (properties of the parent `stock.picking` record). Bare field references to `stock.move` fields — including `state`, `has_tracking`, and any other field even if declared in the arch with `column_invisible="True"` — raise:

```
EvalError: Can not evaluate python expression: (bool(state != 'draft'))
Error: Name 'state' is not defined at MovesListRenderer.evalColumnInvisible
```

All `column_invisible` expressions on the Operations list must use `parent.<field>` form. The `invisible` per-row attribute has full row field access and can reference `has_tracking`.

### `sor_draft_lot_name` avoids auto-advance in Draft

Setting `quantity = 1` on a `stock.move` (from `_onchange_product_id`) triggers `_recompute_state()` which creates a `stock.move.line`. Creating a ML in Draft causes Odoo's availability mechanism to see the demand as fully reserved, transitioning the picking from Draft to Ready (assigned). Using a Char field on `stock.move` (`sor_draft_lot_name`) stores the staff-entered serial without creating any ML. No `stock.move.line` is created until `action_confirm()` runs.

### `stock.move` has no `name` field in Odoo 19

`stock.move._rec_name = 'reference'` — there is no `name` field. Tests that create `stock.move` records must not pass `'name': '...'`. This raises `ValueError: Invalid field 'name' in 'stock.move'`.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init \
  -u sor_tracking_artwork
```

---

## Story Reference

`.backlog/current/Movement Layer Completion/stories/04_Artwork-Movement-UX.md` — serial tracking UX (BUG-14 through BUG-19 fixes)

`.backlog/previous/Track A/12 Movement Enhancements/stories/06_Tracking-Bridge-Modules.md` — original bridge delivery
