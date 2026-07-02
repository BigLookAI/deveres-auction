# Technical Architecture: sor_locations_artwork

## Overview

`sor_locations_artwork` is a **bridge module** that delivers artwork location assignment and the Artwork Locations dashboard — composable features that only make sense when both `sor_locations` and `sor_artwork` are installed simultaneously:

```
sor_locations          sor_artwork
       \                   /
        \                 /
    sor_locations_artwork   (auto_install=True, application=False)
```

Neither parent module is modified. The bridge activates automatically when both parents are installed.

---

## Bridge Module Pattern

**Manifest flags:**
```python
'category': 'Hidden/Technical',
'depends': ['sor_locations', 'sor_artwork'],
'auto_install': True,
'application': False,
```

- `auto_install: True` — Odoo installs the bridge automatically when both `sor_locations` and `sor_artwork` are present.
- `application: False` — The bridge does not appear as a top-level App.
- `category: 'Hidden/Technical'` — Kept out of business category listings.

**Why a bridge?** `sor_locations` must be installable without artwork features (e.g., for a collection manager who does not use the artwork product model). `sor_artwork` must be installable without location/inventory features (e.g., for a gallery that tracks artwork metadata without inventory). Placing the location-assignment field or dashboard in either parent would introduce coupling. The bridge keeps base modules independent and the intersection explicit.

**No opt-in setting required:** Unlike Artist Studios (which creates a warehouse on opt-in) and External Locations (which creates a virtual parent location), artwork-location assignment requires no initial data setup. The `current_location_id` field simply appears on artwork records when the bridge installs. There is no Settings toggle, no `post_init_hook`, and no `_sor_ensure_*()` method — this is a pure "just works" intersection.

---

## Architecture: current_location_id on product.template

Artworks are unique, singular physical objects — not fungible stock items. Stock quants track quantities across locations; they are unsuitable for tracking "where is this specific painting right now." A direct `Many2one('stock.location')` field on `product.template` is the correct construct for one-to-one physical location assignment.

```
product.template (artwork)
└── current_location_id → stock.location
                          ├── Internal locations (Rooms, Studios)
                          └── Customer locations (External Locations)
```

**Domain restriction:**
```
"[('usage', 'in', ['internal', 'customer', 'supplier']), ('company_id', '!=', False)]"
```
Covers Rooms and Artist Studios (internal), External Locations (customer), and Vendor-pool staging areas (supplier). The `supplier` usage was added in the Movement Enhancements sprint to include the Vendors/External pool location provisioned by `sor_tracking`. Excludes view and transit locations.

`('company_id', '!=', False)` excludes Odoo's global virtual locations — the system-wide **Customers** (usage=customer) and **Vendors** (usage=supplier) entries that have no company assignment. These appear in usage-only domain searches and must be explicitly excluded. SOR movements use company-scoped pool locations (Vendors/External, Buyers/External) that carry a `company_id` and are therefore included correctly.

Company consistency at assignment time is enforced by `check_company=True` on the field (ORM raises `UserError` on cross-company write), not by a `company_id` equality filter in the domain.

**Company enforcement:** `check_company=True` is set on the field. Odoo's ORM enforces company consistency at write time — assigning a location from a different company raises `UserError` (not `ValidationError`). This is Odoo's standard `check_company` mechanism, not a custom `@api.constrains`.

**Field is not artwork-exclusive:** `current_location_id` is added to `product.template` (not restricted to artworks by a constraint). Any product can have a current location set. The dashboard filters to artworks; the field itself is unrestricted by product type.

---

## Model: product.template (extended)

Fields added by the bridge (`models/product_template.py`):

| Field | Type | Notes |
|-------|------|-------|
| `current_location_id` | `Many2one('stock.location')` | Domain: `[('usage','in',['internal','customer','supplier']), ('company_id','!=',False)]`. `supplier` usage added in Movement Enhancements sprint to include the Vendors/External pool location. `('company_id','!=',False)` added (UAT Issue 3) to exclude Odoo's global virtual locations (Customers/Vendors with no company). `check_company=True` — ORM blocks cross-company assignment at write time with `UserError`. Optional — blank means location not yet assigned. `tracking=True` for chatter history. |

---

## Model: stock.location (extended)

Fields and methods added by the bridge (`models/stock_location.py`):

| | Description |
|-|-------------|
| `artwork_count` | Computed `Integer` — count of artworks whose `current_location_id` equals this location. Search includes company filter: `'|', ('company_id','=',False), ('company_id','=',location.company_id.id)` — counts only artworks from the same company as the location, plus shared artworks with no company. |
| `action_open_artworks()` | Returns an `ir.actions.act_window` dict for `product.template`, domain `[('current_location_id','=',self.id),('product_type','=','artwork'), '|', ('company_id','=',False), ('company_id','=',self.company_id.id)]`. Used by the Artworks smart button on the location form. |

---

## Model: stock.warehouse (extended)

Fields and methods added by the bridge (`models/stock_warehouse.py`):

| | Description |
|-|-------------|
| `artwork_count` | Computed `Integer` — count of artworks at any location under this warehouse's view location hierarchy. Uses `('id','child_of', warehouse.view_location_id.id)` to collect all descendant locations, then counts artworks at those locations. Search includes company filter: `'|', ('company_id','=',False), ('company_id','=',warehouse.company_id.id)` — counts only artworks from the same company as the warehouse, plus shared artworks with no company. |
| `action_open_artworks()` | Returns an `ir.actions.act_window` dict for `product.template`, domain `[('current_location_id','in', child_location_ids),('product_type','=','artwork'), '|', ('company_id','=',False), ('company_id','=',self.company_id.id)]`. Used by the Artworks smart button on the warehouse form. |

**child_of operator:** The warehouse smart button uses Odoo's `child_of` domain operator on `view_location_id.id` to traverse the full location hierarchy. This correctly handles multi-level location trees (e.g. a Room that contains sub-rooms).

---

## Views

### product.template (artwork form)

- Inherits `sor_artwork.view_product_template_form_artwork`.
- Adds `current_location_id` field after `creation_year` in the artwork metadata group.

### Artwork Locations Dashboard

- **List view** (`view_artwork_location_dashboard_list`): `mode=primary`, inherits `sor_artwork.view_product_template_tree_artwork`. Adds `current_location_id` column. Primary mode means this view is scoped to the dashboard action only and does not affect the standard artwork list.
- **Search view** (`view_artwork_location_dashboard_search`): `mode=primary`, inherits `sor_artwork.view_product_template_search_artwork`. Adds:
  - **Current Location** field search
  - **No Location Assigned** filter: `[('current_location_id','=',False),('product_type','=','artwork')]`
  - **Group by Location** option
  - Default context activates **Group by Location** on open: `{'search_default_group_by_location': 1}`.
- **Window action** (`action_artwork_location_dashboard`): domain `[('product_type','=','artwork')]`, explicit `view_ids` and `search_view_id` referencing the primary views above.

### Stock Location (Smart Button)

- Inherits `stock.view_location_form` (non-primary).
- Because all SOR location forms (Rooms, Studios, External Locations) derive from `stock.view_location_form` via `mode=primary`, this single inheritance adds the Artworks smart button to every location form type without needing separate overrides.

### Stock Warehouse (Smart Button)

- Inherits `stock.view_warehouse`.
- Adds the Artworks smart button to the Viewing Location (warehouse) form.

### Menu

- **Artwork Locations** — under **Inventory → Products** (parent: `stock.menu_stock_inventory_control`), sequence 15, visible to `stock.group_stock_user`.

---

## Module File Structure

```
addons/sor_locations_artwork/
├── __init__.py
├── __manifest__.py                         # depends=['sor_locations','sor_artwork'], auto_install=True
├── models/
│   ├── __init__.py
│   ├── product_template.py                 # current_location_id Many2one('stock.location')
│   ├── stock_location.py                   # artwork_count (computed), action_open_artworks()
│   └── stock_warehouse.py                  # artwork_count (computed), action_open_artworks()
├── views/
│   ├── product_template_views.xml          # Artwork form extension + dashboard list/search + window action
│   ├── stock_location_views.xml            # Artworks smart button on stock.location form
│   ├── stock_warehouse_views.xml           # Artworks smart button on stock.warehouse form
│   └── menu.xml                            # Dashboard menu under Inventory → Products
├── security/
│   └── ir.model.access.csv                 # Header only — no new models added
├── tests/
│   ├── __init__.py
│   └── test_sor_artwork_locations.py       # 15 tests, @tagged('artwork_locations')
└── doc/
    ├── TECHNICAL_ARCHITECTURE.md           # This file
    └── KNOWLEDGE_BASE.md                   # User-facing feature documentation
```

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | `auto_install=True`, `depends=['sor_locations','sor_artwork']` — the composability declaration |
| `models/product_template.py` | Adds `current_location_id` to `product.template` |
| `models/stock_location.py` | `artwork_count` + `action_open_artworks()` on `stock.location` |
| `models/stock_warehouse.py` | `artwork_count` + `action_open_artworks()` on `stock.warehouse` |
| `views/product_template_views.xml` | Dashboard list view (primary), search view (primary), window action, artwork form extension |
| `views/stock_location_views.xml` | Artworks smart button on all location forms (non-primary inherit of `stock.view_location_form`) |
| `views/stock_warehouse_views.xml` | Artworks smart button on Viewing Location (warehouse) form |
| `views/menu.xml` | Dashboard menu item under `stock.menu_stock_inventory_control` |
| `tests/test_sor_artwork_locations.py` | 15 automated tests covering field, domain, counts, actions, composability, and company scoping |

---

## Composability Boundary

| Scenario | `current_location_id` on artwork | Dashboard menu | Smart buttons |
|----------|----------------------------------|----------------|---------------|
| `sor_locations` only | ✗ absent | ✗ absent | ✗ absent |
| `sor_artwork` only | ✗ absent | ✗ absent | ✗ absent |
| Both installed | ✓ present (bridge auto-activates) | ✓ present | ✓ present |

This boundary is verified by automated test 14 (`test_14_composability_boundary`).

---

## Company Scoping

### Field enforcement

`current_location_id` uses `check_company=True`. Odoo's ORM calls `_check_company()` on every write and raises `UserError` (not `ValidationError`) if the linked location's `company_id` does not match the product's `company_id`. The exception type matters for test code: `assertRaises(UserError)` is required, not `assertRaises(ValidationError)`.

**Note:** The `current_location_id` field domain explicitly excludes `company_id = False` locations (`('company_id', '!=', False)`). This is intentional: Odoo's global virtual locations (Customers, Vendors) have `company_id = False` and must not appear in the artwork location picker. All SOR pool locations (Vendors/External, Buyers/External, Partners/External) are company-scoped and are correctly included. The `check_company=True` enforcement at ORM write time does not apply to `company_id = False` fields — those are treated as shared. But the domain filter in the picker prevents staff from ever selecting a global virtual location in the first place.

### Count and action domain pattern

Both `_compute_artwork_count` and `action_open_artworks()` on `stock.location` and `stock.warehouse` include the same company filter:

```python
'|', ('company_id', '=', False),
     ('company_id', '=', <record>.company_id.id),
```

This is a **defensive filter** — it ensures that if an artwork record with no `company_id` (shared product) were somehow linked to a location, it would still be counted by the location's company. In normal operation, `check_company=True` prevents cross-company assignments before they reach the database.

The filter is applied on the **location's company**, not the **viewing user's company**. A Company B location always counts its own Company B artworks regardless of which user is viewing. Odoo's record rules provide the user-level access gate in a multi-company deployment; the explicit filter is a belt-and-braces guard at the ORM query level.

### Test fixture requirement

Because `check_company=True` raises when a product with `company_id = False` is linked to a location with a `company_id`, all test artworks must be created with an explicit `company_id`:

```python
cls.artwork = cls.env['product.template'].create({
    ...
    'company_id': cls.env.company.id,
})
```

This reflects real usage: artworks in the art market always belong to a specific company's inventory.

### Existing data consideration

`check_company` is enforced at write time only — existing records with `current_location_id` set and `company_id = False` are not invalidated at rest. In a deployment upgrading from a pre-Story-05 installation, a data migration to set `company_id` on existing artwork `product.template` records is advisable before the next write to those records.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 --db_user=odoo --db_password=admin \
  -d odoo -u sor_locations_artwork \
  --test-tags=artwork_locations --stop-after-init
```

See `.cursor/rules/docker_dev_workflow.mdc` for full Docker upgrade/restart workflow.

---

## Story Reference

Parent story: `.backlog/01 Locations/stories/04_Artwork-Location-Assignment-and-Dashboard.md`
Sprint: Sprint 01 — Locations (8 SP)

Movement Enhancements sprint: `current_location_id` domain extended to include `supplier` usage (Vendors/External pool location); UAT Issue 3: domain updated to `('company_id', '!=', False)` to exclude Odoo global virtual locations (Customers/Vendors with no company).
