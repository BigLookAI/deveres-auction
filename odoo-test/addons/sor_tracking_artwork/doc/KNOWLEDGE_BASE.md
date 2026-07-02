# Knowledge Base: sor_tracking_artwork

## What does this module do?

`sor_tracking_artwork` is the bridge module that activates when both **SOR Tracking** and **SOR Artwork** are installed. It has four responsibilities:

### 1. Serial Number Tracking Defaults

Artwork products are unique physical objects — each piece is one-of-a-kind. Serial number tracking (one serial number per unit) is the correct Odoo tracking mode for artworks. This bridge:

- Sets `tracking = 'serial'` as the default when a new artwork product is created (via `default_get`)
- Runs a migration on install that sets `tracking = 'serial'` on all existing artwork products
- Enables the Odoo serial tracking feature group at install so serial number fields are visible in the UI

### 2. Serial Number Assignment — Draft Entry, Auto-Assignment, and Unique-Object Integrity

Each artwork product is a unique physical object with exactly one serial number, forever. Once a `stock.lot` exists for an artwork product, all subsequent movements for that product must use the same lot — a second distinct serial for the same artwork is never created.

#### Draft state — manual serial entry via `sor_draft_lot_name`

In Draft state, the movement Operations list shows an editable **Serial Number** text column (`sor_draft_lot_name`, a Char field on `stock.move`). Staff may type a serial number directly in this column. The value is stored on the move only — no `stock.move.line` or `stock.lot` record is created in Draft. The movement stays in Draft; auto-advance to Ready is avoided entirely.

If staff leave the field blank in Draft, that is also valid — the serial is auto-assigned from the `sor.artwork.serial` sequence at Mark as Todo time.

#### Mark as Todo — `action_confirm()` pre-creation

When staff click **Mark as Todo**, `action_confirm()` runs the following sequence before calling `super()`:

1. For each move with `sor_draft_lot_name` set: look up whether a `stock.lot` already exists for `(product_id, company_id)`. If one exists, reuse it. If not, create a new `stock.lot` using the staff-entered name and assign it.
2. Clear `sor_draft_lot_name` on the move.
3. Call `super().action_confirm()`. Odoo's `_action_assign` creates `stock.move.line` records. The `stock.move.line.create()` override finds the existing lot (from step 1) and reuses it — no new sequence value is consumed.
4. A post-confirm loop handles moves that `_action_assign` did not cover (manual reservation type): creates one `stock.move.line` per unassigned unique-object serial-tracked artwork move.

For moves with no `sor_draft_lot_name` entered: the `stock.move.line.create()` override auto-assigns from the `sor.artwork.serial` sequence at step 3.

#### Unique-object serial integrity (existing-lot lookup)

In both `stock.move.line.create()` and `_onchange_sor_artwork_serial`, before consuming a sequence value, the bridge searches for an existing `stock.lot` for `(product_id, company_id)`. If one is found, it is reused (`lot_id` set) — no new serial is generated. This ensures exactly one serial exists per artwork product across all movements, regardless of how many pickings are created for it.

The sequence format is `SN/YYYY/NNNNN` (e.g. `SN/2026/00001`). Each company has its own independent counter.

The **BUG-08 guard** additionally skips auto-assignment in `create()` if any other ML on the same parent `stock.move` already has a serial — preventing a second sequence value being consumed when Odoo's `_action_done()` creates "done" move lines for a move that already has a serial from the demand stage.

### 3. Ghost Move Line Deletion Before Confirmation

Opening the Detailed Operations dialog on a draft movement and saving without confirming can leave "ghost" move lines: lines with `lot_name` set but `lot_id = False` and `quantity = 0`. These stale lines interfere with `_action_confirm`'s internal availability assignment: `_action_assign` sees the ghost ML contributing 0 quantity, creates a second ML for the full demand quantity, and the BUG-08 guard then blocks serial assignment on the new ML.

The `action_confirm()` override deletes ghost MLs (filter: `lot_name` set, `lot_id = False`, `quantity = 0`) as the first step inside `action_confirm()`, before the `sor_draft_lot_name` pre-creation and before `super().action_confirm()`. This ensures `_action_assign` always works with a clean state.

### 4. Serial Number Column on the Main Movement Form

Staff assign serial numbers directly on the main movement form — in the Operations list alongside the artwork name — without needing to open the Detailed Operations modal. The Operations list shows different columns depending on the picking state:

| Picking state | Column shown | Field | Widget |
|---|---|---|---|
| Draft | **Serial Number** (editable text) | `sor_draft_lot_name` on `stock.move` | Plain char input |
| Ready (assigned) or later | **Serial Number** (lot tag, non-editable) | `lot_ids` on `stock.move` | Many2many tags, `no_create` |

In Draft, staff type a serial directly into the text cell. At Mark as Todo (`action_confirm`), the text entry is converted to a `stock.lot` and the column switches to the read-only `lot_ids` tags view. Exactly one column is visible at any time — `sor_draft_lot_name` is hidden when the picking is not in Draft; `lot_ids` is hidden when the picking is in Draft.

### 3. Traceability Smart Button on Artwork Product Forms

The artwork product form carries a **Traceability** smart button that opens a list of all completed `stock.move.line` records for this artwork. This replaces the native Odoo "Lot/Serial Numbers" kanban view, which is not suitable for the art market use case.

- Available on all products with the Unique Object asset paradigm (`sor_asset_paradigm` + `sor_artwork` combination)
- `sor_movement_count` (computed Integer) drives the button count
- `action_view_traceability()` returns the act_window action

### 4. Navigation Fix — Artwork Form Opens Correctly from Movement Links

When staff navigate to an artwork from a movement line (clicking the product link in the Operations tab), Odoo's native navigation would open `product.product` — a form that does not carry SOR artwork customisations. This bridge overrides `product.product.get_formview_action()` so that navigation from any movement line opens the correct `product.template` artwork form.

> **What this module does NOT do:** It does not validate that a serial number is assigned before confirmation (Odoo's native serial tracking validation enforces this). It does not add any fields or computations to the artwork product model beyond `sor_movement_count` — those belong to `sor_artwork`. It does not enforce that the auto-populated serial number is used — staff may override it before confirming.

---

## Prerequisites

Requires both:
- **SOR Tracking** (`sor_tracking`) — provides the physical movement infrastructure
- **SOR Artwork** (`sor_artwork`) — provides artwork product records with `product_type = 'artwork'`

When both are installed, `sor_tracking_artwork` activates automatically. No Settings toggle is required.

> **Composability:** Without this bridge, artwork products default to Odoo's standard tracking mode (`none`), no Traceability smart button appears, the serial number column is absent from the Operations list on movement forms, and navigating from a movement line product link opens the uncustomised `product.product` form.

---

## Guide 1 — Create an Artwork with Serial Tracking

1. Navigate to **Movements → Catalogue** (or **Inventory → Products**) and create a new product.
2. In the new product dialog, select **Product Type: Artwork**.
3. The **Tracking** field is automatically set to **Serial Numbers** — it does not need to be changed.
4. Save the artwork. From this point, each time this artwork is received or dispatched, Odoo requires a serial number to be assigned.

> **Existing artworks:** Serial tracking is applied to all existing artwork products on module install. No manual update is needed.

---

## Guide 2 — Assign a Serial Number on the Main Movement Form

Staff assign serial numbers directly on the movement form without opening the Detailed Operations modal. The serial column behaves differently in Draft versus Ready state.

**In Draft state:**

1. Navigate to **Movements → Movement In** (or Movement Out / Internal Transfers) and open the movement.
2. In the **Operations** tab, locate the artwork line.
3. The **Serial Number** column shows a blank editable text field. Optionally type a serial number directly in the cell to pre-assign it. Save — the movement stays in Draft.

**At Mark as Todo:**

4. Click **Mark as Todo**.
5. If a serial was entered in step 3, it is converted to a `stock.lot` (or the existing lot for this artwork is reused if it already has one). The Serial Number column switches to show the lot tag.
6. If the serial field was left blank, a serial from the `sor.artwork.serial` sequence (`SN/YYYY/NNNNN`) is auto-assigned. The lot tag appears in the Serial Number column.

**In Ready state:**

7. The serial number is shown as a non-editable tag in the Serial Number column.
8. Click **Validate** to complete the movement.

> **Unique object constraint:** Each artwork has exactly one serial number in the system. If the artwork already has a serial from a previous movement, that same serial is automatically reused — a new sequence value is never consumed for an artwork that already has one.

---

## Guide 3 — View Artwork Traceability

1. Open the artwork product record.
2. In the product header, click the **Traceability** smart button.
3. A list of all completed movement operations (`stock.move.line`, state = done) for this artwork opens, showing the serial number, source location, destination location, and movement date.

> **Button count:** The Traceability button shows the count of completed movement line records for this artwork. A new artwork with no confirmed movements shows 0.

---

## Key fields and methods

### `product.template`

| Field / Method | Type / Signature | Purpose |
|----------------|-----------------|---------|
| `sor_movement_count` | Integer (computed, `store=False`) | Count of completed `stock.move.line` records where `product_id.product_tmpl_id = self`. Drives the Traceability smart button count. |
| `default_get` | `(fields_list)` | Sets `tracking = 'serial'` when `product_type` defaults to `'artwork'` via context. Only activates when context key `default_product_type = 'artwork'` is present. |
| `action_view_traceability` | `()` → `dict` | Returns an `ir.actions.act_window` for `stock.move.line` filtered to `state='done'` and `product_id.product_tmpl_id = self.id`. Name: `'Traceability'`. |

### `product.product`

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get_formview_action` | `()` → `dict` | Override: for artwork `product.product` variants, returns a form action targeting `product.template` at the artwork's template ID. Non-artwork products fall through to Odoo's standard behaviour. Fixes the navigation issue where clicking a product link on a movement line opened the SOR-uncustomised `product.product` form. |

### `stock.move` (extended)

| Field | Type | Purpose |
|-------|------|---------|
| `sor_draft_lot_name` | Char | Temporary serial name for Draft-state manual entry. Staff type a serial here in Draft; `action_confirm()` converts it to a `stock.lot` and clears this field at Mark as Todo time. Hidden (`column_invisible="parent.state != 'draft'"`) when the picking is not in Draft. |

The `lot_ids` field (One2many to `stock.lot`) is already present on `stock.move` in Odoo. This bridge surfaces it as a visible column when the picking is in non-Draft states via view inheritance (the native `column_invisible="parent.state == 'draft'"` expression is preserved as-is). No new field is added for `lot_ids`; only the `optional` and `options` attributes are changed.

### `stock.move.line` (extended)

| Method | Purpose |
|--------|---------|
| `create()` override | For unique-object serial-tracked artwork lines: (1) searches for an existing `stock.lot` for `(product_id, company_id)` — if found, reuses it by setting `lot_id`; (2) if no existing lot and picking is in Draft, sets `lot_name` with the next sequence value; (3) if no existing lot and not in Draft, creates a new `stock.lot` and sets `lot_id`. Skips if `lot_id` or `lot_name` is already set (e.g. pre-set by `action_confirm()`). BUG-08 guard: skips if any other ML on the same `move_id` already has a serial (prevents duplicate consumption during `_action_done()`). Uses `with_company(company)` for the correct per-company counter. |
| `_onchange_sor_artwork_serial` | Reactive assignment for the Detailed Operations dialog. Fires on `product_id`/`picking_id` change. Searches for an existing `stock.lot` for `(product_id, company_id)` first — if found, sets `lot_id` directly; otherwise calls `next_by_code` and sets `lot_name`. Same skip conditions as `create()`. |

### `stock.picking` (extended — ghost ML deletion)

| Method | Purpose |
|--------|---------|
| `action_confirm()` override | Sequence: (1) deletes ghost MLs (`lot_name` set, `lot_id=False`, `quantity=0`) to clean stale lines left by the Detailed Operations dialog; (2) for each move with `sor_draft_lot_name` set, looks up or creates a `stock.lot` from the staff-entered name before calling `super()` — so that `_action_assign` finds and reuses the pre-created lot via the `create()` override's existing-lot check; (3) clears `sor_draft_lot_name`; (4) calls `super().action_confirm()`; (5) post-confirm loop creates one ML for any remaining unassigned unique-object serial-tracked moves (manual reservation type — not covered by `_action_assign`). |

### `ir.sequence` — per-company serial sequence

Code: `sor.artwork.serial`  
Format: `SN/%(year)s/NNNNN` (e.g. `SN/2026/00001`)  
Scope: one sequence per company, created at install for all existing companies via `post_init_hook` and for new companies via `res.company.create()` override.  
Users can find and edit their company's sequence via Settings → Technical → Sequences & Identifiers → Sequences (developer mode required).

### `res.company`

A `res.company.create()` override is present but is a passthrough — serial tracking groups are Odoo instance-wide settings, not per-company, so no per-company provisioning is needed.

### `hooks.post_init_hook(env)`

Runs on module install. Calls:
- `_enable_serial_tracking(env)` — enables `group_stock_production_lot` and `group_lot_on_delivery_slip` via `res.config.settings.execute()`
- `_migrate_existing_artworks(env)` — sets `tracking = 'serial'` on all existing artwork products

---

## Configuration

No Settings toggle is required. Serial tracking is enabled automatically on install. The tracking mode on individual artwork products is set automatically when created; it can be changed manually on the product form if needed (not recommended for artworks).

> **Serial tracking group:** `stock.group_stock_production_lot` is activated by the `post_init_hook`. This is an instance-wide Odoo setting. If it is later disabled, serial number fields disappear from the UI but existing serial number records are preserved.

---

## Developer menu

No developer menu entries. This is a pure bridge module with no configurable rules or runtime-togglable settings.

---

## Building on this module

If you are building a module that depends on serial tracking being active for artwork movements:

1. Declare `sor_tracking_artwork` as a dependency (or declare both `sor_tracking` and `sor_artwork` to let the bridge auto-install).
2. Access serial number records via `stock.lot` with `product_id` referencing the artwork's `product.product`.
3. In views that display `stock.move.line` for artwork movements, use `lot_id` for the serial number field on individual move lines.
4. To add items to the artwork product header (e.g. additional smart buttons), inherit the product.template form — the Traceability button is in the `oe_stat_button` area.
5. The `get_formview_action` override on `product.product` is limited to artworks (`product_type == 'artwork'`). Modules adding other product types do not need to work around it.

---

## Regression checks

**R1 — New artwork defaults to serial tracking**
1. Navigate to Movements → Catalogue → New Product.
2. Set Product Type to Artwork.
3. Verify the Tracking field automatically shows "By Unique Serial Number".

**R2 — Existing artworks have serial tracking**
1. Open any existing artwork product.
2. Verify the Tracking field shows "By Unique Serial Number".

**R3 — Traceability smart button on artwork product form**
1. Open an artwork product that has had at least one confirmed movement.
2. Verify the smart button in the header reads "Traceability" (not "Serial Numbers" or "Lot/Serial Numbers").
3. Click the button. Verify a list of `stock.move.line` records opens filtered to state=done for this artwork.

**R4 — Serial number column on main movement form**
1. Open any movement containing an artwork line in Queued state.
2. Verify the Operations tab shows a "Serial Number" column directly on each artwork line.
3. Assign a serial number in that column and confirm the movement. Verify the serial number is saved.

**R5 — Non-artwork products unaffected**
1. Create a new non-artwork storable product.
2. Verify the Tracking field does not default to "By Unique Serial Number".

**R6 — Navigation from movement line opens artwork template form**
1. Open a confirmed movement that contains an artwork line.
2. In the Operations tab, click the product name link on the artwork line.
3. Verify the artwork's `product.template` form opens (with the full SOR artwork layout), not a `product.product` variant form.

**R7 — Non-artwork navigation unaffected**
1. Open a movement containing a non-artwork storable product line (if any).
2. Click the product name link.
3. Verify navigation behaves as standard Odoo — this bridge does not interfere with non-artwork products.

**R8 — Serial Number column in Draft state is a blank editable text field**
1. Create a new Movement In and add an artwork line in the Operations tab.
2. Verify the Serial Number column shows a blank editable text cell (not a pre-populated lot tag).
3. Leave it blank and click Mark as Todo.
4. Verify the Serial Number column now shows a lot tag in `SN/YYYY/NNNNN` format, auto-assigned from Settings → Technical → Sequences → SOR Artwork Serial Number.

**R8b — Manual serial entry in Draft is preserved at Mark as Todo**
1. Create a new Movement In and add an artwork line.
2. In the Serial Number column (Draft state), type a custom serial name (e.g. `MY-SERIAL-001`).
3. Click Mark as Todo.
4. Verify the Serial Number column shows a lot tag with the name `MY-SERIAL-001` (not a sequence-generated value).

**R9 — Serial number can be overridden**
1. On a movement with a pre-populated serial number, change the serial to a custom value.
2. Confirm the movement.
3. Verify the custom serial number (not the auto-populated one) is recorded against the artwork.

**R10 — Per-company sequences are independent**
1. In a multi-company database, create a movement in Company A and note the pre-populated serial (e.g. `SN/2026/00003`).
2. Create a movement in Company B and note the pre-populated serial.
3. Verify the Company B serial comes from Company B's own counter — not continuing from Company A's counter.

**R11 — Ghost move lines cleaned before action_confirm**
1. Create a Movement In with an artwork line.
2. Click the detail icon to open Detailed Operations. Save the form without confirming.
3. Reopen the movement and click Confirm.
4. Verify the movement confirms without error and the artwork receives exactly one serial number.

---

## Interoperability

| Module combination | Effect |
|-------------------|--------|
| `sor_tracking` only | No serial tracking defaults; no Traceability button; native product navigation unchanged |
| `sor_artwork` only | Artwork products exist; no tracking defaults, no Traceability button, no navigation fix |
| `sor_tracking` + `sor_artwork` | This bridge activates: serial tracking default, migration, serial number column on movement form, Traceability smart button, navigation fix for movement → artwork template |
| + `sor_tracking_asset_paradigm` | Quantity columns suppressed for unique-object artworks; serial tracking and Traceability button unchanged |
