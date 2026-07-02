# SOR Locations — Knowledge Base

**Module**: `sor_locations`
**Sprint**: 01 — Locations
**Story**: 01 — Viewing Location and Rooms
**Depends on**: `stock` (Odoo Community Inventory)

---

## What Is This Block?

**SOR Locations** introduces the concepts of **Viewing Locations** and **Rooms** into the SOR system. It extends Odoo's built-in Inventory (stock) module — no new database tables are created. Viewing Locations and Rooms are the physical backbone of the SOR system: every artwork in the system can be assigned to a place, and that place is always described as a Room inside a Viewing Location.

| Concept | What it is | Odoo model |
|---------|-----------|------------|
| **Viewing Location** | One physical site — a gallery, auction house, or campus building. Has an address and belongs to one company. | `stock.warehouse` |
| **Room** | A sub-division within a Viewing Location — e.g. "Gallery Viewing", "Storage", "Basement". | `stock.location` (usage = internal) |

---

## How to Use It

### Installing the module

Install **SOR Locations** from the Apps screen. On install, the module automatically enables the Odoo **Storage Locations** setting so Rooms appear without any manual configuration step. You do not need to visit Inventory → Configuration → Settings.

### Creating a Viewing Location

Navigate to **Inventory → Configuration → Viewing Locations**.

- Give the location a name (e.g. "SO Fine Art Gallery").
- The address defaults to the current company's address. To use a different address, select one from the **Address** field.
- Each Viewing Location belongs to one company (set automatically from context).

> A Viewing Location requires an address. If you attempt to save without one, the system will show a validation error.

### Creating Rooms

Navigate to **Inventory → Configuration → Rooms**.

- Select the parent **Viewing Location** (required).
- Only Viewing Locations appear as valid parents — it is not possible to nest a Room inside another Room.
- Give the Room a name (e.g. "Gallery Floor", "Storage").

### Pilot configurations

**SO Fine Art** (single gallery):
```
SO Fine Art Gallery           ← Viewing Location
  ├── Gallery Viewing         ← Room
  └── Storage                 ← Room
```

**SETU** (multi-campus campus collection):
```
SETU Building A               ← Viewing Location
  ├── Room A1                 ← Room
  └── Room A2                 ← Room

SETU Building B               ← Viewing Location
  ├── Room B1                 ← Room
  └── Room B2                 ← Room
```

---

## Interoperability

### With Odoo Stock

`sor_locations` extends — not replaces — the Odoo stock module:

| Stock concept | SOR concept | Relationship |
|--------------|-------------|--------------|
| `stock.warehouse` | Viewing Location | `_inherit` — all warehouses in SOR are Viewing Locations |
| `stock.location` (internal) | Room | `_inherit` — internal locations under a warehouse view location are Rooms |

The standard Odoo **Warehouses** and **Locations** menus in Inventory → Configuration are suppressed while `sor_locations` is installed, to avoid confusion with the SOR-specific menus. They are restored automatically if the module is uninstalled.

---

## Constraints and Business Rules

1. **Address required** — A Viewing Location cannot be saved without an address (`partner_id`). The default is the current company's address.
2. **Room parent must be a Viewing Location** — A Room (`stock.location`, `usage = internal`) must be a direct child of a warehouse's view location. Nesting a Room under another Room raises a validation error.
3. **Company scoping** — Viewing Locations and Rooms are scoped to the company they belong to. A user restricted to Company B cannot see Viewing Locations created for Company A.
4. **Storage Locations enabled on install** — The `post_init_hook` enables the Odoo `stock.group_stock_multi_locations` setting so Rooms are visible without manual user action.
5. **Menu suppression on install / restoration on uninstall** — The standard Odoo Warehouses and Locations menus are deactivated while `sor_locations` is installed and restored when it is removed.

---

## Multi-Company and Distributed Collections

### Single-company, distributed collections

Multiple Viewing Locations and Rooms can coexist within a single company. There is no limit to the number of Viewing Locations. This directly supports the **SETU multi-campus** use case: each campus building is a separate Viewing Location, each room is a Room under it, and all buildings belong to the same legal entity (company).

```
SETU (one company)
  SETU Building A       ← Viewing Location
    Room A1             ← Room
    Room A2             ← Room
  SETU Building B       ← Viewing Location
    Room B1             ← Room
    Room B2             ← Room
```

No Odoo **Branches** feature is needed or used. The existing `stock.warehouse` / `stock.location` hierarchy handles multi-campus correctly in Community Edition.

### Multi-company

Each company has its own independent set of:
- Viewing Locations and Rooms (`sor_locations`)
- Artist Studios Warehouse and Studios (`sor_locations_artist_studios`)
- External Locations parent and External Locations (`sor_locations_external`)

Data is company-scoped at the ORM level via `stock.warehouse.company_id` and `stock.location.company_id`. Odoo enforces that a user restricted to Company B cannot read or modify locations belonging to Company A.

### Artwork location assignment

`current_location_id` on `product.template` (added by the `sor_locations_artwork` bridge) uses `check_company=True`. Only locations from the **same company** as the artwork, or shared locations with no company, can be assigned to an artwork. Attempting to assign a location from a different company raises a validation error.

The field domain is:
```
[('usage', 'in', ['internal', 'customer']), '|', ('company_id', '=', False), ('company_id', '=', company_id)]
```

The `artwork_count` computed fields on `stock.location` and `stock.warehouse` apply the same company filter, so counts shown on a location reflect only artworks from that location's own company.

### Contact fields (`artist_id`, `contact_id`)

`res.partner` is **shared master data** across companies in Odoo Community Edition. The `artist_id` field on Artist Studios (`sor_locations_artist_studios`) and the `contact_id` field on External Locations (`sor_locations_external`) do **not** use `check_company=True`. This is by design: an artist or customer contact can appear in multiple companies' data without duplication. There is no cross-company data leak risk because the contact record itself is shared, not owned by any company.

### Known Community Edition limitations

**Settings toggle shared state.** The "Enable Artist Studios" and "Enable External Locations" checkboxes in company Settings use `ir.config_parameter` under the hood. In a multi-company deployment, `config_parameter` values are global — the checkbox state is shared across all companies. When enabled in one company, the setting appears ticked in all companies' Settings screens. Data creation (warehouses, location parents) is correctly per-company when the action is performed from that company. This is an accepted CE constraint; it is raised as a retrospective item for a future fix (e.g. migrating to `res.config.settings` company-specific fields).

**Menu activation is global.** The External Locations menu entry is activated by setting `menu.active = True`. In Odoo CE, menu active state is not company-specific; enabling the menu in one company activates it for all companies. This is an accepted CE behaviour.

### Interoperability

| Block | Module | Story |
|-------|--------|-------|
| Viewing Locations and Rooms | `sor_locations` | Story 01 |
| Artist Studios | `sor_locations_artist_studios` | Story 02 |
| External Locations | `sor_locations_external` | Story 03 |
| Artwork ↔ Location bridge | `sor_locations_artwork` | Story 04 |

For multi-company Odoo CE behaviour, refer to the Odoo 19 documentation in `odoodocs/documentation-19.0/content/applications/general/companies.rst`.
