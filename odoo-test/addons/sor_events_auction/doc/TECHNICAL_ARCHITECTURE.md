# Technical Architecture: sor_events_auction

## Overview

`sor_events_auction` is a **bridge module** that delivers the events-to-lots linkage — the composable intersection of auction event management and lot catalogue management that only makes sense when both `sor_events` and `sor_lotting` are installed simultaneously:

```
sor_events            sor_lotting
      \                   /
       \                 /
   sor_events_auction    (auto_install=True, application=False)
```

Neither parent module is modified. The bridge activates automatically when both parents are present. It extends `sor.event` with auction-specific metadata fields and the lot catalogue relationship, extends `sor.lot` with the `auction_id` assignment field and the `live` state, enforces a within-auction lot number uniqueness constraint, and provides the Go Live action that opens an auction sale and simultaneously cascades all catalogued lots to live status.

---

## Module Pattern

**Manifest flags:**

```python
'category': 'Hidden/Technical',
'depends': ['sor_events', 'sor_lotting'],
'auto_install': True,
'application': False,
```

- `auto_install: True` — Odoo installs the bridge automatically when both `sor_events` and `sor_lotting` are present. No manual install step required.
- `application: False` — The bridge does not appear as a top-level App in the Odoo Apps menu.
- `category: 'Hidden/Technical'` — Excluded from business category listings; the bridge is infrastructure, not a user-facing application.
- No `summary` field — bridge modules carry no marketing metadata by convention.
- No `ir.model.access.csv` is needed because the bridge adds no new models; it only extends existing ones via `_inherit`.

**Why a bridge?** `sor_events` must be installable without lot catalogue features — an exhibition manager does not need `sor_lotting`. `sor_lotting` must be installable without event management — a cataloguer working outside live sales does not need `sor_events`. Placing `auction_id` in `sor_lotting` would introduce a hard dependency; placing it in `sor_events` would introduce the same dependency in reverse. The bridge carries the coupling; both parents remain independently installable.

---

## Architecture Decisions

### Why bridge, not base module modification

The `auction_id` field on `sor.lot` is only meaningful when `sor_events` is installed — it references `sor.event`. Adding it to `sor_lotting` directly would require `sor_lotting` to depend on `sor_events`, violating the SOR composability rule that no base module may depend on another base module. The bridge is the only architecturally correct location for this field.

### selection_add — ordering limitation

`selection_add` in Odoo appends values to the end of the selection list by default. The desired statusbar order is `draft → catalogued → live → sold → passed → withdrawn`, but `selection_add` appends `live` at the end: `..., sold, passed, withdrawn, live`. This does not affect field storage or logic — the value `'live'` is a string in the database, not an integer position. The ordering concern is purely visual on the statusbar widget. The bridge compensates by patching `statusbar_visible` on the lot form view to explicitly declare the correct display sequence:

```xml
<attribute name="statusbar_visible">draft,catalogued,live,sold,passed,withdrawn</attribute>
```

This gives the correct visual order regardless of the underlying selection list order. Future bridge modules that add further lot states must read the current `statusbar_visible` patch and include all existing values plus their own addition to avoid overwriting prior patches.

### Direct write for live state, not a lot action method

`action_go_live()` on `sor.event` writes `{'state': 'live'}` directly on the filtered lot recordset:

```python
catalogued_lots.write({'state': 'live'})
```

The alternative — calling a `lot.action_go_live()` method — is architecturally incorrect here. The `live` state is introduced by this bridge via `selection_add`; it does not exist on `sor.lot` in a `sor_lotting`-only install. Adding `action_go_live()` to `sor.lot` directly would require `sor_lotting` to carry bridge-level logic. The direct write pattern is appropriate: the bridge owns the `live` state and is the only caller of the transition that leads to it.

### models.Constraint, not _sql_constraints

The unique constraint on `(auction_id, lot_number)` uses `models.Constraint` as a class-level attribute:

```python
_auction_lot_number_unique = models.Constraint(
    'UNIQUE(auction_id, lot_number)',
    'Lot number must be unique within an auction.',
)
```

In Odoo 19, `_sql_constraints` is silently ignored — the constraint is never applied to the database. `models.Constraint` is the only supported mechanism. Import is via `from odoo import models`; `Constraint` is accessed as `models.Constraint`.

### ondelete policy on auction_id

`auction_id` uses `ondelete='restrict'`: an auction event that has lots assigned cannot be deleted at the database level. This is the correct policy — deleting an auction with a live catalogue would orphan lot records. Staff must reassign or unlink lots before an auction event can be removed.

### check_company=True on auction_id

`check_company=True` on `auction_id` delegates cross-company enforcement to Odoo's ORM via the `_check_company_auto = True` flag on `sor.lot`. At write time, the ORM verifies that the referenced `sor.event` belongs to the same company as the `sor.lot`. A cross-company assignment raises `UserError` (not `ValidationError`) — this matters in test assertions.

---

## Models

### sor.event (extended)

`models/sor_event_auction.py` — `_inherit = 'sor.event'`

| Field / Method | Type | Notes |
|----------------|------|-------|
| `auction_subtype` | `Selection` | Values: `live`, `online_only`, `hybrid`. Optional. `tracking=True` for chatter. |
| `sale_number` | `Char` | Free-form external sale number. Optional. |
| `preview_start` | `Datetime` | Preview period start. Optional. |
| `preview_end` | `Datetime` | Preview period end. Optional. |
| `lot_ids` | `One2many('sor.lot', 'auction_id')` | All lots linked to this auction. |
| `lot_count` | `Integer` | Computed via `_compute_lot_count`. `store=False`. `@api.depends('lot_ids')`. |
| `_compute_lot_count(self)` | Method | `event.lot_count = len(event.lot_ids)` |
| `action_go_live(self)` | Method | See detailed description below. |

#### action_go_live() logic

```python
for event in self:
    if event.status != 'published':
        raise UserError(...)
    event.status = 'active'
    event.message_post(...)
    catalogued_lots = event.lot_ids.filtered(lambda lot: lot.state == 'catalogued')
    if catalogued_lots:
        catalogued_lots.write({'state': 'live'})
        event.message_post(...)
```

- Guard: raises `UserError` with event name and current status label if not `published`.
- Sets `event.status = 'active'` (the standard `active` value defined by `sor_events`).
- Filters to catalogued lots only — draft lots are excluded by design.
- Writes `live` directly on the filtered recordset — no per-lot method call.
- Posts two chatter messages: one for the event opening, one for the lot count.

### sor.lot (extended)

`models/sor_lot_auction.py` — `_inherit = 'sor.lot'`

| Field / Constraint | Type | Notes |
|--------------------|------|-------|
| `auction_id` | `Many2one('sor.event')` | Domain: `[('event_type', '=', 'auction')]`. `check_company=True`. `ondelete='restrict'`. Optional. |
| `state` | `Selection` (extended) | `selection_add=[('live', 'Live')]`. `ondelete={'live': 'set default'}`. The `ondelete` policy is required on `required` selection fields in Odoo 16+; omitting it raises `ValueError` at registry load time. |
| `_auction_lot_number_unique` | `models.Constraint` | `UNIQUE(auction_id, lot_number)`. Applied at the database level. Constraint name suffix on the table: `sor_lot__auction_lot_number_unique`. |

**ondelete={'live': 'set default'} rationale:** If `sor_events_auction` were uninstalled, any `sor.lot` records in `live` state would have an invalid `state` value. The `'set default'` policy reverts those records to the field's default (`'draft'`), preventing orphaned state values. In practice, uninstalling `sor_events_auction` when live auction data exists is inadvisable; this is a safety net, not an operational workflow.

---

## Views

All view inheritance is in `views/sor_events_auction_views.xml`.

### sor.event — Go Live header button

**Record ID:** `sor_event_view_form_go_live_button`
**Inherits:** `sor_events.sor_event_view_form`
**Mode:** non-primary (standard patch)

Inserts a **Go Live** primary button in `//header` before the `status` statusbar field. Invisible when `event_type != 'auction'` or `status not in ('draft', 'published')` — hidden after the auction is already live, closed, or archived.

### sor.event — Lots stat button

**Record ID:** `sor_event_view_form_lots_button`
**Inherits:** `sor_events.sor_event_view_form`
**Mode:** non-primary

The base `sor.event` form has no `button_box` div. This patch inserts one before the first `<group>` inside `<sheet>`, then places a `lot_count` stat button inside it. The stat button triggers `sor_lot_action_from_event` (window action filtered by `active_id`). Invisible when `event_type != 'auction'`.

### sor.event — Auction Details tab

**Record ID:** `sor_event_view_form_auction_tab`
**Inherits:** `sor_events.sor_event_view_form`
**Mode:** non-primary

Appends an **Auction Details** page to `//notebook` on the event form. Invisible when `event_type != 'auction'`. Contains two field groups (subtype + sale number; preview dates) and an inline `lot_ids` list with key lot columns (`lot_number`, `lot_suffix`, `product_id`, `state`, `reserve_price`). `currency_id` is declared with `column_invisible="1"` to satisfy the Monetary widget's currency dependency without rendering a column.

### sor.lot — auction_id field on form

**Record ID:** `sor_lot_view_form_auction_id`
**Inherits:** `sor_lotting.sor_lot_view_form`
**Mode:** non-primary

Inserts a `<group>` containing `auction_id` before the `<notebook>` on the lot form, at the D2 bridge injection point annotated in the base view.

### sor.lot — live state in statusbar

**Record ID:** `sor_lot_view_form_statusbar_live`
**Inherits:** `sor_lotting.sor_lot_view_form`
**Mode:** non-primary

Patches the `statusbar_visible` attribute on `//field[@name='state'][@widget='statusbar']` to add `live` in the correct visual position: `draft,catalogued,live,sold,passed,withdrawn`. This corrects the visual ordering that `selection_add` alone cannot control.

### sor.lot — auction_id column on list view

**Record ID:** `sor_lot_view_list_auction_id`
**Inherits:** `sor_lotting.sor_lot_view_list`
**Mode:** non-primary

Inserts an `auction_id` column before `lot_reference` on the global lots list so auction context is visible at a glance.

### Window actions

| Record ID | Description |
|-----------|-------------|
| `sor_lot_action_from_event` | Opens `sor.lot` list filtered by `auction_id = active_id`. Used by the stat button. |
| `sor_auction_action_all` | Opens all auction events. Uses standalone `sor_auction_view_list`. |
| `sor_auction_action_live` | Opens active auction events only (`status = 'active'`). |
| `sor_auction_action_upcoming` | Opens draft and published auction events. |
| `sor_auction_action_past` | Opens closed and archived auction events. |

### Standalone list view

**Record ID:** `sor_auction_view_list` — A `mode=primary` equivalent standalone list for `sor.event` scoped to auction columns: Name, Sale Number, Auction Subtype, Start Date, End Date, Lot Count, Status. Used by all four auction window actions. This provides a focused auction-optimised list without affecting the base `sor.event` list view.

### Menus

| Menu ID | Name | Parent | Sequence | Action |
|---------|------|--------|----------|--------|
| `menu_sor_auctions_root` | Auctions | (root) | 110 | `sor_auction_action_all` |
| `menu_sor_auctions_live` | Live | root | 10 | `sor_auction_action_live` |
| `menu_sor_auctions_upcoming` | Upcoming | root | 20 | `sor_auction_action_upcoming` |
| `menu_sor_auctions_past` | Past | root | 30 | `sor_auction_action_past` |

The Auctions root menu is placed at sequence 110 (before the Lots menu from `sor_lotting` at sequence 120) so Auctions appears above Lots in the navigation sidebar.

---

## Module File Structure

```
addons/sor_events_auction/
├── __init__.py                              # imports models package
├── __manifest__.py                          # auto_install=True; depends=['sor_events','sor_lotting']
├── models/
│   ├── __init__.py                          # imports sor_event_auction, sor_lot_auction
│   ├── sor_event_auction.py                 # extends sor.event: auction fields + action_go_live()
│   └── sor_lot_auction.py                   # extends sor.lot: auction_id, live state, constraint
├── views/
│   └── sor_events_auction_views.xml         # all view patches, window actions, menus
├── i18n/
│   └── sor_events_auction.pot               # translatable strings
├── tests/
│   ├── __init__.py                          # imports test_sor_events_auction
│   └── test_sor_events_auction.py           # 16 tests covering all confirmed ACs
└── doc/
    ├── KNOWLEDGE_BASE.md                    # user-facing feature documentation
    └── TECHNICAL_ARCHITECTURE.md           # this file
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | `auto_install=True`, `depends=['sor_events','sor_lotting']` — the composability declaration |
| `models/sor_event_auction.py` | Auction fields on `sor.event`; `_compute_lot_count`; `action_go_live()` |
| `models/sor_lot_auction.py` | `auction_id` field; `live` state via `selection_add`; `UNIQUE(auction_id, lot_number)` constraint |
| `views/sor_events_auction_views.xml` | All view patches, standalone list view, window actions, menus |
| `tests/test_sor_events_auction.py` | 16 automated tests covering all confirmed ACs |

---

## Composability Boundary

| Feature | `sor_events` only | `sor_lotting` only | Both installed |
|---------|--------------------|---------------------|----------------|
| `auction_id` on `sor.lot` | ✗ absent | ✗ absent | ✓ present (bridge) |
| `live` state on `sor.lot` | ✗ absent | ✗ absent | ✓ present (bridge) |
| `lot_ids` / `lot_count` on `sor.event` | ✗ absent | ✗ absent | ✓ present (bridge) |
| Auction Details tab on event form | ✗ absent | ✗ absent | ✓ present (bridge) |
| Go Live button on event form | ✗ absent | ✗ absent | ✓ present (bridge) |
| Lots stat button on event form | ✗ absent | ✗ absent | ✓ present (bridge) |
| Auctions navigation menu | ✗ absent | ✗ absent | ✓ present (bridge) |
| `UNIQUE(auction_id, lot_number)` constraint | ✗ absent | ✗ absent | ✓ enforced (bridge) |

---

## Special Concerns

### selection_add ordering limitation

`selection_add` appends values to the end of the selection list. The `live` value will appear after `withdrawn` in the raw selection if only `selection_add` is used. The `statusbar_visible` attribute on the lot form view statusbar widget is patched explicitly to restore the intended visual order. Any future bridge that adds additional lot states must read the current `statusbar_visible` patch and include all prior values plus its own new value — otherwise it will overwrite this patch and remove `live` from the displayed sequence.

### auction_id immutability

Once a lot is assigned to an auction and the auction has transitioned past Draft, changing `auction_id` could disrupt catalogue numbering and live sale state. The current implementation does not enforce immutability at the model layer — this is noted as a future hardening concern for `sor_bidding` or `sor_commercial_auction_house`. Bridge builders downstream should not assume `auction_id` is stable unless an explicit `readonly` guard has been added.

### ondelete policy requirement for required Selection fields

Odoo 16+ requires an `ondelete` policy when `selection_add` extends a `required` Selection field. Omitting it raises:

```
ValueError: 'sor.lot.state': required selection fields must define an ondelete policy
```

This bridge uses `ondelete={'live': 'set default'}`. The `'set default'` policy reverts `live` records to the field's declared `default` (`'draft'`) if the bridge is uninstalled. See `odoo_conventions.md` for the full pattern.

### No ir.model.access.csv

The bridge adds no new models — only `_inherit` extensions. No `ir.model.access.csv` is required. Access to `sor.event` and `sor.lot` is governed by the access rules defined in `sor_events` and `sor_lotting` respectively.

### active_id in view domain

The `sor_lot_action_from_event` window action uses `active_id` in its `domain` and `context` fields:

```xml
<field name="domain">[('auction_id', '=', active_id)]</field>
<field name="context">{'default_auction_id': active_id}</field>
```

`active_id` is valid in window action XML domains and context fields because these are evaluated at action dispatch time, not at view parse time. The Odoo 19 restriction against `active_id` in view `context=` attributes (field-level context) does not apply here. See `odoo_conventions.md` for the distinction.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_events_auction
```

See `docker_dev_workflow.md` for the full Docker upgrade and restart workflow.

---

## Story Reference

Parent story: `.backlog/current/Auction Engine/stories/03_Events-Auction-Bridge.md`
Sprint: Sprint 09 — Auction Engine
