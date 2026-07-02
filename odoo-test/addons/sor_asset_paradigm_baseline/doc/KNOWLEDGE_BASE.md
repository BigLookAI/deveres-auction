# Knowledge Base — sor_asset_paradigm_baseline

## Overview

`sor_asset_paradigm_baseline` is a developer-support module that installs automatically alongside `sor_asset_paradigm`. Its sole purpose is to provide a **Baseline Product** — a persistent reference record with the `standard` paradigm and zero suppression rules — so developers can compare the full OOTB Odoo inventory UI against any paradigm-suppressed product.

**This module does NOT:**
- Add user-facing features or configuration
- Suppress any UI elements
- Define suppression rules for any paradigm
- Require or interact with vertical modules (`sor_artwork`, etc.)

**Depends on:** `sor_asset_paradigm` only. Auto-installs whenever `sor_asset_paradigm` is installed.

---

## Key Fields and Models

No new models are introduced. The module makes one addition to an existing model:

| Model | Field | Type | Purpose |
|-------|-------|------|---------|
| `product.template` | `asset_paradigm` | `Selection` (`selection_add`) | Registers the `standard` paradigm value. Without this module, `standard` is not a valid selection option. |

The `standard` paradigm signals "no suppression" — all OOTB Odoo inventory UI elements remain visible for products with this value.

---

## The Baseline Product

The Baseline Product is created once by `post_init_hook` at module install time via ORM. An `ir.model.data` record is created alongside it so the product has a stable external ID and the hook remains idempotent on subsequent installs.

| Property | Value |
|----------|-------|
| Name | Baseline Product (SOR Paradigm Reference) |
| `asset_paradigm` | `standard` |
| `active` | `False` (archived — not visible in normal product lists) |
| `type` | `consu` |
| `is_storable` | `True` |
| `tracking` | `none` |
| External ID | `sor_asset_paradigm_baseline.baseline_product` |

`product_type` is not set on the Baseline Product — it is left empty (the field is provided by `sor_artwork` which may not be installed). The ORM create uses `with_context(default_product_type=False)` to prevent `sor_artwork`'s `default_get` from stamping `'artwork'` when both modules are installed together.

The product is **archived** by default so it does not appear in production product lists. It is only surfaced through the developer menu (see below) or by searching with `active_test=False`.

---

## Developer Menu

**Location:** Settings → Technical → SOR → Baseline Product *(developer mode only)*

**How to access:**

1. Activate developer mode (`?debug=1` in the URL, or via Settings → General Settings → Developer Tools).
2. Go to **Settings → Technical → SOR → Baseline Product**.
3. The list opens showing the single Baseline Product record (the action uses `context={'active_test': False}` to show the archived record).

**What it shows:**

The Baseline Product form displays the full standard Odoo product form with the `standard` paradigm assigned. Since `standard` has no suppression rules, all inventory UI elements — stat buttons (Forecasted, On Hand, Reorder Points), quantity columns, Operations tab, and the Replenish action — are visible. This is the reference state that artwork and other paradigm-suppressed products are compared against.

---

## Building on This Module

This module is not a direct dependency for other SOR modules. Bridge modules that register new paradigm values should depend on `sor_asset_paradigm`, not on `sor_asset_paradigm_baseline`.

If you are building a new paradigm module and want to ensure the developer experience is complete:

1. Declare `depends: ['sor_asset_paradigm']` in your manifest.
2. Register your paradigm value via `selection_add` on `product.template.asset_paradigm`.
3. Install your rule data records in `data/` XML (with `noupdate="1"`).
4. Use `is_element_suppressed(element_key)` from `sor_asset_paradigm` in your computed suppression booleans.

The Baseline Product remains unchanged — it always carries `standard` paradigm and reflects zero suppression. It does not need to be referenced or modified by new bridge modules.

---

## Regression Checks

| # | Check | How to verify | Expected |
|---|-------|---------------|----------|
| R1 | Baseline Product exists after install | Settings → Technical → SOR → Baseline Product (developer mode) | One record listed |
| R2 | Baseline Product has `standard` paradigm | Open the record; check Asset Paradigm field | Shows "Standard" |
| R3 | Baseline Product is archived (not visible in normal lists) | Inventory → Products → Products (no debug context) | Record not in list |
| R4 | `standard` paradigm option appears in Asset Paradigm field selector | Any product form → General Information → Asset Paradigm dropdown | "Standard" option present |
| R5 | Baseline Product is not suppressed — all stat buttons visible | Open Baseline Product via developer menu; observe top-right stat buttons | Forecasted, On Hand, Reorder Points buttons all visible |
| R6 | Baseline Product survives a module upgrade unchanged | Run `docker exec odoo-app python3 odoo-bin … -u sor_asset_paradigm_baseline --stop-after-init` | Record still exists with `standard` paradigm; no errors in log |
| R7 | Hook is idempotent — re-running does not create a duplicate | Inspect `ir.model.data` for `sor_asset_paradigm_baseline.baseline_product` | Exactly one row |

---

## Interoperability

| Module | Installed alongside | Effect |
|--------|--------------------|----|
| `sor_asset_paradigm` | Always (this module auto-installs with it) | Provides the `standard` paradigm value and the Baseline Product developer reference |
| `sor_artwork` | Optional | No interaction. The Baseline Product ORM create uses `with_context(default_product_type=False)` to prevent `sor_artwork`'s `default_get` from stamping `product_type='artwork'`, which would otherwise trigger the creator constraint and fail the fresh install |
| `sor_asset_paradigm_artwork` | Optional | No interaction. The artwork bridge registers the `unique_object` paradigm and its rules; `standard` remains unaffected |
| Any future paradigm bridge | Optional | No interaction required. New bridges register their own paradigm values independently |
