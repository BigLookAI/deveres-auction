# SOR Locations — Artist Studios × Artwork: Knowledge Base

## Overview

`sor_locations_artist_studios_artwork` is a bridge module that activates automatically when both **SOR Locations — Artist Studios** (`sor_locations_artist_studios`) and **SOR Locations — Artwork** (`sor_locations_artwork`) are installed. It adds a second disable guard to the Artist Studios toggle in Settings.

**What it does:**

`sor_locations_artwork` adds `current_location_id` to artwork products — a field that records the artwork's last known location, set when a movement is confirmed or assigned manually. `sor_locations_artist_studios` already blocks disabling the Artist Studios toggle when a `stock.quant` record exists at an AS location. That guard covers physical inventory records created by Odoo's warehouse moves.

This bridge closes a gap: `current_location_id` can be set on an artwork *without* a corresponding quant record — for example, when artwork data is imported with an existing location assignment, or when a location is manually set on the product form. In those cases the quant-based guard in `sor_locations_artist_studios` would pass, but disabling Artist Studios would silently orphan artworks whose tracked location points to a now-inactive AS location.

This bridge's `set_values()` override adds a check: before allowing the Artist Studios toggle to be disabled, verify that no artwork has `current_location_id` pointing to an AS location for the current company. If any do, a `UserError` is raised with a count and the company name.

**What this module does NOT do:**

- It does not add any new fields to any model.
- It does not change how `current_location_id` is set — that is handled by `sor_locations_artwork` during movement confirmation.
- It does not add any settings toggles or menu items.
- It does not provide UI for viewing or clearing current location assignments — that is in `sor_locations_artwork`.

**Depends on:** `sor_locations_artist_studios` and `sor_locations_artwork`.

---

## Key Fields and Models

This bridge adds no new fields. It extends a single transient model method.

### `res.config.settings` (extended)

| Extension | Type | Notes |
|-----------|------|-------|
| `set_values()` override | Method | Calls the parent guard check (via `super().set_values()`) after its own check. Both guards are additive: the `stock.quant` guard in `sor_locations_artist_studios` and the `current_location_id` guard in this bridge must both pass before the toggle is disabled. |

---

## Methods

### `res.config.settings.set_values()`

Override that adds the `current_location_id` disable guard before calling `super()`. Full execution path when staff click **Save** in Settings with the Artist Studios toggle turned off:

1. Check if `sor_artist_studios_enabled` is `False` in the new values.
2. Find the `AS` warehouse for `env.company`.
3. Find all `stock.location` records that are children of the AS warehouse's `view_location_id`.
4. Count `product.template` records whose `current_location_id` is in that set.
5. If the count is non-zero, raise `UserError` with the company name and artwork count.
6. Call `super().set_values()` — which in turn calls the `sor_locations_artist_studios` guard checking `stock.quant`.

**Error message:**
```
"Artist Studios cannot be disabled for {company} — {count} artwork(s) currently have an Artist Studio
as their location. Reassign those artworks before disabling."
```

---

## Configuration

No configuration is required. This bridge auto-installs when both parent modules are installed. No Settings toggle exists for the bridge itself — it is always active when installed.

---

## Developer Menu

No developer menu entries. This bridge has no configurable rules or runtime-togglable settings.

---

## Building on this Module

If you are building a module that adds a third disable guard for the Artist Studios toggle (for example, checking a future consignment or agreement model for AS-linked records):

1. Declare `sor_locations_artist_studios` (or this bridge if your module also requires `sor_locations_artwork`) as a dependency.
2. Add your own `set_values()` override that:
   - Performs its check first
   - Calls `super().set_values()` to chain all guards
3. Never call `sor_locations_artist_studios`'s guard directly — rely on the `super()` chain.

The pattern ensures all guards fire in dependency order without any module knowing about the others.

---

## Regression Checks

**R1 — Bridge installs when both parents are installed**
1. Navigate to Settings → Apps.
2. Verify `sor_locations_artist_studios_artwork` shows as installed.
3. In developer mode, verify both `sor_locations_artist_studios` and `sor_locations_artwork` are also installed.

**R2 — Disable guard blocked when artwork has current_location_id at AS location**
1. Confirm at least one artwork product has its Current Location set to a Studio (an internal location under the AS warehouse).
2. Navigate to Settings → Inventory → Artist Studios and uncheck the toggle.
3. Click Save.
4. Verify a `UserError` is raised naming the company and the artwork count.
5. Verify the toggle is still enabled.

**R3 — Disable guard passes when no artwork is at an AS location**
1. Confirm no artwork product has its Current Location set to a Studio.
2. Also confirm no `stock.quant` records exist at AS locations.
3. Navigate to Settings → Inventory → Artist Studios and uncheck the toggle.
4. Click Save.
5. Verify the setting saves without error.

> **Note:** R2 and R3 may be environment-dependent. In a clean test database with no AS-assigned artwork data, R2 cannot be directly demonstrated. The automated test `test_disable_guard_blocked_when_artwork_at_as_location` skips cleanly in that case.

---

## Interoperability

| Module combination | Effect on AS disable guard |
|-------------------|---------------------------|
| `sor_locations_artist_studios` only | Quant-based guard only: disabling AS blocked when a `stock.quant` records quantity > 0 at an AS location |
| `sor_locations_artwork` only | No disable guard for AS (AS toggle not present when `sor_locations_artist_studios` is absent) |
| `sor_locations_artist_studios` + `sor_locations_artwork` | This bridge activates: both guards run; `current_location_id` guard fires first in the `set_values()` chain |
| Without `sor_locations_artwork` | `current_location_id` does not exist on `product.template`; this bridge should not be installed |
