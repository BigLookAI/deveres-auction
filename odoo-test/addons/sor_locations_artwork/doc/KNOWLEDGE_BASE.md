# Knowledge Base: sor_locations_artwork

## What does this module do?

`sor_locations_artwork` is the bridge module that activates when both **SOR Locations** and **SOR Artwork** are installed. It has two responsibilities:

### 1. Artwork Location Assignment

Records the current physical location of each artwork — which Room in the gallery, which Artist Studio, or which External Location (a collector's home, a client's premises, a storage facility). This makes it possible to answer at a glance: "Where is this painting right now?"

**Use cases:**
- Commercial gallery: track which room each artwork is hanging in, or which client has it on approval
- Permanent collection: track which gallery space or off-site store holds each object
- Artist studio management: confirm which artworks are currently with a specific artist

> **Note:** Artwork Location Assignment records *where* an artwork is at any given moment. The specific reason for a move (sold, on loan, donated, on consignment) is managed by separate Consignments and Loans workflows.

### 2. Viewing Location UI Cleanup

Suppresses Odoo warehouse logistics UI elements that have no meaning when Viewing Locations are used to manage unique object artworks:

| Suppressed element | Form | Location in UI | Reason |
|--------------------|------|---------------|--------|
| Routes stat button | Viewing Location | Header | Procurement route configuration is irrelevant for artworks |
| Warehouse Configuration tab | Viewing Location | Tabs | Shipment routing and resupply settings do not apply to unique objects |
| Technical Information tab | Viewing Location | Tabs | Internal location IDs and operation types are Odoo logistics internals |
| Putaway Rules stat button | Room / Studio / External Location | Header | Auto-routing rules for incoming stock have no meaning for manually-placed artworks |
| Products stat button | Room / Studio / External Location | Header | Shows quant-based stock counts; artworks use `current_location_id` directly — the Artworks button is the correct entry point |
| Cyclic Counting section | Room / Studio / External Location | Additional Information | Automated periodic inventory counts are irrelevant for unique objects tracked individually |
| Logistics section | Room / Studio / External Location | Additional Information | Removal strategy (FIFO/FEFO/LIFO) applies to fungible stock, not to unique objects |

> **Composability note:** These suppressions belong in this bridge — not in `sor_locations` — because they reflect a decision specific to the *artwork* use case. A future asset bridge (e.g. `sor_locations_furniture`) may make a different decision about whether these elements are needed. `sor_locations` itself remains unopinionated.

---

## Prerequisites

Artwork Location Assignment requires:

- **SOR Locations** must be installed (provides Rooms and Viewing Locations)
- **SOR Artwork** must be installed (provides artwork product records)

When both are installed, the bridge module `sor_locations_artwork` activates automatically. No Settings toggle is required.

> **Composability:** This feature is provided by the `sor_locations_artwork` bridge module. It is only available when both SOR Locations (`sor_locations`) and SOR Artwork (`sor_artwork`) are installed. When either module is absent, the **Current Location** field does not appear on artwork records, and the Artwork Locations dashboard and smart buttons are not present.

---

## Guide 1 — Assign a Location to an Artwork

**When to use:** When an artwork arrives at a location (a Room, a Studio, or an External Location) and you want to record where it is.

### Steps

1. Go to **Inventory → Products → Artwork Locations** (or open the artwork directly from the Products list).
2. Open the artwork record.
3. In the artwork form, locate the **Current Location** field (in the artwork details section).
4. Click the field and search for the location by name.
   - The search list shows internal locations (Rooms, Studios), customer locations (External Locations), and supplier locations (the Vendors/External pool location provisioned by `sor_tracking`).
   - View and transit locations are excluded.
   - Odoo's global virtual accounting locations — **Customers** and **Vendors** (system-wide entries with no company assignment) — are excluded. These are Odoo internal bookkeeping locations, not physical artwork spaces.
5. Select the location.
6. Click **Save**.

### Expected outcome

- The **Current Location** field on the artwork shows the selected location.
- The artwork appears in the location's Artworks count (visible on the Room or Viewing Location form).
- A chatter entry is recorded showing the location change.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R1 | Current Location field visible on artwork form | Yes |
| R2 | Internal (Room) location selectable | Yes |
| R3 | Customer (External) location selectable | Yes |
| R3a | Supplier location (Vendors/External pool) selectable | Yes — `supplier` included in domain since Movement Enhancements sprint |
| R4 | View-type location not selectable | Yes — excluded by domain |
| R5 | Field saves correctly | Yes |
| R5a | Only locations from the same company appear in the picker | Yes — domain filters by company |
| R5b | Attempting to assign a location from a different company raises an error | Yes — `check_company` blocks cross-company assignment |
| R5c | Odoo global virtual locations (Customers, Vendors with no company) do not appear in the picker | Yes — `('company_id', '!=', False)` in domain excludes them |
| R6 | Chatter records the change | Yes |

---

## Guide 2 — Reassign an Artwork to a Different Location

**When to use:** When an artwork moves from one location to another (e.g. from Room A to Room B, or from a Room to an External Location).

### Steps

1. Open the artwork record.
2. Click the **Current Location** field.
3. Select the new location.
4. Click **Save**.

### Expected outcome

- The **Current Location** field updates to the new location.
- The previous location's Artworks count decreases; the new location's count increases.
- A chatter entry records the reassignment (showing old value → new value).

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R7 | Field updates to new location after save | Yes |
| R8 | Old location count decreases | Yes |
| R9 | New location count increases | Yes |
| R10 | Chatter shows the change | Yes |

---

## Guide 3 — Remove a Location Assignment

**When to use:** When an artwork's location is no longer known, or when it is being removed from all locations (e.g. pending transport).

### Steps

1. Open the artwork record.
2. Click the **Current Location** field.
3. Clear the field (click the × icon next to the selected location, or delete the text).
4. Click **Save**.

### Expected outcome

- The **Current Location** field is blank.
- The artwork appears in the "No Location Assigned" filter in the dashboard.
- The previous location's Artworks count decreases.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R11 | Field clears after save | Yes |
| R12 | Artwork appears in "No Location Assigned" filter | Yes |
| R13 | Previous location count decreases | Yes |

---

## Guide 4 — View the Artwork Locations Dashboard

**When to use:** When you want an overview of all artworks and their current locations — to identify unassigned artworks, see how many artworks are in each space, or filter by location.

### Steps

1. Go to **Inventory → Products → Artwork Locations**.

### Expected outcome

- A list of all artwork products is shown, grouped by **Current Location** by default.
- Each group header shows the location name and the count of artworks at that location.
- Artworks with no location assigned appear under a **(none)** group.
- You can search by artwork name, creator, or current location using the search bar.
- You can use the **No Location Assigned** filter to find artworks that have not been placed.
- You can switch to group by Category or remove grouping entirely using the Group By menu.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R14 | Dashboard opens under Inventory → Products | Yes |
| R15 | Artworks grouped by location by default | Yes |
| R16 | Artwork count per location group is accurate | Yes |
| R17 | "No Location Assigned" filter shows unassigned artworks | Yes |
| R18 | Non-artwork products not shown in dashboard | Yes — domain restricts to product_type='artwork' |
| R19 | Search by artwork name works | Yes |
| R20 | Group by Location works | Yes |

---

## Guide 5 — View Artworks at a Specific Room or Location

**When to use:** When you are viewing a specific Room or location and want to see which artworks are currently there.

### Steps

1. Go to **Inventory → Configuration → Locations** (or navigate to the Room via the Rooms list).
2. Open the location record.
3. Click the **Artworks** smart button at the top of the form.

### Expected outcome

- A filtered list opens showing only artworks whose **Current Location** is this specific location.
- The count on the smart button matches the number of rows in the list.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R21 | Artworks smart button visible on location form | Yes |
| R22 | Smart button count reflects artworks at this location | Yes |
| R23 | Click opens filtered list scoped to this location | Yes |
| R24 | Artworks at other locations not shown | Yes |

---

## Guide 6 — View Artworks Across a Viewing Location (Warehouse)

**When to use:** When you are viewing a Viewing Location (gallery space or building) and want to see the total count of artworks across all its Rooms.

### Steps

1. Go to **Inventory → Configuration → Warehouses** (or navigate to the Viewing Location).
2. Open the Viewing Location record.
3. Click the **Artworks** smart button at the top of the form.

### Expected outcome

- The smart button count shows the total number of artworks at any location within this Viewing Location's hierarchy.
- Clicking the button opens a filtered list of those artworks.
- Artworks at locations outside this Viewing Location are not counted.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R25 | Artworks smart button visible on warehouse (Viewing Location) form | Yes |
| R26 | Count aggregates artworks across all Rooms under this Viewing Location | Yes |
| R27 | Click opens filtered list scoped to this Viewing Location's locations | Yes |
| R28 | Artworks at external or other viewing locations not counted | Yes |

---

## Guide 7 — Multi-Company Behaviour

**When relevant:** Deployments where more than one company is active in the same Odoo instance (e.g. a group with separate legal entities sharing one installation).

### Single-company deployments

No change in behaviour. All Viewing Locations, Rooms, Studios, and External Locations belong to the same company, and the **Current Location** picker shows them all as before.

### Multi-company deployments

**Location picker is company-scoped.** When editing an artwork that belongs to Company A, the **Current Location** picker shows only:
- Locations belonging to Company A (Rooms, Studios, External Locations created under Company A)

Locations belonging to Company B are not shown and cannot be selected.

**Global virtual Odoo locations are excluded.** Odoo ships with two system-wide virtual accounting locations — **Customers** and **Vendors** — that have no company assignment (`company_id = False`). These are internal bookkeeping constructs, not physical spaces. They are excluded from the picker by the `('company_id', '!=', False)` clause in the `current_location_id` domain. This applies in both single-company and multi-company deployments. This prevents an artwork from being recorded as physically present in a location that belongs to a different legal entity.

**Attempting a cross-company assignment raises an error.** If a cross-company assignment is attempted (e.g. via import or API), Odoo blocks it with a user-visible error message: *"Uh-oh! You've got some company inconsistencies here…"*

**Artwork counts are company-scoped.** The **Artworks** smart button count on a Room or Viewing Location reflects only artworks from that location's own company. A Company B location's count is not affected by Company A artworks, and vice versa.

**Dashboard shows your active company's artworks.** The Artwork Locations dashboard (Inventory → Products → Artwork Locations) is subject to Odoo's standard multi-company record rules — you see only artworks belonging to your currently active company.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R29 | Picker only shows locations from the active company (plus shared locations) | Yes |
| R30 | Cross-company assignment raises a user-visible error | Yes |
| R31 | Smart button count excludes artworks from other companies | Yes |

---

## Guide 8 — Viewing Location Form (UI Cleanup)

**When relevant:** Any time a user opens a Viewing Location record from **Artworks → Viewing Locations** (or Inventory Configuration → Warehouses).

### What is suppressed and why

When `sor_locations_artwork` is installed, the following elements are hidden on the Viewing Location form. They are Odoo warehouse logistics features that exist on the underlying `stock.warehouse` model but have no operational meaning when Viewing Locations are used to manage artworks:

- **Routes button** (header stat button) — links to procurement route configuration
- **Warehouse Configuration tab** — contains shipment step radio buttons (Receive in 1/2/3 steps, Ship in 1/2/3 steps) and a Resupply section
- **Technical Information tab** — shows internal Odoo location IDs and operation type references

### What this looks like in practice

A **Viewing Location** form shows only:
- The location name and short code
- Address (Partner)
- Company (in multi-company deployments)
- The Artworks smart button (added by this bridge)
- A Branches tab (if child warehouses exist)

A **Room / Studio / External Location** form shows only:
- The location name and parent location
- Additional Information (location type, storage category, company, replenish flag)
- The Artworks smart button (added by this bridge)

### Expected outcome

The three suppressed elements are not visible on the Viewing Location form in any mode (regular or developer mode).

> **Developer mode note:** The Technical Information tab carries Odoo's `groups="base.group_no_one"` restriction, but this is insufficient when `stock.group_adv_location` and `stock.group_stock_multi_warehouses` are both active (both are required by SOR Locations). The explicit `invisible="1"` suppression here overrides the groups-based visibility.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R32 | Routes stat button not visible on Viewing Location form | Hidden |
| R33 | Warehouse Configuration tab not visible on Viewing Location form | Hidden |
| R34 | Technical Information tab not visible on Viewing Location form | Hidden (including in developer mode) |
| R35 | All three visible if `sor_locations_artwork` is uninstalled | Visible — suppression is bridge-specific |
| R36 | Putaway Rules button not visible on Room / Studio / External Location form | Hidden |
| R37 | Products button not visible on Room / Studio / External Location form | Hidden |
| R38 | Cyclic Counting section not visible on Room / Studio / External Location form | Hidden |
| R39 | Logistics section not visible on Room / Studio / External Location form | Hidden |
| R40 | All four visible if `sor_locations_artwork` is uninstalled | Visible — suppression is bridge-specific |

---

## Scope — What is NOT Included

The following are explicitly out of scope for this feature and belong to later sprints:

- **Movement history** — `current_location_id` records *where* an artwork is now. Historical location movements and transfer records are managed by the Consignments and Loans workflows.
- **Ownership and consignor information** — the artwork's owner (Consignor) field is display-only at this stage. It will be populated by the Consignments sprint.
- **Transfer reasons** — why an artwork moved (sold, on loan, donated, on approval) is tracked by Consignments and Loans, not by this field.
- **Reordering, forecasting, and stock quants** — artwork location assignment uses a direct field on `product.template`, not Odoo's quant/inventory system. Standard stock operations (replenishment, inventory adjustments) are not relevant to artwork location assignment.

---

## Interoperability

### With Artist Studios (`sor_locations_artist_studios`)

When Artist Studios is also installed, Studio locations (internal) appear in the **Current Location** search list alongside gallery Rooms. An artwork can be assigned to an Artist Studio to record that it is currently at the artist's premises.

### With External Locations (`sor_locations_external`)

When External Locations is also installed, External Location records (customer-type) appear in the **Current Location** search list. An artwork assigned to an External Location is recorded as being at a collector's home, a client's premises, or a storage facility.

### With SOR Tracking (`sor_tracking`)

When `sor_tracking` is installed:
- Validating a movement updates `current_location_id` on artwork products to the movement's destination location.
- A **destination confirmation wizard** fires before validation when the artwork already has a location recorded — staff confirm the update.
- A **source location discrepancy wizard** fires before validation when the movement's declared source location does not match the artwork's `current_location_id` — staff can proceed or cancel to investigate.
- The `current_location_id` domain now includes `supplier` locations (in addition to `internal` and `customer`) so that the Vendors/External pool location provisioned by `sor_tracking` appears in the picker.

---

## Quick Reference: Regression Test Checklist

| Ref | Area | Check | Expected |
|-----|------|-------|----------|
| R1 | Assign | Current Location field visible on artwork form | Yes |
| R2 | Assign | Internal (Room) location selectable | Yes |
| R3 | Assign | Customer (External) location selectable | Yes |
| R3a | Assign | Supplier location (Vendors/External pool) selectable | Yes |
| R4 | Assign | View-type location not selectable | Yes |
| R5 | Assign | Field saves correctly | Yes |
| R5c | Assign | Odoo global virtual locations (Customers/Vendors, company_id=False) not selectable | Yes — excluded by domain |
| R6 | Assign | Chatter records the change | Yes |
| R7 | Reassign | Field updates to new location | Yes |
| R8 | Reassign | Old location count decreases | Yes |
| R9 | Reassign | New location count increases | Yes |
| R10 | Reassign | Chatter shows the change | Yes |
| R11 | Clear | Field clears after save | Yes |
| R12 | Clear | Artwork appears in "No Location Assigned" filter | Yes |
| R13 | Clear | Previous location count decreases | Yes |
| R14 | Dashboard | Opens under Inventory → Products | Yes |
| R15 | Dashboard | Grouped by location by default | Yes |
| R16 | Dashboard | Artwork count per group is accurate | Yes |
| R17 | Dashboard | "No Location Assigned" filter works | Yes |
| R18 | Dashboard | Non-artwork products excluded | Yes |
| R19 | Dashboard | Search by artwork name works | Yes |
| R20 | Dashboard | Group by Location works | Yes |
| R21 | Location | Artworks smart button visible on location form | Yes |
| R22 | Location | Smart button count accurate | Yes |
| R23 | Location | Click opens filtered list for this location | Yes |
| R24 | Location | Artworks at other locations excluded | Yes |
| R25 | Warehouse | Artworks smart button visible on warehouse form | Yes |
| R26 | Warehouse | Count aggregates across all child locations | Yes |
| R27 | Warehouse | Click opens filtered list for this warehouse | Yes |
| R28 | Warehouse | Artworks at other locations excluded | Yes |
| R29 | Company | Picker only shows same-company locations (plus shared) | Yes |
| R30 | Company | Cross-company assignment raises a user-visible error | Yes |
| R31 | Company | Smart button count excludes other-company artworks | Yes |
| R32 | Viewing Location UI | Routes stat button not visible | Hidden |
| R33 | Viewing Location UI | Warehouse Configuration tab not visible | Hidden |
| R34 | Viewing Location UI | Technical Information tab not visible (incl. developer mode) | Hidden |
| R35 | Viewing Location UI | All three visible without this bridge installed | Visible |
| R36 | Location UI | Putaway Rules button not visible on Room/Studio/External form | Hidden |
| R37 | Location UI | Products button not visible on Room/Studio/External form | Hidden |
| R38 | Location UI | Cyclic Counting section not visible on Room/Studio/External form | Hidden |
| R39 | Location UI | Logistics section not visible on Room/Studio/External form | Hidden |
| R40 | Location UI | All four visible without this bridge installed | Visible |
