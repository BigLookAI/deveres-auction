# Technical Architecture: sor_locations_external

## Overview

`sor_locations_external` is a **bridge module** that delivers External Locations — off-premises customer locations linked to customer contacts — as a composable feature at the intersection of two base modules:

```
sor_locations          sor_contact_roles
       \                      /
        \                    /
    sor_locations_external   (auto_install=True, application=False)
```

Neither parent module is modified. The bridge activates automatically when both parents are installed.

---

## Bridge Module Pattern

**Manifest flags:**
```python
'category': 'Hidden/Technical',
'depends': ['sor_locations', 'sor_contact_roles'],
'auto_install': True,
'application': False,
```

- `auto_install: True` — Odoo installs the bridge automatically when both `sor_locations` and `sor_contact_roles` are present.
- `application: False` — The bridge does not appear as a top-level App.
- `category: 'Hidden/Technical'` — Kept out of business category listings.

**Why a bridge?** `sor_locations` must be installable without contact role features. `sor_contact_roles` must be installable without inventory/locations. Placing External Location logic in either parent would introduce coupling. The bridge keeps base modules independent and the intersection explicit.

---

## Architecture: External Locations as a View Location

Individual External Locations are `stock.location` (customer) records parented under an "External Locations" `stock.location` (view).

```
External Locations [stock.location, usage=view]
├── Collector A — Home [stock.location, usage=customer]
├── Collector A — Storage Facility [stock.location, usage=customer]
└── Collector B — Gallery [stock.location, usage=customer]
```

**Why a `stock.location(usage='view')` as parent?**
Customer locations (`usage='customer'`) are by definition outside the warehouse hierarchy. They require no warehouse infrastructure (routes, operations, picking types). A view-type `stock.location` is the correct Odoo primitive for grouping locations without implying any operational role.

This contrasts with `sor_locations_artist_studios` (Story 02), which uses a `stock.warehouse` as parent specifically to sidestep the Room nesting constraint introduced by Story 01. That constraint does not apply to customer locations.

**Separation from Rooms and Studios:** The Rooms action (`sor_locations.action_room_form`) filters by `usage='internal'`, which naturally excludes all customer locations. External Locations have their own menu entry and window action.

---

## Two-Layer Design

Story 03 delivers External Locations in two layers:

| Layer | Module | What it provides |
|-------|--------|-----------------|
| Layer 1 | `sor_locations` | `usage='customer'` location type available; base list/search/form views for external locations |
| Layer 2 | `sor_locations_external` (this module) | Virtual parent, opt-in, contact linkage, address defaulting, contact form smart button |

Layer 1 alone is sufficient for simple "external location" tracking without contact association. Layer 2 activates automatically when `sor_contact_roles` is also installed, adding the full contact-linked workflow.

---

## Opt-in Mechanism

External Locations is opt-in per company via Inventory → Configuration → Settings.

**Settings field:**
```python
# res.config.settings
sor_external_locations_enabled = fields.Boolean(
    config_parameter='sor_locations.external_locations_enabled',
)
```

When enabled, `set_values()`:
1. Activates the "External Locations" menu item (`menu.active = True`)
2. Calls `stock.location._sor_ensure_external_locations_parent()`, which creates the parent view location for the current company if it does not already exist. The method is idempotent.

**Parent location creation:**
- `name`: `'External Locations'`
- `usage`: `'view'`
- `company_id`: current company

### Post-install: all companies covered (Module Foundations sprint)

The `post_init_hook` in `__init__.py` runs on first install and calls `_sor_ensure_external_locations_parent()` for **every existing company**, not only the active company at install time. This ensures External Locations is available for all companies without each company administrator needing to navigate to Settings and toggle the setting manually.

```python
def post_init_hook(env):
    """Create the External Locations parent location for all existing companies on install."""
    for company in env['res.company'].search([]):
        env_co = env(context=dict(env.context, allowed_company_ids=[company.id]))
        env_co['stock.location']._sor_ensure_external_locations_parent()
```

The hook is declared in `__manifest__.py` as `'post_init_hook': 'post_init_hook'`. This follows the same pattern as `sor_locations_artist_studios`.

---

## Model: stock.location (extended)

Fields added by the bridge (`models/stock_location.py`):

| Field | Type | Notes |
|-------|------|-------|
| `contact_id` | `Many2one('res.partner')` | Domain: `[('is_customer', '=', True)]`. One customer per location; one customer may have many locations. |
| `ext_street` | `Char` | Independent stored field. Defaulted from contact on assignment; freely editable after. |
| `ext_city` | `Char` | As above. |
| `ext_zip` | `Char` | Label: "ZIP / Postcode". As above. |
| `ext_country_id` | `Many2one('res.country')` | As above. |

**Address defaulting (not derivation):** When `contact_id` is first selected in the form, `@api.onchange('contact_id')` copies the contact's current address into the location's `ext_*` fields. These fields are stored independently — they are NOT related/computed from the contact. Subsequent changes to the contact's address do not propagate to existing locations, and changing a location's address never modifies the contact. Multiple locations per contact with distinct addresses is fully supported.

**`default_get()` override:** Uses `sor_external_context: True` in context to pre-populate `location_id` with the External Locations view location, so new external locations are created under the correct parent by default.

---

## Model: res.partner (extended)

Fields and methods added by the bridge (`models/res_partner.py`):

| | Description |
|-|-------------|
| `external_location_ids` | `One2many('stock.location', 'contact_id')` — reverse of `contact_id`. Domain restricts to `usage=customer`. String: `'External Location Records'` (avoids duplicate label). |
| `external_location_count` | Computed `Integer` — count of linked external locations. Used by the smart button. |
| `action_open_external_locations()` | Opens a filtered list of external locations linked to this customer. |
| `action_create_external_location()` | Opens a new External Location form as a modal dialog, pre-populated with the contact's address. Raises `UserError` if the virtual parent has not been enabled. **Non-destructive** — always opens a new-record form; existing locations are unaffected. |

---

## Views

### Stock Location (External)
- **List** (`view_external_location_list`): name, contact, city, country.
- **Search** (`view_external_location_search`): search by name or contact; filter to contact-linked locations; group by contact.
- **Form** (`view_external_location_form`): inherits `stock.view_location_form` with `mode=primary` (standalone form, not shared with Rooms). Extensions:
  - `location_id` (h2): relabelled "External Locations", domain restricted to view locations named "External Locations", `readonly="id"` (editable only on new records).
  - `contact_id`: inserted before `usage` in the Additional Information group.
  - `usage`: marked readonly — External Locations are always Customer type.
  - External Address group: `ext_street`, `ext_city`, `ext_zip`, `ext_country_id`.
- **Window action** (`action_external_location_form`): domain `[('usage','=','customer')]`, context includes `sor_external_context: True`.

### Partner (Contact)
- Inherits `base.view_partner_form`.
- External Locations stat button (visible when `is_customer=True`): shows `external_location_count`, opens `action_open_external_locations`.
- "Create External Location" button (visible when `is_customer=True`): calls `action_create_external_location`, opens as modal dialog.

---

## Composability Boundary

| Scenario | `contact_id` on `stock.location` | External Locations in Settings | External Locations menu |
|----------|----------------------------------|-------------------------------|------------------------|
| `sor_locations` only | ✗ absent | ✗ absent | ✗ absent |
| `sor_contact_roles` only | ✗ absent | ✗ absent | ✗ absent |
| Both installed | ✓ present (bridge auto-activates) | ✓ present | ✓ present (when enabled) |

This boundary is verified by automated test 14 (`test_14_composability_boundary`).

---

## Comparison with sor_locations_artist_studios

| Aspect | Artist Studios | External Locations |
|--------|---------------|-------------------|
| Bridge module | `sor_locations_artist_studios` | `sor_locations_external` |
| Parent construct | `stock.warehouse` (code=AS) | `stock.location` (`usage='view'`) |
| Why that parent | Sidestep Room nesting constraint | Customer locs are outside warehouse hierarchy |
| Child `usage` | `'internal'` | `'customer'` |
| Contact field | `artist_id`, domain `[('is_artist','=',True)]` | `contact_id`, domain `[('is_customer','=',True)]` |
| Address fields | `studio_street/city/zip/country_id` | `ext_street/city/zip/country_id` |
| Opt-in ensures | `stock.warehouse._sor_ensure_artist_studios_warehouse()` | `stock.location._sor_ensure_external_locations_parent()` |
| Config parameter | `sor_locations.artist_studios_enabled` | `sor_locations.external_locations_enabled` |
| Reverse One2many | `studio_ids` / `studio_count` | `external_location_ids` / `external_location_count` |
| Contact visible when | `is_artist=True` | `is_customer=True` |

---

## Interoperability

### With Odoo Stock
External Locations are standard `stock.location` records with `usage='customer'`. Odoo's stock move engine natively supports moves to customer locations — this is the foundation of the standard sale order delivery flow. Moving artwork to a customer location decrements internal stock and credits the customer location. No custom move logic is required.

### With Story 01 — Viewing Locations and Rooms
Rooms are `usage='internal'` locations under Viewing Location warehouses. External Locations are `usage='customer'` — the `usage` type difference ensures complete separation. The Rooms window action domain (`usage='internal'`) naturally excludes External Locations.

### With Story 02 — Artist Studios
Artist Studios are `usage='internal'` locations under the Artist Studios warehouse. They are not External Locations. An artist's studio is an internal location (artwork is stored there as inventory); an external location is a customer location (artwork has left internal stock). If a collector who is also an artist has both studios and external locations, each appears under the appropriate module's UI independently.

### Out of Scope
Consignments, Loans, and Donations *workflows* are separate sprints. External Locations represent *where* artwork is physically located. The *why* (sold, on loan, donated) and *how* (consignment agreement, loan form, donation deed) are implemented in later sprints.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo -u sor_locations_external \
  --test-tags=external --stop-after-init
```

See `.cursor/rules/docker_dev_workflow.mdc` for full Docker upgrade/restart workflow.

---

## Story Reference

Parent story: `.backlog/01 Locations/stories/03_External-Locations.md`
Sprint: Sprint 01 — Locations (8 SP)
