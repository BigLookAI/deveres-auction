# Knowledge Base: sor_tracking_asset_paradigm

## What does this module do?

`sor_tracking_asset_paradigm` is the bridge module that activates when both **SOR Tracking** and **SOR Asset Paradigm** are installed. It adapts the movement form for unique-object assets (artworks and other one-of-a-kind items), removing quantity-focused UI elements that have no meaning for objects where quantity is always 1.

### 1. Quantity Column Suppression

For movements where every product line is a unique object (`asset_paradigm = 'unique_object'`), the bridge suppresses:

- The **Demand** column in the movement lines list
- The **Quantity** column in the movement lines list
- The **Demand** group in the Detailed Operations dialog
- The **Quantity** column in the Detailed Operations inner list
- The **Shipping Policy** field (not meaningful for unique-object movements)

These suppressions are conditional — they only apply when **all** lines in the picking are unique objects. A mixed movement (some unique, some standard) retains the full quantity UI.

### 2. Automatic Quantity Defaulting

When a `stock.move` is created for a `unique_object` product without specifying a quantity, the bridge automatically sets `product_uom_qty = 1`. This prevents moves with zero quantity for unique objects. The defaulting applies at:

- `create()` — when a move is created programmatically without a qty
- `@api.onchange('product_id')` — when a user selects a unique-object product in the form
- `_action_confirm()` — safety net before confirmation, in case qty was cleared after creation

> **What this module does NOT do:** It does not prevent users from setting a quantity other than 1 on a unique-object move (e.g. if physically correcting a miscount). It does not add any physical inventory logic. The `sor_all_unique_objects` field is computed at read-time only (`store=False`) and is not used for access control.

---

## Prerequisites

Requires both:
- **SOR Tracking** (`sor_tracking`) — provides `stock.picking` with movement state
- **SOR Asset Paradigm** (`sor_asset_paradigm`) — provides the `asset_paradigm` field on `product.template`

When both are installed, `sor_tracking_asset_paradigm` activates automatically. No Settings toggle is required.

> **Composability:** The full effect of quantity suppression requires `sor_asset_paradigm_artwork` to also be installed (it registers the `unique_object` paradigm value and assigns it to artwork products). Without artwork products having `asset_paradigm = 'unique_object'`, the `sor_all_unique_objects` field will always be `False` and the suppressions will not activate in practice.

---

## Guide 1 — View a Movement with Quantity Suppression Active

1. Navigate to **Movements → Movement In** (or Movement Out / Internal Transfer).
2. Open a movement that contains only artwork lines.
3. The movement lines list shows product, UoM, and status columns — the Demand and Quantity columns are hidden.
4. The Shipping Policy field does not appear in the form header.

For a mixed movement (artworks and non-artwork products), all columns appear as normal.

---

## Key fields and methods

### `stock.picking` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `sor_all_unique_objects` | `Boolean`, computed, `store=False` | `True` when every `stock.move` in this picking has `product_id.asset_paradigm == 'unique_object'` and the picking is non-empty. `False` for empty pickings. |
| `_compute_sor_all_unique_objects` | Method | Iterates `move_ids`; filters to moves with products; checks all paradigms. Depends on `move_ids.product_id.asset_paradigm`. |

### `stock.move` (extended)

| Addition | Type | Purpose |
|----------|------|---------|
| `sor_all_unique_objects` | `Boolean`, computed, `store=False` | Mirrors `picking_id.sor_all_unique_objects`. Needed in the `stock.move` form (Detailed Operations dialog) where the view expression must reference a field on the `stock.move` record. |
| `_compute_sor_all_unique_objects_move` | Method | Returns `picking_id.sor_all_unique_objects` or `False` when no picking. |
| `create` override | Method | Sets `product_uom_qty = 1` for `unique_object` products when qty is absent from the create dict. |
| `_onchange_product_id_sor_tracking_asset_paradigm` | Onchange | Sets `product_uom_qty = 1` and `quantity = 1` when a `unique_object` product is selected in the UI. |
| `_action_confirm` override | Method | Safety net: ensures `product_uom_qty = 1` before confirmation for any `unique_object` move where qty is 0. |

---

## Configuration

No Settings toggle and no developer rule records. The `sor_all_unique_objects` flag is computed dynamically from the `asset_paradigm` values on the products in each picking. To test with suppression active, ensure the picking contains only products with `asset_paradigm = 'unique_object'`.

---

## Developer menu

No developer menu entries. This bridge has no configurable rules.

---

## Building on this module

If you are building a module that reacts differently to unique-object movements:

1. Declare `sor_tracking_asset_paradigm` as a dependency.
2. Use `picking.sor_all_unique_objects` (or `move.sor_all_unique_objects`) in view `invisible` expressions or Python logic.
3. Do not read `asset_paradigm` directly from each move's product — use the pre-computed `sor_all_unique_objects` field to avoid per-record lookups.
4. For new XPath patches on the movement form, inherit `sor_tracking.view_picking_form_sor_tracking` (not Odoo's base form) since `sor_tracking` already inherits the base.

---

## Regression checks

**R1 — Demand column suppressed for all-unique-object picking**
1. Navigate to Movements → Movement In and open or create a movement containing only artwork lines.
2. Verify the Demand column is absent from the lines list.
3. Verify the Quantity column is absent from the lines list.

**R2 — Demand column visible for mixed picking**
1. Navigate to Movements → Movement In and open or create a movement containing both artwork and non-artwork lines.
2. Verify the Demand and Quantity columns are visible.

**R3 — Demand column visible for empty picking**
1. Navigate to Movements → Movement In and create a new (empty) movement.
2. Verify the Demand and Quantity columns are visible (empty picking → `sor_all_unique_objects = False`).

**R4 — Quantity defaulting on create**
1. Via the Odoo shell or a picking form, create a `stock.move` for a unique-object product without specifying a quantity.
2. Verify `product_uom_qty` is 1.

**R5 — Quantity not overridden when explicitly provided**
1. Create a `stock.move` for a unique-object product with `product_uom_qty = 3`.
2. Verify `product_uom_qty` remains 3.

**R6 — Detailed Operations dialog: Demand group suppressed**
1. Open a movement with only unique-object lines.
2. Click the detail icon on a line to open the Detailed Operations dialog.
3. Verify the Demand group (qty fields) is absent.

---

## Interoperability

| Module combination | Effect |
|-------------------|--------|
| `sor_tracking` only | No paradigm awareness; no quantity suppression |
| `sor_asset_paradigm` only | `asset_paradigm` field exists on products; no movement UI changes |
| `sor_tracking` + `sor_asset_paradigm` | This bridge activates: `sor_all_unique_objects` computed field; suppression and defaulting active |
| + `sor_asset_paradigm_artwork` | Artwork products get `asset_paradigm = 'unique_object'`; suppressions now activate for artwork movements |
| + `sor_tracking_artwork` | Serial number tracking on artwork movements; both bridges compose independently |
