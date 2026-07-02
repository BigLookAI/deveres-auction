# Knowledge Base: Asset Paradigm Foundation

## What is Asset Paradigm?

Asset Paradigm is a classification system that governs which Odoo inventory UI elements are shown or hidden for a given product. Each product can be assigned a **paradigm** — a value that describes what kind of asset it is — and a set of **suppression rules** translates that paradigm into specific UI changes.

The mechanism is intentionally generic. It does not know about artworks or any other domain directly. That knowledge lives in bridge modules (such as `sor_asset_paradigm_artwork`) that add new paradigm values and register the suppression rules they require.

**Out of the box, this module provides:**
- The `asset_paradigm` field on every product
- The `sor.asset.paradigm.rule` model and admin UI
- The `is_element_suppressed()` helper that bridges call to compute their suppression booleans
- The `standard` paradigm value (no suppression — full OOTB Odoo inventory UI)
- A developer debug parameter to temporarily disable all suppression

---

## Prerequisites

- **SOR Artwork** (`sor_artwork`) is not required. The Asset Paradigm module works with any product type.
- `sor_asset_paradigm` installs standalone. Bridge modules (`sor_asset_paradigm_artwork`, etc.) auto-install on top of it when their dependencies are met.

---

## Guide 1 — View the Asset Paradigm Value on a Product

**When to use:** To confirm which paradigm is assigned to a product and understand why certain inventory UI elements are or are not visible.

### Steps

1. Open any product (e.g. via the **Artworks** top-level menu).
2. Go to the **General Information** tab.
3. Look for the **Asset Paradigm** field below **Category**. It is displayed as a coloured badge when a value is set, and blank when no paradigm is assigned.

### Expected outcome

- Artwork products show **Unique Object** (set automatically by the artwork bridge).
- Standard products show a blank field (no paradigm assigned — full inventory UI visible).

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R1 | Asset Paradigm field visible in General Information tab, below Category | Yes |
| R2 | Artwork product shows "Unique Object" badge | Yes |
| R3 | Non-artwork product shows blank field | Yes |
| R4 | Field is editable by admin users | Yes |
| R5 | Field renders as badge widget (not plain text) | Yes |

---

## Guide 2 — Manage Paradigm Suppression Rules (Developer Mode)

**When to use:** To inspect which UI elements are suppressed for a paradigm, or to temporarily disable a suppression rule for debugging.

This UI is only visible in **developer mode** (`?debug=1` in the URL, or activated via Settings → General Settings → Developer Tools).

### Steps

1. Activate developer mode.
2. Go to **Settings → Technical → SOR → Paradigm Rules**.
3. The list shows all registered suppression rules. Each row displays the **Paradigm**, **Feature** (a human-readable label for the element), and **Instances suppressed** (the number of UI manifestations currently suppressed for that rule).
4. Click a rule to open its detail view, which enumerates all **UI Manifestations** — the specific form, list, and kanban elements that the rule suppresses.
5. Each rule has a **Suppressed** checkbox in the detail view. When checked, the element is hidden for products of that paradigm. When unchecked, the element is re-enabled.

### Expected outcome

- All rules for the `unique_object` paradigm (installed by `sor_asset_paradigm_artwork`) are listed.
- Unchecking **Suppressed** on a rule and saving causes the element to reappear on artwork products after a browser hard refresh (Cmd+Shift+R / Ctrl+Shift+R).
- Re-checking **Suppressed** and saving restores the suppression.
- Rules with Suppressed unchecked remain visible in the list (they are not archived).

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R6 | Paradigm Rules list accessible under Settings → Technical → SOR (developer mode only) | Yes |
| R7 | List shows all 13 rules for `unique_object` paradigm | Yes |
| R8 | Rules with Suppressed unchecked remain visible in the list | Yes |
| R9 | Toggling Suppressed off and saving re-enables the element on affected products (after hard refresh) | Yes |
| R10 | Toggling Suppressed back on and saving re-suppresses the element (after hard refresh) | Yes |
| R11 | Paradigm Rules menu is absent when developer mode is off | Yes |

---

## Guide 3 — Use the Debug Parameter to Disable All Suppression

**When to use:** When you want to temporarily see the full OOTB Odoo inventory UI for all products — for example, to compare against a baseline product or to verify that a suppression issue is caused by the paradigm system and not something else.

### Steps

1. Activate developer mode.
2. Go to **Settings → Technical → Parameters → System Parameters**.
3. Search for `sor_asset_paradigm.debug_show_quant_ui`.
4. Set the value to `True` and save.
5. Hard refresh any open product form (Cmd+Shift+R / Ctrl+Shift+R).
6. All suppressed elements will reappear for all products, regardless of their paradigm.
7. Reset the value to `False` when debugging is complete.

### Expected outcome

- All paradigm-suppressed elements become visible site-wide while the parameter is `True`.
- Setting the parameter back to `False` restores all suppression.
- Module upgrades do not reset a manually changed value (`noupdate="1"`).

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R12 | `sor_asset_paradigm.debug_show_quant_ui` parameter exists after module install | Yes |
| R13 | Default value is `False` | Yes |
| R14 | Setting value to `True` disables all suppression site-wide (after hard refresh) | Yes |
| R15 | Setting value back to `False` restores suppression (after hard refresh) | Yes |
| R16 | Module upgrade does not reset a manually changed value | Yes |

---

## Scope — What is NOT Included

- **Artwork-specific suppression rules** — these are registered by `sor_asset_paradigm_artwork`, not this module.
- **Automatic paradigm assignment** — assigning `asset_paradigm='unique_object'` to artwork products on create/write is done by `sor_asset_paradigm_artwork`, not here.
- **Change log** — the `sor.asset.paradigm.log` model and paradigm history smart button are a planned future task.

---

## Interoperability

### With Artwork Quant Suppression (`sor_asset_paradigm_artwork`)

The primary consumer of this module. Installs automatically when both `sor_asset_paradigm` and `sor_artwork` are present. Registers the `unique_object` paradigm and 13 suppression rules that hide inventory UI elements not relevant to art objects.

### Adding a new bridge

Any module can register its own paradigm value and suppression rules by:
1. Adding `selection_add` on `product.template.asset_paradigm`.
2. Creating `sor.asset.paradigm.rule` records in a `data/` XML file.
3. Adding computed suppression boolean fields to `product.template` (and `product.product` if variant forms are used) that call `is_element_suppressed()`.

---

## Quick Reference: Regression Test Checklist

| Ref | Area | Check | Expected |
|-----|------|-------|----------|
| R1 | Field | Asset Paradigm field visible in General Information tab | Yes |
| R2 | Field | Artwork product shows "Unique Object" badge | Yes |
| R3 | Field | Non-artwork product shows blank field | Yes |
| R4 | Field | Field is editable by admin users | Yes |
| R5 | Field | Field renders as badge widget | Yes |
| R6 | Rules | Paradigm Rules list accessible in developer mode | Yes |
| R7 | Rules | 13 rules listed for `unique_object` paradigm | Yes |
| R8 | Rules | Unsuppressed rules remain visible in list | Yes |
| R9 | Rules | Toggle off re-enables element (after hard refresh) | Yes |
| R10 | Rules | Toggle on re-suppresses element (after hard refresh) | Yes |
| R11 | Rules | Menu absent when developer mode is off | Yes |
| R12 | Debug | Debug parameter exists after install | Yes |
| R13 | Debug | Default value is `False` | Yes |
| R14 | Debug | `True` disables all suppression site-wide | Yes |
| R15 | Debug | `False` restores suppression | Yes |
| R16 | Debug | Upgrade does not reset manually changed value | Yes |
