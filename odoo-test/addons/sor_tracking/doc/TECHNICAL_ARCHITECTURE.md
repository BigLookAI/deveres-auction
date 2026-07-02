# Technical Architecture: sor_tracking

## Overview

`sor_tracking` is a standalone SOR module (not a bridge) that delivers the physical movement infrastructure for external artwork flows. It depends only on Odoo's `stock` module — no other SOR modules are required. It provides the navigation, lifecycle field, form overrides, search filters, list customisations, and activity dashboard that form the foundation for all artwork movement recording in SOR.

```
stock (Odoo core)
      |
sor_tracking   ← standalone; not auto_install
```

Level 1 bridge modules extend `sor_tracking` at defined injection points in its views once they have additional context (agreements, paradigm rules, etc.).

---

## Module Pattern

**Manifest flags:**
```python
'category': 'Inventory',
'depends': ['stock'],
'application': False,
'auto_install': False,
'post_init_hook': 'post_init_hook',
```

- `application: False` — not a top-level App in the Odoo App Store sense; presented as an add-on to the stock module
- `auto_install: False` — must be explicitly installed; it does not activate automatically with `stock`
- `post_init_hook` — enables Multi-Location and Owner Tracking settings at install time
- `category: 'Inventory'` — appears in the Inventory category in Apps rather than Technical/Hidden

---

## Architecture Decisions

### Option C — native Odoo operation types

Three approaches were evaluated for Movement In / Movement Out / Internal Transfer identification:

| Option | Approach | Rejected because |
|--------|----------|-----------------|
| A | Custom `sequence_code` values ('MVI', 'MVO', 'MVT') on existing operation types | Fragile — depends on matching string values set by gallery admin; breaks if default types are renamed |
| B | Create entirely new `stock.picking.type` records at install | Doubles the available operation types; confuses staff who see both native and SOR types |
| **C** | Use Odoo's native operation types identified by `picking_type_id.code` ('incoming', 'outgoing', 'internal') | Correct — aligns with Odoo's own classification; warehouse creation provisions these types automatically; no data dependency on admin-configurable strings |

Option C is the implemented approach. All domain filters, SQL, and navigation use `picking_type_id.code` — not `sequence_code`.

### `sor_movement_state` as a separate field, not reusing Odoo `state`

Odoo's native `state` on `stock.picking` has values (`draft`, `confirmed`, `assigned`, `done`, `cancel`) that are tightly coupled to the inventory workflow (reservation, packing, validation). SOR's operational concept — "is this movement in the pipeline or has it happened?" — does not map cleanly to these values:

- A movement can be "Queued" while in `draft`, `confirmed`, or `assigned` state
- "Confirmed" in SOR means physically completed — which is `done` in Odoo
- "Cancelled" maps to `cancel`, but the transition rules differ

A separate `sor_movement_state` field avoids coupling SOR business logic to Odoo's internal state machine and allows the state to be set independently of whether the picking has been fully validated in Odoo's inventory workflow.

### TransientModel dashboard with raw SQL

Three dashboard approaches were evaluated (see Story 05 T1 finding):

| Option | Rejected because |
|--------|-----------------|
| Kanban grouped by `sor_movement_state` | Single kanban cannot show Movement In and Movement Out in separate labelled sections |
| `ir.actions.client` + OWL template | Requires custom JS; maintenance burden for a simple count display |
| **TransientModel + form view with `oe_stat_button`** | Native pattern; no JS; SQL aggregation in one query; `@api.model` buttons fire without saved record |

The raw SQL aggregate query retrieves all counts in a single round-trip. It must be explicitly scoped to `company_id` because `env.cr.execute()` bypasses `ir.rule` multi-company filters.

### `oe_stat_button` layout — `<separator>` + `<div class="oe_button_box">` directly under `<sheet>`

`<div class="oe_button_box">` placed inside a `<group>` element does not get the CSS flex context that the `statinfo` widget requires — the number and label render concatenated ("3Queued") rather than as a two-line tile. The correct pattern is:

1. `<separator string="Section Title" invisible="..."/>` directly under `<sheet>` for the section heading
2. `<div class="oe_button_box" invisible="...">` directly under `<sheet>` for the button row

Both elements carry the same `invisible` expression so that when all counts in a section are zero, both the heading and the button row are hidden together.

### Pool locations — company-scoped, not global virtual locations

Odoo's default installation includes global virtual locations (`Vendors`, `Customers`) with `company_id = False`. These are shared across all companies and cannot be made company-specific. SOR movements use a domain that explicitly excludes `company_id = False` locations from pickers — so the Odoo-native global virtuals are invisible to staff.

`sor_tracking` provisions **company-scoped** equivalents: Partners/External (internal), Vendors/External (supplier), Buyers/External (customer), all under a company-owned External view location. These appear in pickers because they carry the correct `company_id`. This preserves the "external staging area" concept without the cross-company visibility problems of global virtuals.

Pool locations are provisioned by `_ensure_pool_locations()` in `hooks.py` and called from three paths:
1. `post_init_hook` — at install time, for all existing companies
2. `res.company.create()` — when a new company is created (browser flow)
3. `stock.warehouse.create()` — when a warehouse is created after the company (production flow)

All three paths call the same idempotent helper.

### Picking type inference from locations (server-side)

`picking_type_id` is marked `readonly="1"` in the form view — the value is inferred from locations and staff cannot override it. Odoo 19's OWL framework excludes static `readonly="1"` fields from create/write RPC payloads. The server must re-infer the value in both `create()` and `write()` overrides. The inference logic is extracted into `_sor_infer_picking_type_id()` and shared with the `@api.onchange` handler to avoid duplication.

### `action_cancel` override, not `_action_cancel`

In Odoo 19, `stock.picking.action_cancel()` does NOT call `_action_cancel()` on the picking — it calls `move_ids._action_cancel()` on the moves. Overriding `_action_cancel` on `stock.picking` is dead code. The correct hook is `action_cancel`. (See `odoo_conventions.md` for the full pattern.)

---

## Models

### `stock.picking` (extended)

**File:** `models/stock_picking.py`

| Field/Method | Type | Notes |
|---|---|---|
| `sor_movement_state` | `Selection` | `('queued','confirmed','cancelled')`. Default: `'queued'`. `copy=False`. `index=True`. `store=True`. |
| `sor_movement_state_label` | `Char` (computed) | Direction-aware display label. `@api.depends('sor_movement_state','picking_type_id.code')`. `store=False`. |
| `sor_movement_hint` | `Char` (computed) | Contextual instruction text. `@api.depends('sor_movement_state','picking_type_id.code')`. `store=False`. Empty when not queued. |
| `_sor_infer_picking_type_id(loc_id, dest_id)` | `@api.model` method | Returns inferred `stock.picking.type` ID from location usages, or `False`. |
| `_sor_infer_partner_id(loc_id, dest_id)` | instance method | Returns partner_id inferred from `stock.location.partner_id`, or `False`. Checks source location first (incoming/internal), then destination (outgoing). Defensive: returns `False` immediately if `partner_id` is not a field on `stock.location` (requires `sor_locations_external`). |
| `_onchange_sor_infer_picking_type()` | `@api.onchange` | UI-side inference on location change; infers both `picking_type_id` and `partner_id` (if not already set). Restores user location selections after Odoo's native `_onchange_picking_type` overwrites them. |
| `create(vals_list)` | `@api.model_create_multi` | Infers `picking_type_id` and `partner_id` server-side when absent from OWL payload. |
| `write(vals)` | standard override | Validates `sor_movement_state` transitions before writing; re-infers `picking_type_id` on location changes. |
| `_sor_movement_state_transition_allowed(from, to)` | instance method | State machine: `queued→confirmed`, `queued→cancelled` allowed; `confirmed` and `cancelled` are terminal. |
| `_get_source_location_discrepancies()` | instance method | Returns subset of `move_ids` where `location_id` ≠ `product_id.current_location_id`. Returns empty recordset immediately when `current_location_id` not in `product.template._fields`. Called by `button_validate()`. |
| `button_validate()` | override | (1) Fires `sor.movement.source.location.confirm` wizard when source location discrepancies exist (checked first). (2) Fires `sor.movement.location.confirm` wizard when artworks have an existing `current_location_id` (checked after source). Both checks are skipped when the relevant context flag is set by the wizard's `action_confirm()`. |
| `_action_done()` | override | Transitions `sor_movement_state` to `confirmed`; updates `current_location_id` on artworks if `sor_locations_artwork` is installed. |
| `action_cancel()` | override | Transitions `sor_movement_state` to `cancelled`. |

### `sor.tracking.dashboard` (TransientModel)

**File:** `models/sor_tracking_dashboard.py`

| Field/Method | Type | Notes |
|---|---|---|
| `name` | `Char` | Default: `'Movement Activity'`. Required for breadcrumb display in Odoo 19. |
| `mvi_queued` | `Integer` (computed) | `@api.depends()` with no args. |
| `mvi_confirmed` | `Integer` (computed) | |
| `mvi_cancelled` | `Integer` (computed) | |
| `mvo_queued` | `Integer` (computed) | |
| `mvo_confirmed` | `Integer` (computed) | |
| `mvo_cancelled` | `Integer` (computed) | |
| `mvt_queued` | `Integer` (computed) | |
| `_compute_counts()` | compute method | Single raw SQL `GROUP BY pt.code, sp.sor_movement_state` scoped to `sp.company_id = %(company_id)s`. Bypasses `ir.rule` — must scope explicitly. |
| `_picking_action(type_code, state)` | `@api.model` | Builds `ir.actions.act_window` dict for `stock.picking` with domain `[('picking_type_id.code','=',type_code),('sor_movement_state','=',state)]`. |
| `action_view_mvi_queued(*args)` (×7) | `@api.model` | Stat button targets. `*args` absorbs the extra positional argument that Odoo 19 `call_kw` passes to `@api.model` methods. |

### `sor.movement.location.confirm` (TransientModel)

**File:** `models/sor_movement_location_confirm.py`

Wizard that intercepts `button_validate()` when `sor_locations_artwork` is installed and the movement contains artworks with an existing `current_location_id`. Renders a confirmation dialog before proceeding with validation and location update.

| Field/Method | Notes |
|---|---|
| `picking_id` | `Many2one('stock.picking')` |
| `action_open()` | Returns `ir.actions.act_window` with `target='new'` (modal) and `name='Confirm Location Update'` — SOR-branded dialog title. |
| `action_confirm()` | Calls `picking_id.with_context(sor_skip_location_confirm=True).button_validate()` |

### `sor.movement.source.location.confirm` (TransientModel)

**File:** `models/sor_movement_source_location_confirm.py`

Wizard that intercepts `button_validate()` when the movement's declared source location does not match an artwork's recorded `current_location_id` (requires `sor_locations_artwork`). Fires before `sor.movement.location.confirm` in the validation sequence. Presents a formatted discrepancy list so staff can review before proceeding.

| Field/Method | Notes |
|---|---|
| `picking_id` | `Many2one('stock.picking')` |
| `discrepancy_info` | `Text`, `readonly=True` — formatted multi-line string: one bullet per discrepant move, showing artwork name, system-recorded location, and declared source |
| `action_confirm()` | Calls `picking_id.with_context(skip_source_location_check=True, sor_skip_location_confirm=True).button_validate()` — both flags prevent double-confirm: source check is bypassed and destination dialog is also suppressed on the second pass. |
| `action_cancel()` | Returns `ir.actions.act_window_close` — closes dialog without validating |

### `res.company` (extended)

**File:** `models/res_company.py`

`create()` override that calls `_ensure_pool_locations()` for each new company. Ensures pool locations exist when a company is created in production (where `stock.warehouse.create` is not called from within `res.company.create`). Idempotent — `_ensure_pool_locations` searches before creating.

### `stock.warehouse` (extended)

**File:** `models/stock_warehouse.py`

`create()` override that calls `_ensure_pool_locations()` for each new warehouse's company. Handles production case where a warehouse is created separately after the company. The dual-hook pattern (`res.company.create` + `stock.warehouse.create`) ensures pool locations are always provisioned regardless of the creation path.

---

## Views

### List view — `view_picking_list_sor_tracking` (mode: primary)

**File:** `views/stock_picking_views.xml`

Primary-mode inheritance from `stock.vpicktree`. Creates a standalone SOR list view bound to all four window actions via explicit `ir.actions.act_window.view` binding records (required in Odoo 19 — `view_id` on the action is unreliable for list views).

Key customisations:
- Row colour coding: `decoration-success` for confirmed, `decoration-muted` for cancelled
- `sor_movement_state` declared with `column_invisible="1"` — provides decoration data without rendering a column
- `partner_id` and `scheduled_date` made default-visible (native has `optional="show"`)
- `sor_movement_state_label` added as "Status" column after `scheduled_date`
- `owner_id` added as "Beneficial Owner" column (`optional="show"`, `readonly` when not queued)
- Native columns suppressed: `state` badge, `origin`, `company_id`, `priority`, `location_id`, `location_dest_id`

### Search view — `view_picking_search_sor_tracking`

Inherits `stock.view_picking_internal_search`. Adds three SOR state filters (Queued / Confirmed / Cancelled) after the native `available` filter, separated by a `<separator/>`.

### Form view — `view_picking_form_sor_tracking`

Inherits `stock.view_picking_form`. Key overrides:
- Both native `state` statusbars hidden (`invisible="1"`)
- `sor_movement_state` statusbar added before the native Cancel button
- Contextual hint box added above the first form group (alert-info, hidden when hint is empty)
- Named group `sor_tracking_agreement_info` added after the first group — injection point for Level 1 bridges
- `owner_id` shown for incoming and outgoing (removes native incoming-only restriction); locked when not queued
- Location dropdowns restricted to `usage in ['internal','customer','supplier']` with `company_id != False`
- Both location fields made always-visible (overrides native direction-dependent hiding)
- `picking_type_id` locked with `readonly="1"` unconditionally

### Dashboard form view — `view_sor_tracking_dashboard_form`

`create="0" edit="0" delete="0"` on the `<form>` tag, with `context={'form_view_initial_mode': 'readonly'}` on the window action — suppresses Save/Discard buttons on the TransientModel new record.

`<field name="name" invisible="1"/>` declared in the arch so Odoo resolves the breadcrumb display name correctly.

Each `<group>` section (Movement In, Movement Out, Internal Transfers) has an `invisible` expression that hides the entire section when all its child stat tiles are zero. Each stat button has `invisible="fieldname == 0"` to hide zero-count tiles individually.

Named injection points for bridges:
```xml
<div name="sor_tracking_dashboard_external"/>
<div name="sor_tracking_dashboard_agreement_alerts"/>
```

---

## Module File Structure

```
sor_tracking/
├── __manifest__.py          — module declaration; post_init_hook registered
├── __init__.py              — imports models; imports post_init_hook
├── hooks.py                 — post_init_hook: enables Multi-Location + Owner Tracking settings
├── models/
│   ├── __init__.py          — imports all model files
│   ├── stock_picking.py     — sor_movement_state field + lifecycle; inference logic; default_get; validation wizards
│   ├── sor_tracking_dashboard.py — TransientModel dashboard with SQL aggregation
│   ├── sor_movement_location_confirm.py — destination location update confirmation wizard
│   ├── sor_movement_source_location_confirm.py — source location discrepancy alert wizard
│   ├── res_company.py       — create() override: provisions pool locations for new companies
│   └── stock_warehouse.py   — create() override: provisions pool locations when warehouse created in production
├── views/
│   ├── stock_picking_views.xml         — list/search/form view overrides for stock.picking
│   ├── sor_tracking_dashboard_views.xml — dashboard form view + window action
│   ├── sor_movement_location_confirm_views.xml — wizard form view
│   └── menus.xml            — window actions, view bindings, navigation menus, inventory menu suppression
├── security/
│   └── ir.model.access.csv  — read/write/create access for both TransientModels
├── migrations/
│   └── 19.0.1.x.0/          — post-migrate scripts for field renames across sprint iterations
├── i18n/
│   └── sor_tracking.pot     — translatable string catalogue
├── tests/
│   ├── __init__.py
│   └── test_sor_tracking.py — full test suite (module install, state machine, labels, hints, owner, inference, dashboard SQL)
└── doc/
    ├── KNOWLEDGE_BASE.md    — staff-facing operational guide
    └── TECHNICAL_ARCHITECTURE.md — this file
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/stock_picking.py` | Core: `sor_movement_state` field, state machine, inference, `action_cancel`, `_action_done` |
| `models/sor_tracking_dashboard.py` | Dashboard: SQL aggregation, `@api.model` button methods, company scoping |
| `views/stock_picking_views.xml` | Primary list view, search view, form view |
| `views/sor_tracking_dashboard_views.xml` | Dashboard form view and window action |
| `views/menus.xml` | Navigation structure, window actions, view bindings, inventory menu suppression |
| `hooks.py` | Enables required inventory settings at install |
| `security/ir.model.access.csv` | Access control for TransientModels |

---

## Composability Boundary

| Module combination | Features available |
|---|---|
| `stock` only | Native Odoo Inventory — no SOR tracking |
| `stock` + `sor_tracking` | Movements navigation, `sor_movement_state` lifecycle, dashboard, location-inferred operation type, beneficial owner on MVI + MVO, pool locations |
| + `sor_locations_artwork` | Destination confirmation wizard before validation; source location discrepancy alert before validation; artwork `current_location_id` updated on `_action_done` |
| + `sor_artwork` | `sor_tracking_artwork` bridge auto-installs: serial tracking defaults for artworks; "Serial Numbers" label correction |
| + `sor_asset_paradigm` | `sor_tracking_asset_paradigm` bridge auto-installs: `sor_all_unique_objects` computed field; Demand/Quantity column suppression; qty default = 1 for unique objects |
| + `sor_legal_agreement` | `agreement_id` on `stock.picking` available; injection group `sor_tracking_agreement_info` populated by bridge |
| + *(future)* `sor_tracking_legal_agreement` | Agreement-aware counts and stale agreement alerts on dashboard |

---

## Special Concerns

### Raw SQL bypasses `ir.rule` multi-company filters

`_compute_counts` uses `env.cr.execute()` — a direct cursor call that bypasses all Odoo record-level security rules including multi-company `ir.rule`. The query must explicitly filter `AND sp.company_id = %(company_id)s` with `self.env.company.id`. Without this filter, counts aggregate records from all companies regardless of the user's active company session.

**This applies to any future extension that adds raw SQL to this dashboard.** Any `SELECT ... FROM stock_picking` without `company_id` scoping will produce inflated cross-company counts.

### `@api.model` button methods require `*args` in Odoo 19

Odoo 19's `call_kw` layer passes an extra positional argument (the record ID — `[false]` for TransientModel new records) to `@api.model` methods before stripping. Without `*args`, the method signature raises `TypeError: takes 1 positional argument but 2 were given`. All seven `action_view_*` methods include `*args` in their signatures.

### `readonly="1"` fields excluded from OWL save payloads

`picking_type_id` is `readonly="1"` in the form view. Odoo 19's OWL excludes unconditionally readonly fields from create/write RPC payloads. `create()` and `write()` must infer the value server-side. The inference logic is shared between the onchange handler and both ORM overrides via `_sor_infer_picking_type_id()`.

### Navigation menu suppression is `noupdate="1"`

The native Inventory top-level menu suppression (`stock.menu_stock_root active=False`) is wrapped in `<data noupdate="1">`. Without this, `-u sor_tracking` would reset the `active` field to `True` on every upgrade, making the native Inventory menu reappear.

### `action_cancel` not `_action_cancel`

In Odoo 19, the `button_cancel` UI action calls `action_cancel()`, which cancels the moves via `move_ids._action_cancel()` — it does not call `picking._action_cancel()`. Overriding `_action_cancel` on `stock.picking` is dead code in Odoo 19. The `sor_movement_state` → `cancelled` transition is set in `action_cancel()`.

### `button_validate` guard for `sor_locations_artwork`

The `button_validate()` override checks `'current_location_id' in self.env['product.template']._fields` before attempting to access the field. This ensures `sor_tracking` can be installed without `sor_locations_artwork` and that validation works normally without the bridge.

### Pool location provisioning — dual-hook required

In Odoo 19, `stock.res_company.create` only calls `stock.warehouse` creation during automated tests (`modules.module.current_test`). In production, the warehouse is created separately. To ensure pool locations exist regardless of how companies and warehouses are created, `sor_tracking` uses a **dual-hook** pattern:

- `res.company.create()` — fires when a company is created; provisions pool locations for that company
- `stock.warehouse.create()` — fires when a warehouse is created; provisions pool locations for the warehouse's company

Both call the same idempotent `_ensure_pool_locations(env, company)` helper (which searches before creating). The `post_init_hook` covers existing companies at install time. See `orm_and_field_patterns.md` § "stock.warehouse is not created inside res.company.create in production".

### `button_validate` — two-stage wizard interception

The `button_validate()` override intercepts validation at two points, in order:

1. **Source location check** (`skip_source_location_check` context flag not set): calls `_get_source_location_discrepancies()`. If non-empty, opens `sor.movement.source.location.confirm` wizard with formatted discrepancy lines.
2. **Destination location check** (`sor_skip_location_confirm` context flag not set): checks whether any moved products have an existing `current_location_id`. If so, opens `sor.movement.location.confirm` wizard.

Both checks are guarded by `'current_location_id' in self.env['product.template']._fields` — the checks are entirely skipped when `sor_locations_artwork` is not installed. Setting `sor_skip_location_confirm=True` skips **both** checks (the source wizard sets `skip_source_location_check`; the destination wizard sets `sor_skip_location_confirm`).

### Defensive field check pattern for optional bridge fields

`sor_tracking` is bridge-agnostic — it must not raise `AttributeError` when optional bridge modules are absent. Any method that accesses a field added by a bridge or optional module must guard with `'field_name' in self.env['model']._fields` before accessing the field. Current instances:

- `_sor_infer_partner_id`: checks `'partner_id' in self.env['stock.location']._fields` — `partner_id` is only present when `sor_locations_external` is installed.
- `button_validate()`: checks `'current_location_id' in self.env['product.template']._fields` — only present with `sor_locations_artwork`.

Apply this same guard in any future method that reads a field from an optional bridge module.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_tracking
```

Expected: `0 failed, 0 error(s) of 30 tests`

---

## Story Reference

Sprint 11 — SOR Tracking:
- Story 01: Movement form and operation type
- Story 02: `sor_movement_state` field and state machine
- Story 03: Movements navigation (menus, list views)
- Story 04: Beneficial owner and return picking
- Story 05: Movement Activity Dashboard

Movement Enhancements sprint:
- Story 02: Pool Locations — `_ensure_pool_locations`, `res_company.py`, `stock_warehouse.py`
- Story 03: Source Location Alert — `sor.movement.source.location.confirm`, `_get_source_location_discrepancies`; double-confirm prevention via `sor_skip_location_confirm` context flag; SOR-branded dialog title on `sor.movement.location.confirm.action_open()`
- UAT Issue 18: Removed erroneous `default_get` override that set `name='New'` on pickings — native Odoo create() sequence assignment requires the `name` field to be absent from `default_get` (condition: `defaults.get('name', '/') == '/'`)
