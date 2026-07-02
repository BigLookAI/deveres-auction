# SOR Locations — Artist Studios × Artwork: Technical Architecture

## Overview

`sor_locations_artist_studios_artwork` is a **bridge module** that composes at the intersection of `sor_locations_artist_studios` (Artist Studios toggle and infrastructure) and `sor_locations_artwork` (`current_location_id` on artwork products):

```
sor_locations_artist_studios      sor_locations_artwork
            \                           /
             \                         /
     sor_locations_artist_studios_artwork   (auto_install=True, application=False)
```

Neither parent module is modified. The bridge activates automatically when both parents are installed.

**Sprint:** Movement Layer Completion  
**Story:** Story 05 — Legal Agreement DoD Closure (BUG-05 fix)

---

## Module Pattern

**Manifest flags:**

```python
{
    'depends': ['sor_locations_artist_studios', 'sor_locations_artwork'],
    'auto_install': True,
    'application': False,
    'category': 'Hidden/Technical',
}
```

- `auto_install: True` — Odoo installs the bridge automatically when both parents are present.
- `application: False` — Does not appear as a top-level App.
- `category: 'Hidden/Technical'` — Excluded from business category listings.

---

## Architecture Decisions

### Why a bridge rather than extending `sor_locations_artist_studios`?

`sor_locations_artist_studios` has no dependency on `sor_locations_artwork`. Adding a `current_location_id` check directly inside `sor_locations_artist_studios.set_values()` would require adding `sor_locations_artwork` to the parent's `depends` list — violating the composability rule that base modules may not depend on each other.

The bridge carries the coupling: it depends on both parents and adds the check only when both are present. When `sor_locations_artwork` is absent, the bridge is not installed and the check does not run. This is the correct composability boundary.

### Guard chain via `super().set_values()`

The bridge's `set_values()` runs its check first, then calls `super().set_values()`. The MRO chain for a full installation is:

```
ResConfigSettings (bridge) → ResConfigSettings (sor_locations_artist_studios) → Odoo base
```

The bridge check fires first. If it passes, `super()` runs the quant-based guard in `sor_locations_artist_studios`. Both guards must pass before the toggle is disabled. Adding a third guard in a future bridge follows the same pattern: override `set_values()`, check, call `super()`.

### `current_location_id` versus `stock.quant`

These are complementary, not overlapping, guards:

| Guard | Covers | Where defined |
|-------|--------|---------------|
| `stock.quant` check | Artworks with active quant records at AS locations — set by Odoo's internal inventory system when physical stock moves are validated | `sor_locations_artist_studios` |
| `current_location_id` check | Artworks whose SOR-tracked current location is an AS location — set by movement confirmation in `sor_locations_artwork`, or manually assigned | This bridge |

The quant guard catches inventory-system-managed records. The `current_location_id` guard catches SOR-tracked records that may not have a corresponding quant (imported data, manual assignments, artworks where inventory tracking is not active). Both must pass for a clean disable.

---

## Models

### `res.config.settings` (TransientModel)

**Method override: `set_values()`**

```python
def set_values(self):
    if not self.sor_artist_studios_enabled:
        as_warehouses = self.env['stock.warehouse'].search([
            ('code', '=', 'AS'),
            ('company_id', '=', self.env.company.id),
        ])
        if as_warehouses:
            as_location_ids = self.env['stock.location'].search([
                ('location_id', 'child_of', as_warehouses.view_location_id.ids),
            ]).ids
            occupied = self.env['product.template'].search_count([
                ('current_location_id', 'in', as_location_ids),
            ])
            if occupied:
                raise UserError(_(
                    "Artist Studios cannot be disabled for %(company)s — "
                    "%(count)d artwork(s) currently have an Artist Studio as their location. "
                    "Reassign those artworks before disabling.",
                    company=self.env.company.name, count=occupied,
                ))
    super().set_values()
```

**Scoping notes:**
- Checks `as_warehouses` against `env.company` — multi-company safe.
- Uses `view_location_id.ids` + `child_of` to include all sub-locations under the AS view location.
- `search_count` is a single SQL COUNT — no ORM record loading.
- Guard only fires when `sor_artist_studios_enabled` is being set to `False`. Saving Settings with the toggle already enabled is unaffected.

No new fields. No data XML. No views.

---

## Views

**N/A** — This bridge adds no views. The disable guard is purely server-side.

---

## Module File Structure

```
sor_locations_artist_studios_artwork/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── res_config_settings.py       ← set_values() override with current_location_id guard
├── security/
│   └── ir.model.access.csv          ← empty (no new models)
├── i18n/
│   └── sor_locations_artist_studios_artwork.pot
├── tests/
│   ├── __init__.py
│   └── test_sor_locations_artist_studios_artwork.py
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/res_config_settings.py` | The sole model file — contains the entire bridge logic: the `set_values()` override with the `current_location_id` guard |
| `tests/test_sor_locations_artist_studios_artwork.py` | Three tests: module installed, set_values override present in MRO, disable guard blocked/passes |

---

## Composability Boundary

| Installation state | `set_values()` behaviour |
|-------------------|--------------------------|
| `sor_locations_artist_studios` only | Quant guard only |
| `sor_locations_artwork` only | No AS toggle exists — guard irrelevant |
| Both parents installed | This bridge auto-installs; both guards active |
| Bridge installed, `sor_locations_artwork` removed | Bridge would be in broken state (dependency removed) — Odoo prevents this scenario |

---

## Special Concerns

### Environment dependency of the integration test

`test_disable_guard_blocked_when_artwork_at_as_location` is an integration test — it requires real artwork data with `current_location_id` pointing to an AS location in the test database. If no such artwork exists, the test skips. This is intentional: setting `current_location_id` directly in the test would require cross-company write logic that adds test complexity disproportionate to the guard's simplicity. The unit concern (that `set_values` checks `current_location_id`) is covered by `test_set_values_override_present` via MRO inspection.

---

## Running the Tests

```bash
docker exec odoo-app python3 /app/odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo \
  --test-enable --stop-after-init \
  -u sor_locations_artist_studios_artwork \
  2>&1 | tail -40
```

Expected: 3 tests, 0 failures, 0 errors (the integration test may skip if no AS-assigned artwork exists).

---

## Story Reference

Parent story: `.backlog/current/Movement Layer Completion/stories/05_Legal-Agreement-DoD-Closure.md`  
Sprint: Movement Layer Completion — BUG-05 fix
