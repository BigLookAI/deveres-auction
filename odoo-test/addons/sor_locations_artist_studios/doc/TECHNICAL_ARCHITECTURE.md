# Technical Architecture: sor_locations_artist_studios

## Overview

`sor_locations_artist_studios` is a **bridge module** that delivers Artist Studios — off-premises storage locations linked to artist contacts — as a composable feature at the intersection of two base modules:

```
sor_locations          sor_contact_roles
       \                      /
        \                    /
    sor_locations_artist_studios   (auto_install=True, application=False)
```

Neither parent module is modified. The bridge activates automatically when both parents are installed.

> ⚠️ **F05 — Pending architectural correction:** The current parent `sor_contact_roles` is incorrect. Artist Studios is an artwork-domain concept — the reason to model an artist's studio as an SOR location is artwork tracking. The bridge should depend on `sor_artwork_contact_roles` (which requires `sor_artwork + sor_contact_roles`), making the effective trigger `sor_locations + sor_artwork + sor_contact_roles`. With the current parents, the bridge auto-installs in any deployment that has locations and contact roles, including future non-artwork deployments where Artist Studios are not meaningful. This is masked today by the `sor_artwork` manifest violation (which forces `sor_contact_roles` to always co-install with `sor_artwork`), but will surface when a new asset vertical is introduced or the violation is resolved. See Sprint Findings F05 for the full rationale and proposed fix.

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

**Why a bridge?** `sor_locations` must be installable without contact role features (e.g., for a simple gallery that does not track artists). `sor_contact_roles` must be installable without inventory/locations (e.g., for a CRM-only deployment). Placing Artist Studios logic in either parent would introduce coupling. The bridge keeps base modules independent and the intersection explicit.

---

## Architecture: Artist Studios as a Warehouse

Individual Studios are `stock.location` (internal) records parented under an "Artist Studios" `stock.warehouse` (Viewing Location).

```
Artist Studios [stock.warehouse, code=AS]
└── AS [stock.location, usage=view]          ← view_location_id
    ├── Studio: Painter A — Dublin            ← stock.location, usage=internal
    ├── Studio: Painter A — Cork              ← stock.location, usage=internal
    └── Studio: Sculptor B — London           ← stock.location, usage=internal
```

**Why a Warehouse as parent?** Story 01 (`sor_locations`) added a constraint preventing `stock.location` (Room) records from being nested under other Room records. Using a Warehouse as the parent sidesteps this constraint entirely, reuses all Viewing Location infrastructure, and keeps Studios cleanly separated from gallery Rooms in the UI.

**Separation from Rooms:** The Rooms window action (`sor_locations.action_room_form`) is overridden to exclude locations under the `Artist Studios` warehouse. Studios and Rooms are distinct concepts and do not appear in each other's lists.

---

## Opt-in Mechanism

Artist Studios is opt-in per company via Inventory → Configuration → Settings.

**Settings field:**
```python
# res.config.settings
sor_artist_studios_enabled = fields.Boolean(
    config_parameter='sor_locations.artist_studios_enabled',
)
```

When enabled, `set_values()` calls `stock.warehouse._sor_ensure_artist_studios_warehouse()`, which creates the "Artist Studios" warehouse for the current company if it does not already exist. The method is idempotent — calling it multiple times is safe.

**Warehouse creation:**
- `name`: `'Artist Studios'`
- `code`: `'AS'`
- `partner_id`: `env.company.partner_id`
- `company_id`: current company

### Post-install: all companies covered (Module Foundations sprint)

The `post_init_hook` in `__init__.py` runs on first install and calls `_sor_ensure_artist_studios_warehouse()` for **every existing company**, not only the active company at install time. Companies without a `partner_id` are skipped (this is a defensive guard; all well-formed `res.company` records have a partner). This ensures Artist Studios infrastructure is available for all companies without each company administrator needing to navigate to Settings and toggle the setting manually.

```python
def post_init_hook(env):
    """Create the Artist Studios warehouse for all existing companies on install."""
    for company in env['res.company'].search([]):
        if not company.partner_id:
            continue
        env_co = env(context=dict(env.context, allowed_company_ids=[company.id]))
        env_co['stock.warehouse']._sor_ensure_artist_studios_warehouse()
```

The hook is declared in `__manifest__.py` as `'post_init_hook': 'post_init_hook'`. This follows the same pattern as `sor_locations_external`.

---

## Model: stock.location (extended)

Fields added by the bridge (`models/stock_location.py`):

| Field | Type | Notes |
|-------|------|-------|
| `artist_id` | `Many2one('res.partner')` | Domain: `[('is_artist', '=', True)]`. One artist per Studio; one artist may have many Studios. |
| `studio_street` | `Char` | Independent stored field. Defaulted from artist on assignment; freely editable after. |
| `studio_city` | `Char` | As above. |
| `studio_zip` | `Char` | As above. |
| `studio_country_id` | `Many2one('res.country')` | As above. |

**Address defaulting (not derivation):** When `artist_id` is first selected in the form, `@api.onchange('artist_id')` copies the artist's current address into the Studio's address fields. These fields are stored independently — they are NOT related/computed from the artist. Subsequent changes to the artist's address do not propagate to existing Studios, and changing a Studio's address never modifies the artist contact. Multiple Studios per artist with distinct addresses is fully supported.

**New record context:** The window action passes `sor_studio_context: True` in its context. `default_get()` on `stock.location` uses this flag to pre-populate `location_id` with the AS view location, so new Studios are created in the correct location by default.

---

## Model: res.partner (extended)

Fields and methods added by the bridge (`models/res_partner.py`):

| | Description |
|-|-------------|
| `studio_ids` | `One2many('stock.location', 'artist_id')` — reverse of `artist_id`. Domain restricts to `usage=internal`. |
| `studio_count` | Computed `Integer` — count of linked Studios. Used by the smart button. |
| `action_open_studios()` | Opens a filtered list of Studios linked to this artist. |
| `action_create_studio()` | Creates a new Studio under the Artist Studios Warehouse, defaulting the address from the partner. Raises `UserError` if the warehouse has not been enabled. **Non-destructive** — always creates a new record; existing Studios are unaffected. |

---

## Views

### Stock Location (Studios)
- **List** (`view_studio_list`): name, artist, city, country, viewing location.
- **Search** (`view_studio_search`): search by name or artist; filter to Artist Studios warehouse; group by artist.
- **Form** (`view_studio_form`): inherits `stock.view_location_form` with `mode=primary` (standalone form, not shared with Rooms). Extensions:
  - `location_id` (h2): relabelled "Artist Studios", domain restricted to AS warehouse, `readonly="id"` (editable only on new records).
  - `artist_id`: inserted before `usage` in the Additional Information group.
  - `usage`: marked readonly — Studios are always Internal.
  - Studio Address group: `studio_street`, `studio_city`, `studio_zip`, `studio_country_id`.
- **Window action** (`action_artist_studio_form`): domain `[('usage','=','internal'), ('warehouse_id.name','=','Artist Studios')]`, context includes `sor_studio_context: True`.

### Rooms window action — domain override
- **Override** (`sor_locations.action_room_form`): adds `('code', '!=', 'AS')` to the Rooms list domain, excluding all locations parented under an Artist Studios warehouse. Ensures Studios never appear in the Rooms list.

### Room form — parent location domain restriction (D7)
- **View** (`view_room_form_restrict_as_parent`): inherits `sor_locations.view_room_form` and tightens the `location_id` (parent Viewing Location) field domain with `('warehouse_view_ids.code', '!=', 'AS')`. Prevents Artist Studios from being selected as the parent of a Room in the creation form. Without this restriction, Artist Studios appeared in the parent dropdown even though it cannot have Rooms under it by design.

### Viewing Locations window action — domain override (D9)
- **Override** (`sor_locations.action_viewing_location_form`): sets `domain=[('code', '!=', 'AS')]` on the Viewing Locations list action. Excludes Artist Studios warehouses from the Viewing Locations list. Without this override, Artist Studios appeared alongside Main Gallery, Secondary Space, and Collection Storage — confusing because Artist Studios cannot have Rooms and is not a valid Room parent. Consistent with the Rooms list and Room form restrictions already provided by this bridge.

### Partner (Contact)
- Inherits `base.view_partner_form`.
- Studios stat button (visible when `is_artist=True`): shows `studio_count`, opens `action_open_studios`.
- "Create Studio" button (visible when `is_artist=True`): calls `action_create_studio`.

---

## Composability Boundary

| Scenario | `artist_id` on `stock.location` | Artist Studios in Settings | Studios menu |
|----------|---------------------------------|---------------------------|--------------|
| `sor_locations` only | ✗ absent | ✗ absent | ✗ absent |
| `sor_contact_roles` only | ✗ absent | ✗ absent | ✗ absent |
| Both installed | ✓ present (bridge auto-activates) | ✓ present | ✓ present |

This boundary is verified by automated test 14 (`test_14_composability_boundary`).

---

## Running the Tests

```bash
# Docker workflow (upgrade + restart for Python changes):
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo -i sor_locations_artist_studios \
  --test-tags=studios --stop-after-init

# Local virtualenv:
source venv/bin/activate
python odoo-bin -d <db> -i sor_locations_artist_studios --test-tags=studios --stop-after-init
```

See `.cursor/rules/docker_dev_workflow.mdc` for full Docker upgrade/restart workflow.

---

## Story Reference

Parent story: `.backlog/01 Locations/stories/02_Studios-as-Internal-Locations.md`
Sprint: Sprint 01 — Locations (8 SP)
