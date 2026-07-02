# Technical Architecture: sor_locations

**Module**: `sor_locations`
**Odoo version**: 19.0
**Depends**: `stock`

---

## Module Structure

```
addons/sor_locations/
├── __manifest__.py           # Module declaration, hooks, data list
├── __init__.py               # Imports models; defines post_init_hook and uninstall_hook
├── models/
│   ├── __init__.py
│   ├── stock_warehouse.py    # Viewing Location: extends stock.warehouse
│   └── stock_location.py    # Room: extends stock.location
├── views/
│   ├── stock_warehouse_views.xml   # Viewing Location form + list; action
│   ├── stock_location_views.xml    # Room list, form (mode=primary), search; action
│   ├── menu.xml                    # Viewing Locations + Rooms menu items
│   └── menu_overrides.xml          # Suppresses stock Warehouses + Locations menus
├── security/
│   └── ir.model.access.csv         # Header-only stub (no new _name models)
└── doc/
    └── TECHNICAL_ARCHITECTURE.md   # This file
```

---

## Design Decisions

### Why `_inherit`, not `_name`

Viewing Locations and Rooms are not new database tables — they are Odoo's existing `stock.warehouse` and `stock.location` with additional SOR constraints and UI. Using `_inherit` means:

- All existing Odoo stock logic (routes, transfers, quants) continues to work without modification.
- Warehouse/location hierarchy (`view_location_id`, `warehouse_view_ids`, `warehouse_id`) is already computed and stored by Odoo core — SOR does not reimplement it.
- Multi-company record rules from `stock` apply automatically.

### Why no new security rules

`stock.warehouse` and `stock.location` already have company-scoped record rules in `stock/security/ir.model.access.csv` and related security XML. SOR relies on these rules. No additional record rules are needed.

### Why `post_init_hook` for Storage Locations

The Odoo setting `group_stock_multi_locations` is not enabled by default in a fresh Odoo install. Without it, `stock.location` sub-locations (Rooms) are not visible in the UI. The `post_init_hook` enables this setting on module installation so users never have to find and enable it manually ("just works" composability principle).

```python
def post_init_hook(env):
    env['res.config.settings'].create({
        'group_stock_multi_locations': True,
    }).execute()
```

### Why `uninstall_hook` for menu restoration

Data XML (`menu_overrides.xml`) sets `stock.menu_action_warehouse_form` and `stock.menu_action_location_form` to `active = False`. Odoo does not automatically revert field-level changes on module uninstall (it only deletes records created by the module). The `uninstall_hook` explicitly restores these menus:

```python
def uninstall_hook(env):
    for xml_id in (
        'stock.menu_action_warehouse_form',
        'stock.menu_action_location_form',
    ):
        menu = env.ref(xml_id, raise_if_not_found=False)
        if menu:
            menu.active = True
```

---

## Models

### `SorViewingLocation` (`stock.warehouse`)

**File**: `models/stock_warehouse.py`

No new fields. Adds:

| Element | Purpose |
|---------|---------|
| `@api.constrains('partner_id')` `_check_partner_required` | Raises `ValidationError` if `partner_id` is empty. Prevents saving a Viewing Location without an address. |
| `@api.onchange('company_id')` `_onchange_company_id_check_address` | Returns a UI warning if the selected company has no `partner_id` configured, prompting the user to visit Settings → Companies. |

`stock.warehouse` already provides: `name`, `code`, `partner_id`, `company_id`, `view_location_id`, `warehouse_view_ids`.

### `SorRoom` (`stock.location`)

**File**: `models/stock_location.py`

| Element | Purpose |
|---------|---------|
| `viewing_location_id` | `fields.Many2one('stock.warehouse', related='warehouse_id', store=False)` — readable alias for `warehouse_id`, exposed in the Room form for clarity. Non-stored, so not usable in search view `<field>` elements or domain filters directly. |
| `@api.constrains('location_id', 'usage')` `_check_room_parent_is_viewing_location` | Raises `ValidationError` if an internal location's parent has `warehouse_id` set but is not itself a warehouse view location (`warehouse_view_ids` is empty). This catches the "Room nested inside another Room" case. |

`stock.location` already provides: `name`, `usage`, `location_id`, `warehouse_id` (computed, stored), `warehouse_view_ids`.

#### Constraint implementation note

The constraint uses `parent.warehouse_id` (the parent location's already-computed field) rather than `record.warehouse_id` (the new record's own field). At `create()` time the new record's `warehouse_id` may not yet be recomputed; the parent's `warehouse_id` is always available since the parent is an existing record.

```python
parent = record.location_id
if parent.warehouse_id and not parent.warehouse_view_ids:
    raise ValidationError(...)
```

---

## Views

### Viewing Location views (`stock_warehouse_views.xml`)

- Inherits `stock.view_warehouse` and `stock.view_warehouse_tree` to relabel headings as "Viewing Location(s)". Changes apply globally (no `mode="primary"`) because all warehouses in SOR are Viewing Locations.
- Defines `action_viewing_location_form` (`ir.actions.act_window`) bound to `stock.warehouse`.

### Room views (`stock_location_views.xml`)

- `view_room_list`: standalone list view showing Name and Viewing Location (via `warehouse_id`).
- `view_room_search`: search view using `warehouse_id` (not `viewing_location_id` — non-stored related fields are invalid in search `<field>` elements in Odoo 19). Group-by uses bare `<group>` (no `expand`/`string` attributes — not valid in Odoo 19 RNG schema).
- `view_room_form`: inherits `stock.view_location_form` with `mode="primary"` to create a standalone form that restricts the `location_id` domain to warehouse view locations only (`[('usage','=','view'),('warehouse_view_ids','!=',False)]`), preventing users from selecting another Room as parent via the UI.
- `action_room_form`: domain `[('usage','=','internal'),('warehouse_id','!=',False)]` to show only Rooms; `view_ids` eval binds list and form views explicitly.

### Menu suppression (`menu_overrides.xml`)

Sets `stock.menu_action_warehouse_form` and `stock.menu_action_location_form` to `active = False` for the duration of the module's install. Reversed by `uninstall_hook`.

---

## Tests

**File**: `tests/test_sor_locations.py`
**Pattern**: `@tagged('post_install', '-at_install')` + `TransactionCase`
**Run**: `python3 odoo-bin -d <db> --test-enable --test-tags=/sor_locations -u sor_locations --stop-after-init`

| Test | What it asserts |
|------|----------------|
| `test_create_viewing_location_with_rooms` | Rooms are internal; `warehouse_id` points to parent VL |
| `test_create_multiple_viewing_locations` | Independent VL hierarchies (SETU multi-building scenario) |
| `test_default_address_from_company` | `partner_id` defaults to `self.env.company.partner_id` |
| `test_partner_required_constraint` | `ValidationError` raised when `partner_id` is False |
| `test_storage_locations_enabled_after_install` | `stock.group_stock_multi_locations` is active after install |
| `test_company_scoping` | VL from Company A not visible to a user restricted to Company B (uses `with_user()`, not context alone — ORM record rules filter by `user.company_ids`) |
| `test_stock_menus_suppressed` | Standard Warehouses + Locations menus are `active = False` |
| `test_room_parent_must_be_viewing_location` | `ValidationError` raised when a Room is nested under another Room |
| `test_viewing_location_id_alias_on_room` | `room.viewing_location_id == room.warehouse_id` |

---

## Known Constraints

- `viewing_location_id` on `stock.location` is `store=False` (related field). It cannot be used in search view `<field>` elements or ORM domain filters directly. Use `warehouse_id` instead for those use cases.
- The Room constraint fires on `create` and `write`. The timing check (using `parent.warehouse_id` rather than `record.warehouse_id`) guards against computed-field recompute ordering at `create` time.
- Menu suppression via data XML plus `uninstall_hook` is a workaround for Odoo not reverting field changes on uninstall. If Odoo ever supports reversible data XML, this can be simplified.
