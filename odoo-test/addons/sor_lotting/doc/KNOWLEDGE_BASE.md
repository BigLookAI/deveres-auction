# SOR Lotting — Knowledge Base

## Overview

`sor_lotting` is a horizontal SOR base module that provides the `sor.lot` model — the central catalogue entry for an auction sale. A lot links a product (the physical object being sold) to its system reference, catalogue number, financial estimates, reserve price, state lifecycle, and sale outcome.

**What this module does:**
- Provides the `sor.lot` model with a system-generated lot reference, optional catalogue lot number, six-state lifecycle with action buttons, monetary estimates, reserve, and multi-company isolation.
- Exposes a user-facing **Lots** menu for direct record management.
- Computes `break_even_value` as a proxy for auction house profitability (reserve price in the base module; fee-adjusted value added by `sor_commercial_auction_house` in a later sprint).
- Assigns a per-company `LOT/YYYY/NNNNN` sequence reference automatically at record creation.

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
| `lot_number` | Integer | No | — | Catalogue number assigned by the auctioneer; optional; editable in Draft and Catalogued states |
| `lot_suffix` | Char(3) | No | — | Optional alpha suffix (e.g. A, B, C for split lots) |
| `product_id` | Many2one → `product.template` | Yes | — | Domain: `is_storable = True`; the physical object being sold |
| `company_id` | Many2one → `res.company` | Yes | `env.company` | Owning company; read-only on form (multi-company guard) |
| `currency_id` | Many2one → `res.currency` | — | — | Related from `company_id.currency_id`; `store=True`; required by Monetary widgets |
| `estimate_low` | Monetary | No | — | Pre-sale low estimate |
| `estimate_high` | Monetary | No | — | Pre-sale high estimate |
| `reserve_price` | Monetary | No | — | Minimum hammer price before the lot is sold |
| `no_reserve` | Boolean | No | `False` | Indicates lot sells at any price; independent of `reserve_price` value |
| `starting_bid` | Monetary | No | — | Opening bid price |
| `hammer_price` | Monetary | No | — | Final achieved price at hammer |
| `break_even_value` | Monetary | — | — | Computed; `store=False`; currently equals `reserve_price`; see Methods |
| `state` | Selection | Yes | `'draft'` | Six-stage lifecycle; see State Lifecycle section below |
| `internal_notes` | Html | No | — | Rich-text internal staff notes |

**Model attributes:**
- `_order = 'lot_reference asc'`
- `_check_company_auto = True`
- Constraint: `estimate_low <= estimate_high` (both may be null — checked via `models.Constraint`)

---

## State Lifecycle

Six states. Transitions are enforced by action buttons with guards — invalid transitions raise a `UserError`.

| State | Value | Meaning | Allowed transitions |
|-------|-------|---------|---------------------|
| Draft | `draft` | Lot created; not yet in the catalogue | → Catalogued, → Withdrawn |
| Catalogued | `catalogued` | Lot assigned to a sale catalogue | → Live, → Withdrawn |
| Live | `live` | Lot is currently open for bidding | → Sold, → Passed |
| Sold | `sold` | Hammer fell; sold above reserve | (terminal) |
| Passed / Bought In | `passed` | Hammer fell; failed to meet reserve | (terminal in D1) |
| Withdrawn | `withdrawn` | Removed from the sale before going live | (terminal) |

**Action buttons on the form header:**

| Button | Method | Guard (raises UserError if not met) |
|--------|--------|--------------------------------------|
| Catalogue | `action_catalogue` | State must be `draft` |
| Go Live | `action_go_live` | State must be `catalogued` |
| Mark Sold | `action_mark_sold` | State must be `live` |
| Mark Passed | `action_mark_passed` | State must be `live` |
| Withdraw | `action_withdraw` | State must be `draft` or `catalogued` |

Buttons are shown only when their guard condition can be satisfied (controlled by `invisible` expressions on each button). Both "Mark Sold" and "Mark Passed" appear simultaneously when a lot is Live, giving the auctioneer a choice at the point of outcome recording.

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

Transitions `draft` → `catalogued`. Raises `UserError` if the lot is not in Draft state.

### action_go_live

Transitions `catalogued` → `live`. Raises `UserError` if the lot is not in Catalogued state.

### action_mark_sold

Transitions `live` → `sold`. Raises `UserError` if the lot is not in Live state.

### action_mark_passed

Transitions `live` → `passed`. Raises `UserError` if the lot is not in Live state.

### action_withdraw

Transitions `draft` or `catalogued` → `withdrawn`. Raises `UserError` if the lot is in any other state.

### action_open_product

Opens the linked `product.template` record in a modal dialog (`target: 'new'`). Triggered by the external-link button inline with the `product_id` field on the form.

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
Navigate to Lots → Lots. Confirm the list loads, columns are visible (Lot Reference, Lot Number, Suffix, Product, State, Low Est., High Est., Reserve), and no JS console errors appear.

**R2 — Create a lot and confirm lot_reference auto-assignment**
Click New. Select any storable product (lot_number is optional — leave it blank). Click Save. Confirm the record saves with `lot_reference` set to a value in the format `LOT/YYYY/NNNNN` (not `New Lot`) and `state = Draft`.

**R3 — Estimate constraint enforced**
Open a lot. Set Low Estimate to 10,000 and High Estimate to 5,000. Click Save. Confirm a database constraint error is raised.

**R4 — State machine action buttons work in sequence**
Create a new lot. Confirm the "Catalogue" button is visible. Click it — state changes to Catalogued. Confirm "Go Live" button appears. Click it — state changes to Live. Confirm both "Mark Sold" and "Mark Passed" appear. Click "Mark Sold" — state changes to Sold. Confirm no further action buttons are visible (terminal state).

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

---

## Interoperability

| Module combination | Effect |
|-------------------|--------|
| `sor_lotting` only | `sor.lot` model with full field set, estimates, six-state lifecycle with action buttons. User-facing Lots menu. No event link. |
| `sor_lotting` + `sor_events` | No change to either module — they are independent horizontals with no bridge yet. |
| `sor_lotting` + `sor_events_auction` (D2) | Bridge auto-installs. Lots gain an `event_id` link to `sor.event` (type=auction). Lot management moves into the Auctions context. |
| `sor_lotting` + `sor_commercial_auction_house` (future) | Bridge adds fee structures. `break_even_value` is overridden to reflect fee-adjusted profitability floor. |
