# SOR Lotting — Knowledge Base

## Overview

`sor_lotting` is a horizontal SOR base module that provides the `sor.lot` model — the central catalogue entry for an auction sale. A lot links a product (the physical object being sold) to its system reference, catalogue number, financial estimates, reserve price, state lifecycle, and sale outcome.

**What this module does:**
- Provides the `sor.lot` model with a system-generated lot reference, optional catalogue lot number, five-state lifecycle with action buttons, monetary estimates, reserve, consignor and buyer party fields, and multi-company isolation.
- Exposes a user-facing **Lots** menu for direct record management.
- Computes `break_even_value` as a proxy for auction house profitability (reserve price in the base module; fee-adjusted value added by `sor_commercial_auction_house`).
- Assigns a per-company `LOT/YYYY/NNNNN` sequence reference automatically at record creation.
- Tracks state changes via chatter (`mail.thread` + `mail.activity.mixin`); every state transition is logged automatically.

**What this module does NOT do:**
- Link lots to a specific auction event — that association is added by the `sor_events_auction` D2 bridge module.
- Implement buyer's premium, seller's fee, or any commercial fee structure — fee data is added by downstream commercial modules.
- Assign a catalogue lot number (`lot_number`) — this is left to the auctioneer at cataloguing time and is not required.

**Depends on:** `product`

---

## Key Fields and Models

### sor.lot

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `lot_reference` | Char | Yes | `'New Lot'` (replaced by sequence on create) | System-generated `LOT/YYYY/NNNNN`; readonly after creation; `copy=False` |
| `lot_number` | Char(10) | No | — | Catalogue number assigned by the auctioneer; optional; editable in Draft and Catalogued states |
| `lot_title` | Char | No | — | Human-readable title for the lot (e.g. artwork title); searchable via `_name_search`. `readonly="state != 'draft'"` — locks once Catalogued, since this is the moment its content is committed to the printed catalogue (Auction MVP Refinements Story 05). Hidden entirely (`invisible="1"`) when `sor_lotting_base` is installed (a vertical module is present) — the vertical's own title/description mechanism takes over. |
| `lot_description` | Html | No | — | Rich-text lot description for catalogue copy. Same `readonly="state != 'draft'"` locking as `lot_title`, for the same reason (Story 05). Also hidden by `sor_lotting_base` when a vertical is installed. |
| `lot_item_name` | Char | — | — | Computed; `store=False`; returns `product.name` or `lot_title` — used for display in lists |
| `product_id` | Many2one → `product.template` | No | — | Domain: `type != 'service'`; the physical object being sold |
| `consignor_id` | Many2one → `res.partner` | No | — | The consignor (vendor/seller) of this lot; `check_company=True` |
| `buyer_id` | Many2one → `res.partner` | No | — | The buyer who won the lot; set when the lot is Sold; `check_company=True` |
| `company_id` | Many2one → `res.company` | Yes | `env.company` | Owning company; read-only on form (multi-company guard) |
| `currency_id` | Many2one → `res.currency` | — | — | Related from `company_id.currency_id`; `store=True`; required by Monetary widgets |
| `estimate_low` | Monetary | No | — | Pre-sale low estimate |
| `estimate_high` | Monetary | No | — | Pre-sale high estimate |
| `reserve_price` | Monetary | No | — | Minimum hammer price before the lot is sold |
| `no_reserve` | Boolean | No | `False` | Indicates lot sells at any price; independent of `reserve_price` value |
| `starting_bid` | Monetary | No | — | Opening bid price |
| `hammer_price` | Monetary | No | — | Final achieved price at hammer |
| `break_even_value` | Monetary | — | — | Computed; `store=False`; currently equals `reserve_price`; see Methods |
| `state` | Selection | Yes | `'draft'` | Five-stage lifecycle with `tracking=True`; see State Lifecycle section below |
| `auction_result` | Selection | No | — | Stored when lot is sold or passed: `'sold'` or `'passed'`; persists through `is_collected` transition; `copy=False` |
| `is_collected` | Boolean | No | `False` | Set to `True` by `action_mark_collected()`; state remains unchanged (Sold or Passed); `copy=False`; `tracking=True` |
| `collected_display` | Char | — | — | Computed; `store=False`; returns `'Collected'` when `is_collected=True`, else blank; used in form header |
| `internal_notes` | Html | No | — | Rich-text internal staff notes |

**Model attributes:**
- `_inherit = ['mail.thread', 'mail.activity.mixin']` — chatter and activity tracking enabled
- `_order = 'lot_reference asc'`
- `_check_company_auto = True`
- Constraint: `estimate_low <= estimate_high` (both may be null — checked via `models.Constraint`)

---

## State Lifecycle

Five states. Transitions are enforced by action buttons with guards — invalid transitions raise a `UserError`. State changes are logged automatically via `mail.thread` (`tracking=True` on `state`).

| State | Value | Meaning | Allowed transitions |
|-------|-------|---------|---------------------|
| Draft | `draft` | Lot created; not yet in the catalogue | → Catalogued, → Withdrawn |
| Catalogued | `catalogued` | Lot assigned to a sale catalogue | → Sold, → Passed, → Withdrawn |
| Sold | `sold` | Hammer fell; sold above reserve | `is_collected` flag set via Mark as Collected (terminal state) |
| Passed / Bought In | `passed` | Hammer fell; failed to meet reserve | `is_collected` flag set via Mark as Collected (terminal state) |
| Withdrawn | `withdrawn` | Removed from the sale before going live | (terminal) |

**Collection is a flag, not a state (Sprint 24 — BUG-U13).** The `is_collected` boolean replaces the former `collected` state. Clicking **Mark as Collected** sets `is_collected=True` and `auction_result` ('sold' or 'passed') is already set from the prior transition. The lot state remains `sold` or `passed` — this preserves auction outcome visibility in list views and reports, while the separate "Collected" indicator appears via the `collected_display` computed field in the form header.

**Note on backwards compatibility:** The `action_mark_sold` and `action_mark_passed` guards accept state `'catalogued'` **or** `'live'` to accommodate any lots that were set to `live` state before Sprint 24 removed the `live` selection value. The `live` selection value is no longer displayed in the UI but old records with `state='live'` remain valid and can transition forward.

**Action buttons on the form header:**

| Button | Method | Guard (raises UserError if not met) |
|--------|--------|--------------------------------------|
| Catalogue | `action_catalogue` | State must be `draft` |
| Mark Sold | `action_mark_sold` | State must be `catalogued` or `live` (backwards compat) |
| Mark Passed | `action_mark_passed` | State must be `catalogued` or `live` (backwards compat) |
| Mark as Collected | `action_mark_collected` | State must be `sold` or `passed` |
| Withdraw | `action_withdraw` | State must be `draft` or `catalogued` |

Buttons are shown only when their guard condition can be satisfied (controlled by `invisible` expressions on each button). Both "Mark Sold" and "Mark Passed" appear simultaneously when a lot is Catalogued, giving the auctioneer a choice at the point of outcome recording.

**Deletion guard:** Only Draft lots may be deleted. Attempting to delete a lot in any other state raises a `UserError` citing the lot reference and current state.

---

## Methods

### create (override)

Auto-assigns `lot_reference` from the `ir.sequence` (code `sor.lot`) on record creation. Uses `with_company(company)` to ensure the sequence counter belongs to the record's company, not the user's session company. If no sequence is found, the default `'New Lot'` is retained.

```python
lot.lot_reference  # → 'LOT/2026/00001' (auto-assigned; read-only after creation)
```

### unlink (override)

Raises `UserError` for any lot not in `draft` state. The error message includes the lot reference and the current state label.

### action_catalogue

Transitions `draft` → `catalogued`. Raises `UserError` if the lot is not in Draft state. Also raises `UserError` if any lot in the recordset has no `lot_number` set — a lot number is required before cataloguing. The error names the affected lot references so staff can identify which records need updating before bulk-cataloguing.

### action_mark_sold

Transitions `catalogued` (or `live` — backwards compat) → `sold`. Sets `auction_result = 'sold'`. Raises `UserError` if the lot is in neither valid state.

### action_mark_passed

Transitions `catalogued` (or `live` — backwards compat) → `passed`. Sets `auction_result = 'passed'`. Raises `UserError` if the lot is in neither valid state.

### action_mark_collected

Sets `is_collected = True` on all lots in the recordset. **State does not change** — the lot remains `sold` or `passed`. Raises `UserError` if any lot is not in a valid pre-collected state.

When `sor_lotting_tracking` is installed, this method is extended to also create and auto-validate a Movement Out stock picking.

```python
lot.action_mark_collected()  # → is_collected becomes True; state unchanged; picking created if sor_lotting_tracking installed
```

### action_withdraw

Transitions `draft` or `catalogued` → `withdrawn`. Raises `UserError` if the lot is in any other state.

### action_open_product

Opens the linked `product.template` record in a modal dialog (`target: 'new'`). Triggered by the external-link button inline with the `product_id` field on the form.

### _compute_lot_item_name

Computed field (`store=False`, `@api.depends('product_id', 'lot_title')`). Returns `product_id.name` if a product is set, otherwise `lot_title`. Used in list views and display contexts where a short human-readable label for the lot item is needed.

### _name_search (override)

Extends the standard `_name_search` to search by `lot_reference`, `lot_number`, and `lot_title` in addition to the default `_rec_name` field. This allows users to find lots by typing any of: the system reference (`LOT/2026/00001`), the catalogue number (`42`), or the title text in Many2one dropdowns and search bars.

### _compute_break_even_value

Computed field (`store=False`, `@api.depends('reserve_price')`). In the base module, `break_even_value` equals `reserve_price`. This is a placeholder — the computed value is overridden by `sor_commercial_auction_house`, which adds buyer's premium and seller's fee to produce a fee-adjusted profitability floor.

```python
lot.break_even_value  # → float; equals reserve_price in the base module
```

---

## Configuration

### Per-company lot reference sequence

`sor_lotting` installs a per-company `ir.sequence` (code `sor.lot`) for the `LOT/YYYY/NNNNN` reference format. The sequence is created automatically:

- **At module install:** `post_init_hook` creates a sequence for every company that does not already have one.
- **When a new company is created:** The `res.company.create` override creates a sequence for the new company.
- **Sequence for `base.main_company`:** Seeded by `data/sor_lot_sequence.xml` at install time.

Users can customise their company's sequence (prefix, padding, next number) via **Settings → Technical → Sequences & Identifiers → Sequences** (developer mode required). Find the sequence named `SOR Lot (<Company Name>)`.

Monetary fields use the company's default currency via `currency_id`, which is derived from `company_id.currency_id`.

---

## Lots Menu

**Location:** Lots → Lots (top-level navigation)

Available to all users (`base.group_user`). Shows all `sor.lot` records for the active company. The domain `[('company_id', '=', allowed_company_ids[0])]` on the window action filters to the current company automatically.

**Note on menu placement:** `sor_lotting` creates its own root menu item because no shared SOR navigation root exists at this sprint stage. When the D2 `sor_events_auction` bridge is installed, auction lots will typically be accessed via the Auctions navigation rather than directly.

---

## Building on This Module

`sor_lotting` is extended by bridge modules that connect lots to auction events and commercial workflows.

### Steps to create a lot bridge

1. **Create the bridge module** with `depends=['sor_lotting', '<domain_module>']` and `auto_install=True`.

2. **Extend `sor.lot`** via `_inherit = 'sor.lot'` to add domain-specific fields (e.g. `event_id → sor.event`, `buyer_premium`, `seller_fee`).

3. **Inherit the form view** via `inherit_id` on `sor_lotting.sor_lot_view_form`. The comment `<!-- D2 bridge injection point: auction_id and fee tabs go here -->` in the base form marks the intended XPath target for tabbed extensions.

4. **Extend action buttons** if the bridge introduces additional workflow control. The base form has five lifecycle buttons (`action_catalogue`, `action_go_live`, `action_mark_sold`, `action_mark_passed`, `action_withdraw`). D2 bridges can add further buttons (e.g. for post-sale offer handling) by inheriting the form view and inserting into the `<header>`.

5. **Tests** should assert that bridge-added fields are present when both modules are installed and absent (or ignored) when only `sor_lotting` is installed.

---

## Regression Checks

Run these checks after any change to `sor_lotting` or any module that extends it.

**R1 — Lots list renders without error**
Navigate to Lots → Lots. Confirm the list loads with these columns visible by default: Lot Reference, Lot Number, Item, State, Collected, Reserve, Hammer Price. No JS console errors appear.

**R2 — Create a lot and confirm lot_reference auto-assignment**
Click New. Select any storable product (lot_number is optional — leave it blank). Click Save. Confirm the record saves with `lot_reference` set to a value in the format `LOT/YYYY/NNNNN` (not `New Lot`) and `state = Draft`.

**R3 — Estimate constraint enforced**
Open a lot. Set Low Estimate to 10,000 and High Estimate to 5,000. Click Save. Confirm a database constraint error is raised.

**R4 — State machine action buttons work in sequence**
Create a new lot. Assign a Lot Number (required before cataloguing). Confirm the "Catalogue" button is visible. Click it — state changes to Catalogued. Confirm both "Mark Sold" and "Mark Passed" appear (no "Go Live" button in Sprint 24+). Click "Mark Sold" — state changes to Sold. Confirm "Mark as Collected" button appears. Click it — state remains Sold; the `is_collected` flag is set to True, and "Collected" text appears in the form header next to the statusbar. Confirm no further action buttons are visible (Sold is terminal). Check the chatter: state transition entries appear — one for Draft → Catalogued, one for Catalogued → Sold. The `is_collected` flag change is also tracked in chatter.

**R5 — Withdraw button available from Draft and Catalogued**
Create a new lot. Confirm "Withdraw" button is visible in Draft. Click it — state changes to Withdrawn. Create a second lot, click "Catalogue", then confirm "Withdraw" is still available in Catalogued state. Click it — state changes to Withdrawn.

**R6 — Break-even value equals reserve**
Set Reserve Price to 5,000 on a lot. Confirm Break-Even Value displays 5,000 (read-only computed field in the Financial group).

**R7 — Multi-company isolation**
With two companies active, switch to Company B and navigate to Lots. Confirm only Company B's lots appear.

**R8 — Per-company sequence produces unique references**
Create two lots in succession. Confirm they receive different `lot_reference` values (e.g. `LOT/2026/00001` and `LOT/2026/00002`). Switch to a second company. Create a lot there and confirm the counter is independent (starts at `LOT/2026/00001` for that company, not a continuation of Company A's counter).

**R9 — Deletion guard**
Create a lot. Click "Catalogue". Attempt to delete the catalogued lot (Action → Delete). Confirm a clear error message is raised naming the lot reference and its current state. In Draft state, deletion must succeed without error.

**R10 — Currency_id hidden in list view by default**
Navigate to the Lots list. Confirm no "Currency" column is visible. Open the optional columns menu (top-right of list header) and confirm "Currency" is listed as a toggleable optional column.

**R12 — Hammer Price default-visible; Low/High Estimate hidden but toggleable (Auction Refinements 01, Story 2)**
Navigate to the Lots list. Confirm **Hammer Price** is visible by default (no toggle needed). Confirm **Low Estimate** and **High Estimate** are hidden by default. Open the optional columns menu and enable them — confirm both appear correctly formatted with currency. This applies to the main Lots list; the same Hammer Price default-visibility is verified separately for the Auction event's embedded Lots tab and the Contact form's Consigned Lots tab (see `sor_events_auction` and `sor_lotting_contact_roles` Knowledge Bases).

**R11 — Mark as Collected available from Sold and Passed (not from Catalogued)**
Create a lot and click Catalogue — state becomes Catalogued. Confirm "Mark as Collected" button is NOT visible. Click "Mark Sold" — state becomes Sold. Confirm "Mark as Collected" button appears. Click it — state remains Sold; `is_collected` is set to True; "Collected" text appears in the form header. Repeat with a separate lot via "Mark Passed" — confirm "Mark as Collected" also appears in Passed state and behaves identically (state stays Passed; `is_collected=True`). Confirm the chatter logs each state transition and the `is_collected` flag change automatically.

**R13 — lot_title / lot_description lock at Catalogued (Auction MVP Refinements Story 05)**
On a Draft lot (with no vertical module such as `sor_artwork` installed — these two fields are hidden entirely when one is), confirm Lot Title and Lot Description are editable. Click "Catalogue". Confirm both fields become read-only. `consignor_id` is unaffected by this story and remains editable at every state.

---

## Interoperability

| Module combination | Effect |
|-------------------|--------|
| `sor_lotting` only | `sor.lot` model with full field set, estimates, five-state lifecycle with action buttons and chatter. User-facing Lots menu. No event link. |
| `sor_lotting` + `sor_events` | No change to either module — they are independent horizontals with no bridge yet. |
| `sor_lotting` + `sor_events_auction` (D2) | Bridge auto-installs. Lots gain an `event_id` link to `sor.event` (type=auction). Lot management moves into the Auctions context. |
| `sor_lotting` + `sor_contact_roles` | `sor_lotting_contact_roles` bridge auto-installs. Consignor earned sub-type is assigned when `consignor_id` is set. Partner form gains a Consigned Lots smart button and tab. |
| `sor_lotting` + `sor_tracking` | `sor_lotting_tracking` bridge auto-installs. Mark as Collected creates and auto-validates a Movement Out stock picking; chatter links both records. |
| `sor_lotting` + `sor_contact_roles` + `sor_tracking` | Both bridges active. Consignor sub-type assignment and picking creation both fire on their respective triggers. No interaction between the two bridges. |
| `sor_lotting` + `sor_commercial_auction_house` (future) | Bridge adds fee structures. `break_even_value` is overridden to reflect fee-adjusted profitability floor. |
