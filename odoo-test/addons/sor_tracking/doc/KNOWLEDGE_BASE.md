# Knowledge Base: SOR Tracking

## Overview

`sor_tracking` provides the physical movement infrastructure for external artwork flows. It replaces Odoo's native Inventory application with a purpose-built Movements navigation, adds an `sor_movement_state` lifecycle to `stock.picking`, and delivers an activity dashboard showing current movement pipeline health.

**What this module does:**
- Adds a `Movements` top-level navigation menu replacing the native Inventory menu
- Adds three navigation sub-menus: Movement In (incoming pickings), Movement Out (outgoing pickings), Internal Transfers
- Adds a Movement Activity Dashboard as the first sub-menu item
- Adds `sor_movement_state` (Queued / Ready / Confirmed / Cancelled) to every `stock.picking` — a four-state lifecycle with direction-aware labels and a contextual hint box visible in Queued and Ready states
- Provides direction-aware status labels (Received, Dispatched, Transferred) visible in the list view
- Shows Beneficial Owner (`owner_id`) for Movement In, Movement Out, and Internal Transfers (native Odoo restricts it to incoming only)
- Infers Operation Type automatically from source/destination location selections — staff do not set it manually
- Enables Multi-Location inventory settings on install via `post_init_hook`
- Suppresses the native Inventory top-level menu so only the SOR Movements menu is visible
- Provisions three pool locations per company on install: **Partners/External** (internal), **Vendors/External** (supplier), and **Buyers/External** (customer) — generic staging areas for movements that do not have a specific partner location
- Alerts staff when a movement's declared source location does not match an artwork's recorded current location, allowing the discrepancy to be reviewed before validation proceeds

**What this module does NOT do:**
- It does not define legal agreements, consignments, or ownership records — those belong to Level 1 bridge modules
- It does not implement loan, donation, or auction movement types — those are scoped to future bridge sprints
- It does not define an "overdue" concept — overdue logic requires agreement data (`sor.agreement.is_stale`) which is not available at this layer
- It does not create new operation types — it uses Odoo's native incoming/outgoing/internal types from the warehouse

**Depends on:** `stock` only. No SOR base modules required.

**Level 1 bridges extend this module** by injecting agreement context via the named injection points in the movement form and dashboard views.

---

## Guide 1 — Navigate to Movement In / Movement Out / Internal Transfers

**When to use:** To review, create, or manage movement records.

### Steps

1. Click **Movements** in the top-level navigation bar.
2. In the sub-menu, select:
   - **Dashboard** — movement activity summary
   - **Movement In** — incoming receipts from external partners (artwork arriving)
   - **Movement Out** — outgoing deliveries to external partners (artwork leaving)
   - **Internal Transfers** — movements between internal gallery locations

### Expected outcome

- Each list shows only pickings of the relevant operation type.
- The list displays: Reference, Partner, Scheduled Date, Status (direction-aware label), and Beneficial Owner (optional, shown by default).
- Rows are colour-coded: green for Received/Dispatched/Transferred, grey for Cancelled, default for Queued.

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R1 | Movements top-level menu visible after install | Yes |
| R2 | Native Inventory top-level menu absent | Yes |
| R3 | Movement In sub-menu lists only incoming pickings | Yes |
| R4 | Movement Out sub-menu lists only outgoing pickings | Yes |
| R5 | Internal Transfers sub-menu lists only internal pickings | Yes |
| R6 | Movements root item opens all pickings (no filter) | Yes |

---

## Guide 2 — Create a New Movement

**When to use:** To record an artwork movement in or out of a gallery location.

### Steps

1. Navigate to **Movements → Movement In** (or Movement Out / Internal Transfers).
2. Click **New**.
3. Set **Source Location** — the location the artwork is leaving from. Includes gallery rooms (internal), Artist Studios (internal), External Locations (customer), and the Vendors/External pool location (supplier).
4. Set **Destination Location** — the location the artwork is arriving at.
5. The **Operation Type** field is set automatically based on the location combination — do not change it.
6. The **Contact** field (Receive from / Deliver to) auto-populates from the selected location's linked partner when `sor_locations_external` is installed and the location has a partner linked. Staff can override it manually.
7. Add movement lines (operations tab) specifying the artwork and quantity.
8. Set **Beneficial Owner** if the artwork is owned by an external party (loans, consignments, or internal studio transfers). Visible on Movement In, Movement Out, and Internal Transfers.
9. Click **Save**. The movement is in **Queued** state.

### Expected outcome

- The form header shows the SOR state statusbar (Queued / Confirmed / Cancelled).
- The movement receives a system-generated sequence reference (e.g. `VR1/IN/00008`) on create — the **Reference** field is never 'New' after saving.
- A blue info box appears below the header explaining what action is needed to confirm the movement.
- The Operation Type field is locked (read-only).

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R7 | New movement form opens without pre-selecting an operation type | Yes |
| R8 | Selecting source/destination automatically sets Operation Type | Yes |
| R9 | Operation Type field is read-only on the form | Yes |
| R10 | Both source and destination location fields are visible on all movement types | Yes |
| R11 | Beneficial Owner field visible for Movement In, Movement Out, and Internal Transfers | Yes |
| R12 | Contact field auto-populates from location's linked partner when sor_locations_external is installed | Yes (when installed) |
| R13 | Info hint box visible when movement is Queued | Yes |
| R14 | Info hint box absent when movement is Confirmed or Cancelled | Yes |
| R14a | New movement receives a sequence reference (not 'New' or '/') after saving | Yes — sequence assigned at create() |

---

## Guide 3 — Confirm a Movement

**When to use:** To record that an artwork has been physically received, dispatched, or transferred.

### State machine for confirmation

SOR movements use a four-state lifecycle. The **Confirm** button (the SOR-renamed Odoo validate button) drives the full Queued → Ready → Confirmed sequence:

```
Queued → (click Confirm) → Ready → Confirmed
```

The **Ready** state indicates that demand has been confirmed and items are staged for physical processing. In the normal one-click flow this is an intermediate state — the movement passes through it on its way to Confirmed. It becomes a resting state if the confirmation is interrupted (e.g. the location update wizard is shown and the user dismisses the form without proceeding).

A blue hint box is visible on the form when the movement is Queued or Ready:
- **Queued hint:** Direction-specific instruction (e.g. "This movement is queued. Confirm it once the items have been physically received and checked in.").
- **Ready hint:** *"This movement is staged. Validate it once items have been physically processed."*

### Steps

1. Open the movement record (from the relevant sub-menu list).
2. Verify the movement details are correct (artwork, quantities, locations).
3. Click **Confirm**.
4. If `sor_locations_artwork` is installed and a movement line's declared **source location** does not match the artwork's recorded `current_location_id`, the **Source Location Discrepancy** wizard opens first. It lists the conflicting artworks, their system-recorded location, and the declared source. Click **Proceed** to continue (treating the system record as stale) or **Cancel** to investigate.
5. If no source discrepancy is found (or after the discrepancy wizard is confirmed with Proceed), and the artworks have an existing `current_location_id`, the **Confirm Location Update** dialog opens. It asks whether to update the artwork location to the destination. Click **Proceed** to update or **Cancel** to abort.
6. The `sor_movement_state` transitions to **Confirmed**.

> **Double-confirm prevention:** When the Source Location Discrepancy wizard fires first and the user clicks Proceed, the destination update dialog is automatically suppressed on the second pass. Only one confirmation dialog appears per movement validation.

### Expected outcome

- The SOR statusbar on the form header moves to Confirmed.
- In the list view, the Status column shows the direction-aware label: **Received** (Movement In), **Dispatched** (Movement Out), or **Transferred** (Internal Transfer).
- The row colour turns green in the list view.
- If `sor_locations_artwork` is installed and the artworks have a `current_location_id`, validation updates the artwork's current location to the destination.
- The destination update dialog title reads **Confirm Location Update** — not "Odoo".

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R15 | Confirming a movement transitions sor_movement_state to 'confirmed' | Yes |
| R15a | Movement passes through 'ready' state during the confirm flow | Yes (intermediate) |
| R15b | A movement in 'ready' state shows the Ready hint text | Yes |
| R16 | Confirmed Movement In shows "Received" in the list Status column | Yes |
| R17 | Confirmed Movement Out shows "Dispatched" in the list Status column | Yes |
| R18 | Confirmed Internal Transfer shows "Transferred" in the list Status column | Yes |
| R19 | Confirmed movement row displays in green in the list | Yes |
| R19a | Source location discrepancy wizard fires when declared source ≠ artwork's current_location_id | Yes (when sor_locations_artwork installed) |
| R19b | Destination update dialog title reads "Confirm Location Update" | Yes — SOR-branded |
| R19c | When source discrepancy wizard is confirmed, destination dialog is suppressed (no double-confirm) | Yes |

---

## Guide 4 — Cancel a Movement

**When to use:** When a planned movement is not going ahead.

### Steps

1. Open the movement record in Queued or Ready state.
2. Click **Cancel** in the form header.
3. The `sor_movement_state` transitions to **Cancelled**.

### Expected outcome

- The SOR statusbar shows Cancelled.
- The row colour turns grey in the list view.
- Cancellation is final — a cancelled movement cannot be re-queued, staged, or confirmed.

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R20 | Cancelling a Queued movement transitions to 'cancelled' | Yes |
| R20a | Cancelling a Ready movement transitions to 'cancelled' | Yes |
| R21 | Cancelled movement row displays in grey in the list | Yes |
| R22 | Confirmed movement cannot be cancelled | Yes |

---

## Guide 5 — Create a Return Movement

**When to use:** To reverse a completed Movement In receipt (e.g., artwork returned to the lending partner).

### Steps

1. Open the confirmed Movement In.
2. Click **Return** in the action menu.
3. Odoo creates a reverse outgoing picking with the source and destination locations swapped.
4. The return picking opens in Queued state.
5. If the original movement had a Beneficial Owner set, the return picking carries the same Beneficial Owner.

### Expected outcome

- Return picking starts in Queued state.
- Beneficial Owner from the original movement is present on the return.

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R23 | Return picking created from confirmed Movement In starts in Queued state | Yes |
| R24 | Beneficial Owner from original movement is present on return | Yes |

---

## Guide 6 — Use the Movement Activity Dashboard

**When to use:** To get a quick overview of the current movement pipeline without navigating each list separately.

### Steps

1. Navigate to **Movements → Dashboard**.
2. The dashboard displays stat buttons grouped by movement type:
   - **Movement In** — Queued / Received / Cancelled counts
   - **Movement Out** — Queued / Dispatched / Cancelled counts
   - **Internal Transfers** — Queued count
3. Sections and tiles with zero counts are hidden automatically.
4. Click any count tile to open the filtered list of matching movements.

### Expected outcome

- Counts reflect the current data for the active company.
- Reloading the page shows up-to-date counts.
- Clicking a tile opens the filtered picking list with the correct domain applied.
- No "overdue" concept is present — the dashboard shows state counts only.

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R25 | Dashboard accessible via Movements → Dashboard | Yes |
| R26 | Movement In section shows correct counts per state | Yes |
| R27 | Movement Out section shows correct counts per state | Yes |
| R28 | Internal Transfers section shows Queued count | Yes |
| R29 | Sections with all-zero counts are hidden | Yes |
| R30 | Zero-count tiles are hidden (not shown as clickable links) | Yes |
| R31 | Clicking a count tile opens the filtered picking list | Yes |
| R32 | Dashboard counts are company-scoped — other company records not included | Yes |
| R33 | Page reload shows up-to-date counts | Yes |
| R34 | No "overdue" indicator on the dashboard | Yes |

---

## Guide 7 — Filter Movements by State in the List View

**When to use:** To narrow the movement list to a specific state.

### Steps

1. Open any Movements sub-menu list.
2. Click the **Search** bar and select the dropdown.
3. Under **Filters**, select: **Queued**, **Ready**, **Confirmed**, or **Cancelled**.
4. The list is filtered to matching state records.

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R35 | SOR state filters (Queued / Ready / Confirmed / Cancelled) appear in the search dropdown | Yes |
| R36 | Applying Queued filter shows only queued pickings | Yes |
| R37 | Native Odoo state filters (Draft / Waiting / Ready) hidden in the SOR search view | Yes |

---

## Guide 9 — Delete a Queued Movement

**When to use:** When a newly-created movement was entered by mistake and needs to be removed before it is staged.

### Steps

1. Open the movement record in **Queued** state.
2. Click **Action → Delete** (or use the list view checkbox → Action → Delete).
3. The movement is permanently removed.

### Expected outcome

- The movement is deleted. No entry remains in the list.
- Attempting to delete a Ready, Confirmed, or Cancelled movement raises a clear error message.

> **Why only Queued?** A movement that has been staged (Ready), confirmed, or cancelled represents an activity that has been at least partially actioned or recorded. Deleting such records would destroy the movement audit trail. Only Queued movements — not yet staged — are safe to delete.

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R43 | Deleting a Queued movement succeeds | Yes |
| R44 | Attempting to delete a Ready movement raises UserError | Yes |
| R45 | Attempting to delete a Confirmed movement raises UserError | Yes |
| R46 | Attempting to delete a Cancelled movement raises UserError | Yes |

---

## Guide 8 — Use Pool Locations

**When to use:** When recording a movement where the external party does not have a dedicated location record — for example, an artwork collected from an unnamed vendor, dispatched to a generic buyer address, or held pending partner assignment.

### Pool locations provided

`sor_tracking` provisions three pool locations per company on install:

| Location | Type | Usage |
|----------|------|-------|
| Partners/External | Internal | Generic staging area for internal transfers involving parties without a specific location record |
| Vendors/External | Supplier | Source location for Movement In receipts from unspecified suppliers or vendors |
| Buyers/External | Customer | Destination location for Movement Out dispatches to unspecified buyers or collectors |

All three are children of a company-scoped **External** view location that groups them.

### Steps

1. Navigate to **Movements → Movement In** (or Movement Out).
2. Click **New**.
3. In the **Source Location** field (for Movement In), select **Vendors/External**.
4. Set the destination to the receiving gallery room.
5. Add the movement lines and click **Save**.

### Expected outcome

- The movement is created with Vendors/External as the source location.
- Operation Type is inferred as incoming (Movement In) automatically.
- The Contact field is not auto-populated (pool locations have no linked partner).

### Regression checks

| # | Check | Expected |
|---|-------|----------|
| R38 | Partners/External, Vendors/External, Buyers/External locations exist per company after install | Yes |
| R39 | All three are children of the company-scoped External view location | Yes |
| R40 | Vendors/External appears as a selectable source location in Movement In | Yes |
| R41 | Buyers/External appears as a selectable destination location in Movement Out | Yes |
| R42 | New companies created after install also receive the three pool locations | Yes |

---

## Key Fields and Models

### `stock.picking` — extended by `sor_tracking`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `sor_movement_state` | Selection | `'queued'` | Four-state lifecycle: `queued`, `ready`, `confirmed`, `cancelled`. `copy=False` — not carried to return pickings. `store=True`, indexed. |
| `sor_movement_state_label` | Char (computed) | — | Direction-aware display label. `store=False`. Returns: Queued, Ready, Received (MVI confirmed), Dispatched (MVO confirmed), Transferred (MVT confirmed), Cancelled. |
| `sor_movement_hint` | Char (computed) | — | Contextual instruction text shown when movement is Queued or Ready. `store=False`. Empty when Confirmed or Cancelled. Queued hint is direction-specific (incoming/outgoing/internal). Ready hint: *"This movement is staged. Validate it once items have been physically processed."* |

### `sor.tracking.dashboard` — TransientModel

A read-only dashboard that aggregates movement counts via a single raw SQL query. Each page visit creates a fresh record so counts always reflect current state.

| Field | Type | Notes |
|-------|------|-------|
| `name` | Char | Default: `'Movement Activity'`. Drives the breadcrumb display name. |
| `mvi_queued` | Integer (computed) | Count of incoming pickings in queued state for the active company. |
| `mvi_confirmed` | Integer (computed) | Count of incoming pickings in confirmed state. |
| `mvi_cancelled` | Integer (computed) | Count of incoming pickings in cancelled state. |
| `mvo_queued` | Integer (computed) | Count of outgoing pickings in queued state. |
| `mvo_confirmed` | Integer (computed) | Count of outgoing pickings in confirmed state. |
| `mvo_cancelled` | Integer (computed) | Count of outgoing pickings in cancelled state. |
| `mvt_queued` | Integer (computed) | Count of internal pickings in queued state. |

### `sor.movement.location.confirm` — TransientModel

A confirmation wizard that fires when a validated movement contains artworks with an existing `current_location_id` (requires `sor_locations_artwork`). Presents a confirmation step before Odoo's native validation proceeds. Staff click **Proceed** to update artwork locations.

- `action_open()` returns an `ir.actions.act_window` dict with `name='Confirm Location Update'` — this is the SOR-branded dialog title, replacing the default "Odoo" title.
- `action_proceed()` calls `button_validate()` on the picking with `sor_skip_location_confirm=True` in context, allowing validation to complete without the wizard firing again.
- `action_cancel()` closes the dialog without validating.

### `sor.movement.source.location.confirm` — TransientModel

A discrepancy alert wizard that fires during `button_validate()` when the movement's declared source location does not match the artwork's recorded `current_location_id` (requires `sor_locations_artwork`). Presents one row per discrepant artwork, showing the system's recorded location and the declared source. Staff click **Proceed** to continue validation (treating the system record as stale) or **Cancel** to return and investigate.

| Field | Notes |
|-------|-------|
| `picking_id` | `Many2one('stock.picking')` — the movement being validated |
| `discrepancy_info` | `Text`, read-only — formatted list of discrepancies: artwork name, system-recorded location, declared source |

`action_confirm()` calls `button_validate()` with both `skip_source_location_check=True` **and** `sor_skip_location_confirm=True` in context. The `skip_source_location_check=True` bypasses the source discrepancy check on the second pass; the `sor_skip_location_confirm=True` suppresses the destination location confirmation wizard so that only one dialog fires per validation. `action_cancel()` closes the dialog without validating.

---

## Methods

### `stock.picking._sor_infer_picking_type_id(location_id, location_dest_id)` → `int | False`

Server-side helper that determines the correct Odoo operation type (incoming/outgoing/internal) from the source and destination location usages. Called from:
- `@api.onchange` (`_onchange_sor_infer_picking_type`) — sets `picking_type_id` reactively in the form
- `create()` override — infers when `picking_type_id` absent from the OWL payload (static `readonly="1"` fields are excluded by OWL)
- `write()` override — re-infers when locations change

**Returns:** ID of the inferred `stock.picking.type` record, or `False` if inference is not possible (e.g. both locations are external).

### `stock.picking._sor_movement_state_transition_allowed(from_state, to_state)` → `bool`

Validates state machine transitions. Allowed transitions:

| From | To |
|------|----|
| `queued` | `ready`, `cancelled` |
| `ready` | `confirmed`, `cancelled` |
| `confirmed` | *(terminal — no transitions)* |
| `cancelled` | *(terminal — no transitions)* |

The `write()` override calls this method on every `sor_movement_state` assignment and raises `UserError` if the transition is not allowed.

### `stock.picking.unlink()`

Deletion protection override. Raises `UserError` for any picking whose `sor_movement_state` is not `queued`. Only newly-created (Queued) movements may be deleted; movements that have been staged (Ready), confirmed, or cancelled are permanent records and cannot be removed via the UI or ORM.

**Error message:** *"You can only delete movements that have not yet been staged. Movements in Ready, Confirmed, or Cancelled state cannot be deleted."*

### `stock.picking._get_source_location_discrepancies()` → recordset

Returns the subset of `move_ids` where the move's declared `location_id` does not match the product's recorded `current_location_id` (requires `sor_locations_artwork`). Returns an empty recordset immediately when `current_location_id` is not in `product.template._fields`. Called by `button_validate()` to determine whether the source location discrepancy wizard should be shown.

### `stock.move.line.create()` — owner propagation

`sor_tracking` overrides `stock.move.line.create()` to propagate the movement's `partner_id` as `owner_id` on every newly-created move line that does not already have an `owner_id` set. This ensures that when a Beneficial Owner is set on the movement, all its operation lines inherit the same owner automatically — without requiring staff to assign the owner line-by-line.

The propagation is skipped if `owner_id` is already provided in the create values, or if the picking has no `partner_id`.

An `@api.onchange('move_id', 'picking_id')` method (`_onchange_sor_tracking_owner`) handles the reactive case when a line is created interactively in the form.

### `sor.tracking.dashboard.action_view_mvi_queued(*args)` (and 6 sibling methods)

`@api.model` methods called from stat buttons. Each returns an `ir.actions.act_window` dict for `stock.picking` with a domain filtering to the relevant `picking_type_id.code` and `sor_movement_state`. The `*args` signature absorbs an extra positional argument that Odoo 19's `call_kw` layer passes to `@api.model` methods before stripping.

---

## Configuration

### Multi-Location and Beneficial Owner tracking

`sor_tracking` enables two Odoo inventory settings on install:

| Setting | Effect | Where to find it |
|---------|--------|-----------------|
| Multi-Location (`group_stock_multi_locations`) | Allows separate source/destination location fields on movements | Settings → Inventory → Warehouse |
| Owner Tracking (`group_stock_tracking_owner`) | Enables the Beneficial Owner field on movement forms | Settings → Inventory → Traceability |

These are enabled automatically via `post_init_hook`. They do not require manual configuration.

### Location domain on movement forms

Source and destination location dropdowns are restricted to:
- Internal locations (gallery rooms, studios)
- Customer locations (external consignee/lender locations)
- Supplier locations (external partner locations)

Global virtual Odoo locations (with `company_id = False`) are excluded from dropdowns. The standard `ir.rule` on `stock.location` enforces per-company isolation beyond the domain.

---

## Building on This Module

### Level 1 bridge modules — agreement context

Bridges that add agreement data to movements (e.g. `sor_tracking_legal_agreement`) should:

1. Inject agreement fields into the named group on the movement form:
   ```xml
   <xpath expr="//group[@name='sor_tracking_agreement_info']" position="inside">
       <field name="agreement_id" .../>
   </xpath>
   ```

2. Inject counts into the named sections on the dashboard:
   ```xml
   <xpath expr="//div[@name='sor_tracking_dashboard_external']" position="inside">
       <!-- agreement-aware count tiles -->
   </xpath>
   <xpath expr="//div[@name='sor_tracking_dashboard_agreement_alerts']" position="inside">
       <!-- stale agreement alerts -->
   </xpath>
   ```

The `sor_tracking_agreement_info` group and the two `<div>` injection points are present in all views from the first `sor_tracking` install. Bridges add to them additively — they never replace the base views.

### Unique object movements — quantity suppression

When `sor_asset_paradigm` is installed, the `sor_tracking_asset_paradigm` bridge (auto-installed with both) provides:
- Automatic `product_uom_qty = 1` default for Unique Object paradigm products
- Hidden Demand and Quantity columns in movement lines when all lines are unique objects
- The `sor_all_unique_objects` computed field on `stock.picking` (and on `stock.move` for the Detailed Operations dialog)

See `sor_tracking_asset_paradigm/doc/KNOWLEDGE_BASE.md` for full details.

---

## Interoperability

| Module | When installed with `sor_tracking` | Effect |
|--------|-------------------------------------|--------|
| `sor_locations_artwork` | `current_location_id` present on `product.template` | Validation of movements containing artwork updates `current_location_id` to destination; source location discrepancy wizard fires when declared source ≠ recorded location; destination confirmation wizard fires when artwork already has a location |
| `sor_tracking_artwork` | Bridge with `sor_artwork` (auto-installs) | Serial tracking defaults for artwork products; "Lot/Serial Numbers" → "Serial Numbers" label correction in movement UI |
| `sor_tracking_asset_paradigm` | Bridge with `sor_asset_paradigm` (auto-installs) | Demand and Quantity columns hidden for all-unique-object pickings; `product_uom_qty` auto-defaults to 1 for unique object products |
| `sor_legal_agreement` | `agreement_id` present on `stock.picking` | Agreement context available on movements; `sor_tracking_agreement_info` group receives agreement field injection |
| *(future)* `sor_tracking_legal_agreement` | Bridge with `sor_legal_agreement` | Agreement dashboard indicators; stale agreement alerts in `sor_tracking_dashboard_agreement_alerts` |
