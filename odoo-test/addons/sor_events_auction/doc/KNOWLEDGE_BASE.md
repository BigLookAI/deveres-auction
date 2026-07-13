# sor_events_auction — Knowledge Base

## Overview

`sor_events_auction` is a **bridge module** that connects SOR auction events with their lot catalogues. It activates automatically when both `sor_events` and `sor_lotting` are installed.

The bridge adds auction-specific details to `sor.event` (subtype, sale number, preview dates, lot catalogue), links `sor.lot` records to their parent auction via `auction_id`, introduces the `live` lot state that is only meaningful during a running sale, and provides the **Go Live** action that opens the auction and moves catalogued lots into the live state in a single operation.

**What this module does NOT do:**
- Manage bidding, bid increments, or buyer registration — those belong to `sor_bidding` (planned)
- Calculate buyers' premiums or seller commissions — those belong to `sor_commercial_auction_house` (planned)
- Manage consignment relationships between the house and consignors — that belongs to `sor_consignments`
- Introduce any new top-level model — it extends `sor.event` and `sor.lot` only

**Dependencies:**

```
sor_events          sor_lotting
      \                  /
       \                /
   sor_events_auction   (auto_install=True)
```

Neither parent is modified. The bridge activates automatically when both parents are present.

---

## Key Fields and Models

### sor.event — fields added by the bridge

| Field | Type | Description |
|-------|------|-------------|
| `auction_subtype` | Selection | Auction format: `live` (Live), `online_only` (Online Only), `hybrid` (Hybrid). Optional — not required at record creation. |
| `sale_number` | Char | External sale reference number assigned by the auction house (e.g. "SP-2026-01"). Free-form text; not system-generated. |
| `preview_start` | Datetime | Start of the public preview period before the sale. Optional. |
| `preview_end` | Datetime | End of the public preview period. Optional. |
| `lot_ids` | One2many → `sor.lot` | All lots assigned to this auction via `auction_id`. Read-only from the event's perspective — lots are assigned by writing `auction_id` on the lot record. |
| `lot_count` | Integer (computed) | Count of lots in `lot_ids`. `store=False` — always computed fresh, never cached. Drives the Lots smart button on the event form. |

**Note on pending count fields:** `psa_pending_count`, `posa_pending_count`, `vss_pending_count`, and `invoice_pending_count` are NOT provided by this bridge. They are added by `sor_auction_documents` and `sor_buyer_invoice_auction_house` respectively when those modules are installed. This bridge provides the lot-event linkage that those counts depend on, but does not own the fields.

### sor.lot — fields added by the bridge

| Field | Type | Description |
|-------|------|-------------|
| `auction_id` | Many2one → `sor.event` | The auction this lot belongs to. Optional — a lot may exist without an auction assignment. Domain restricts the picker to events of type `auction`. `check_company=True` prevents cross-company assignments at the ORM level. `ondelete='restrict'` — an auction with assigned lots cannot be deleted. |
| `state` (extended) | Selection | The bridge adds the `live` value via `selection_add`. `live` appears in the statusbar between `catalogued` and `sold`. Without `sor_events_auction` installed, `live` is absent from the `state` selection. |

### Unique constraint — lot number within auction

The bridge enforces `UNIQUE(auction_id, lot_number)` on `sor.lot`. Attempting to create two lots with the same `lot_number` in the same auction raises a database constraint error. The constraint only applies when both `auction_id` and `lot_number` are non-null — lots without an auction or without a number are not restricted.

---

## Methods

### action_catalogue() override

**Model:** `sor.lot` (via `_inherit`)

**What it does:**

Before delegating to `super()`, checks whether the lot is assigned to an auction and whether that auction's `status` is `active`. If both are true, raises a `UserError` with a message naming both the lot and the auction.

This guard prevents a lot from being added to a sale catalogue after the auction has already opened for bidding. Lots must be catalogued before Go Live.

**Draft lots without an auction** — not affected. The guard only fires when `auction_id` is set and the auction is Active.

---

### action_catalogue_selected_lots() (Auction MVP Refinements Story 04)

**Model:** `sor.lot`

**What it does:** `self.filtered(lambda lot: lot.state == 'draft').action_catalogue()` — catalogues every Draft lot in the recordset, silently skipping any non-Draft lots in the selection (no error, no state change to them). Bound as a `<header>` button on the dedicated Auction Lot list view (see Views below), not as a global server action.

**Why a header button, not a server action:** `ir.actions.server.binding_model_id` has no per-view scoping mechanism — a server action bound this way appears in the Action menu of *every* list view for the model, regardless of which view opened it. The previous design (`action_catalogue_all_lots`, a global server action with a runtime `default_auction_id` context guard) has been removed entirely. A list-view `<header>` button is scoped only to the specific view it is declared in — the correct native mechanism for "this action only makes sense in this one context."

**Header buttons cannot be gated on selected-row state:** Odoo does not expose the current selection's field values to a header button's `invisible` expression, so the button remains visible/clickable even when the selection includes only already-Catalogued or Sold lots. This is why the method above must be defensive (filter to Draft before acting) — the safeguard lives in Python, not the view. See `odoo_conventions/view_patterns.md`.

---

### action_go_live()

**Model:** `sor.event`

**Signature:** `def action_go_live(self)`

**What it does:**

1. Raises `UserError` if the event's `status` is not `published`. The error message includes the event name and its current status label.
2. Sets `event.status = 'active'`.
3. Posts a chatter message: "Auction opened — Go Live triggered."
4. Filters `event.lot_ids` to only those with `state == 'catalogued'`.
5. If any catalogued lots exist, writes `{'state': 'live'}` directly on those lot records.
6. Posts a second chatter message with the count of lots transitioned.

**Draft lots:** Lots in `draft` state are deliberately excluded. A draft lot is not yet curated into the catalogue and should not be surfaced to bidders. It remains in `draft` after Go Live.

**Why direct write instead of a lot action method:** The `live` state is introduced by this bridge via `selection_add` — no corresponding `action_go_live()` method exists on `sor.lot` itself. Calling a method that does not exist on the base model would break a `sor_lotting`-only install. The direct `write({'state': 'live'})` is the correct pattern for bridge-owned state values.

**Pre-condition guard:** The `published` check is at the model layer, not just the view. The Go Live button in the UI is visible on both `draft` and `published` auction events so that staff see a clear error message rather than a silently hidden button. This is consistent with Odoo's standard pre-condition error pattern for action buttons.

---

## Configuration

No configuration is required. `sor_events_auction` is a `auto_install=True` bridge — it activates automatically when both `sor_events` and `sor_lotting` are installed. There is no Settings toggle, no `post_init_hook`, and no initial data to seed.

When the bridge installs, the Auctions navigation menu appears in the SOR business navigation sidebar (sequence 110, before the Lots menu at sequence 120).

---

## Developer Menu

`sor_events_auction` does not register any items under Settings → Technical → SOR. The bridge adds no rule registries, paradigm tables, or configurable admin records. All bridge behaviour is intrinsic to the field definitions and view inheritance.

---

## Building on This Module

If a subsequent bridge or module needs to extend auction-lot behaviour — for example, to add bidding data or commercial fee fields — follow this pattern:

1. **Depend on `sor_events_auction`** (not on `sor_events` + `sor_lotting` separately). The bridge is the correct dependency point because your module's features are only meaningful when the events-auction linkage already exists.

2. **Extend `sor.lot` via `_inherit`** to add fields (e.g. `bid_count`, `buyer_premium`). The `auction_id` field is already present — no need to re-declare it.

3. **Extend `sor.event` via `_inherit`** if you need event-level fields (e.g. `total_hammer_value`, `buyer_registration_ids`).

4. **Add state values carefully.** The `state` field on `sor.lot` now includes `live` from this bridge. If your module adds further states (e.g. `pending_payment`), use `selection_add` with `ondelete` declared. Confirm the intended position in the statusbar by reading the current statusbar_visible patches in `sor_events_auction_views.xml` and extending them in your own view patch.

5. **Do not modify `_auction_lot_number_unique`.** This constraint is owned by `sor_events_auction`. If you need an additional uniqueness scope (e.g. per sale number), add a separate `models.Constraint` in your own model extension.

6. **View injection points.** The `sor.lot` form view has a comment marking the D2 bridge injection point (before the `<notebook>`). The `sor.event` form has a `button_box` div injected by this bridge. Further bridges can add stat buttons to that div using additional `<xpath expr="//div[@name='button_box']" position="inside">` patches.

7. **The dedicated Auction Lot list view (`sor_lot_view_list_auction_dedicated`).** A `mode="primary"` view inheriting `sor_lotting.sor_lot_view_list`, reached only via the event's "Lots" stat button — not the general Lots list. Bulk actions that only make sense within a single auction's context (like "Catalogue Selected Lots") belong on this dedicated view's `<header>`, not as a globally-bound server action. **Before adding a field via XPath to this view, check whether an existing extension already contributes it** — `sor_lot_view_list_auction_id` (the pre-existing patch adding `auction_id` to the *general* Lots list) is automatically baked into this dedicated view's combined arch, since Odoo resolves a `mode="primary"` view's combined arch from the true root of the whole inheritance chain and applies every active extension-mode view along it, not just ones on this view's own direct ancestor path. Re-adding `auction_id` via a second XPath here would produce a duplicate field. Verify via `env.ref('sor_events_auction.sor_lot_view_list_auction_dedicated').get_combined_arch()` in the shell before assuming a field is missing.

---

## Regression Checks

These checks verify that `sor_events_auction` continues to work correctly after any future change.

**R1 — Auction event fields visible**

1. Navigate to **Auctions** in the SOR sidebar.
2. Open or create an auction event.
3. Click the **Auction Details** tab.
4. Confirm the following fields are visible: Auction Subtype, Sale Number, Preview Start, Preview End.

**R2 — Lots stat button appears on auction events only**

1. Open an auction event. Confirm the **Lots** stat button appears in the form header area.
2. Open an exhibition event (create one if needed). Confirm the **Lots** stat button is absent.

**R3 — Lot assignment via auction_id**

1. Navigate to **Lots** → open any lot.
2. Confirm the **Auction** field is present on the form.
3. Assign the lot to an existing auction event. Save.
4. Open the auction event. Confirm the lot count increments by 1 and the lot appears in the Auction Details tab.

**R3b — Embedded Lots tab shows Hammer Price (Auction Refinements 01, Story 2)**

1. Open an auction event with at least one lot assigned.
2. Click the **Lots** tab (the embedded list, not the Lots stat button popup).
3. Confirm a **Hammer Price** column is visible by default, alongside Lot Number, Item, State, and Reserve.

**R4 — Duplicate lot number within same auction raises an error**

1. Open an auction event. Note its name.
2. Create a lot, assign it to that auction, and set Lot Number to `001`. Save.
3. Create a second lot, assign it to the same auction, and set Lot Number to `001`.
4. Attempt to save. Confirm a constraint error is raised.
5. Change the Lot Number on the second lot to `002`. Confirm it saves successfully.

**R5 — Go Live button pre-condition guard**

1. Create a new auction event in Draft status.
2. Confirm the **Go Live** button is visible on the form header.
3. Click **Go Live**. Confirm a UserError message appears stating the auction must be Published first.
4. Click **Publish** (or use the `action_publish` method) to move the event to Published.
5. Click **Go Live**. Confirm the event status changes to Active.

**R6 — Go Live cascades catalogued lots to live, excludes draft lots**

1. Open a Published auction event that has at least one Catalogued lot and one Draft lot.
2. Note the state of each lot.
3. Click **Go Live**.
4. Confirm the Catalogued lot is now in **Live** state.
5. Confirm the Draft lot remains in **Draft** state.

**R7 — live state appears in the lot statusbar**

1. Open any lot that is assigned to a Published or Active auction.
2. Confirm the state statusbar shows: Draft → Catalogued → Live → Sold / Passed / Withdrawn.

**R8 — Auctions navigation menu**

1. Confirm the **Auctions** menu item appears in the SOR navigation sidebar.
2. Confirm the sub-items **Live**, **Upcoming**, and **Past** are present.
3. Navigate to **Upcoming**. Confirm only auction events with status `draft` or `published` are shown.
4. Navigate to **Past**. Confirm only auction events with status `closed` or `archived` are shown.

**R9 — Dedicated Auction Lot view scoping (Auction MVP Refinements Story 04)**

1. Open an auction event's Lots tab (via the "Lots" stat button). Confirm `auction_id` and `hammer_price` columns are present, and selecting Draft lots and clicking "Catalogue Selected Lots" (in the list header) transitions them to Catalogued.
2. Navigate to the general Lots list (not via any event). Select one or more lots and open the Action menu. Confirm "Catalogue Selected Lots" is **not** present, under any selection.
3. Attempting to catalogue a selected lot with no `lot_number` still raises the same clear error as before.
4. Selecting a mix of Draft and already-Catalogued/Sold lots and clicking "Catalogue Selected Lots" catalogues only the Draft ones — no error, no change to the others (the button itself cannot be hidden based on selection; the Python method is defensive instead).

---

## Interoperability

| Module combination | Effect |
|--------------------|--------|
| `sor_events` only | Exhibition and auction event model. No lot catalogue fields. No auction subtype. |
| `sor_lotting` only | Lot management with six-state lifecycle (draft, catalogued, sold, passed, withdrawn). No `live` state. No `auction_id` field. |
| Both installed | `sor_events_auction` auto-installs. `auction_id` appears on lots. `live` state added. Auction Details tab and Go Live action available on auction events. Auctions menu created. |
| `sor_events_auction` + `sor_bidding` (planned) | Bidding data linked to lots. Bid count smart button on lot form. |
| `sor_events_auction` + `sor_commercial_auction_house` (planned) | Buyer's premium and seller fee fields on lots. Break-even value computed with fee data. |
