# Knowledge Base: Artwork Quant Suppression

## What is Artwork Quant Suppression?

When an artwork product is viewed in Odoo's UI, several standard stock and product fields are irrelevant — a painting is not replenished, reordered, or counted in the way a consumable would be. Artwork Quant Suppression automatically hides those elements so that the product form, list, and kanban views present only information that is meaningful for art objects.

The feature activates automatically when both `sor_asset_paradigm` and `sor_artwork` are installed. No settings toggle is required.

**Elements suppressed for artwork products:**

| Element | Location | Why suppressed |
|---------|----------|----------------|
| Forecasted Qty stat button | Product form header | Qty is always 1; the forecast graph adds no information |
| Reorder Rules stat button | Product form header | Unique objects are never automatically reordered |
| Moves In/Out stat button | Product form header | "Stock moves" terminology is misleading for art objects |
| Putaway Rules stat button | Product form header | Putaway rules are irrelevant for individually tracked objects |
| Storage Capacities stat button | Product form header | Capacity rules do not apply to unique objects |
| Qty Available inline field | Product form | Qty is always 1; the field is noise |
| Odoo Product Type field | Product form | Always "Goods" for artworks; the choice adds no information |
| SOR Product Type field | Product form | Always "Artwork"; hidden as it is a fixed, non-editable fact |
| Track Inventory checkbox | Product form | Artworks are always tracked; the checkbox adds no information |
| Inventory tab | Product form | Entire tab hidden — logistics, weight, lead time, and locations are managed by SOR operations modules when in scope |
| Stock Quantity columns | Artworks list view | Qty Available and Forecasted Qty columns fully suppressed |
| On Hand qty | Kanban card | Hidden from artwork kanban cards |
| Replenish action | Action menu | Silently skipped; selecting it for an artwork produces no action |

---

## Prerequisites

- **SOR Asset Paradigm** (`sor_asset_paradigm`) must be installed.
- **SOR Artwork** (`sor_artwork`) must be installed.

When both are present, `sor_asset_paradigm_artwork` auto-installs. No manual installation is required.

> **Composability:** Without `sor_artwork`, artwork products do not exist and there is nothing to suppress. Without `sor_asset_paradigm`, the suppression mechanism does not exist. Both are required.

---

## Guide 1 — Verify Suppression on an Artwork Product

**When to use:** To confirm that the artwork UI suppression is working correctly on a given artwork product.

### Steps

1. Go to **Artworks** (top-level menu) and open any artwork product.
2. Confirm the following stat buttons are **absent** from the form header:
   - Forecasted Qty, Reorder Rules, Moves In/Out, Putaway Rules, Storage Capacities.
3. Go to the **General Information** tab and confirm:
   - **Asset Paradigm** badge shows **Unique Object**.
   - The **Odoo Product Type** field (Goods/Service/Combo), **SOR Type** field, and **Track Inventory** checkbox are not visible.
4. Confirm the **Inventory** tab is absent from the tab bar entirely.
5. From the **Artworks** list view:
   - The **Qty Available** and **Forecasted Qty** columns are fully absent (no column headers, no cell values).
6. From the **Kanban view**:
   - Artwork cards do not show an "On hand: X" line.

### Expected outcome

- All listed elements are absent from artwork product views.
- A product with the `standard` paradigm (e.g. the Baseline Product) opened in developer mode shows all suppressed elements as normal.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R1 | Forecasted Qty stat button absent on artwork form | Yes |
| R2 | Reorder Rules stat button absent on artwork form | Yes |
| R3 | Moves In/Out stat button absent on artwork form | Yes |
| R4 | Putaway Rules stat button absent on artwork form | Yes |
| R5 | Storage Capacities stat button absent on artwork form | Yes |
| R6 | Qty Available inline field absent from artwork form | Yes |
| R7 | Odoo Product Type field absent from artwork form | Yes |
| R8 | SOR Product Type field absent from artwork form | Yes |
| R9 | Track Inventory checkbox absent from artwork form | Yes |
| R10 | Inventory tab absent from artwork form tab bar | Yes |
| R11 | Qty Available column fully absent in Artworks list view (no header, no cells) | Yes |
| R12 | Forecasted Qty column fully absent in Artworks list view (no header, no cells) | Yes |
| R13 | On Hand line absent from artwork kanban card | Yes |
| R14 | Same elements visible on a standard-paradigm product (e.g. Baseline Product in developer mode) | Yes |

---

## Guide 2 — Verify Suppression on a Variant Form

**When to use:** Artwork products may have variants (e.g. edition prints). The suppression also applies to the individual variant form (`product.product`).

### Steps

1. Open an artwork product that has at least one variant.
2. Go to the **Variants** tab and click through to an individual variant form.
3. Confirm the stat buttons (Forecasted Qty, Reorder Rules, Moves In/Out, Putaway Rules, Storage Capacities) are absent from the variant form header.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R15 | Stat buttons absent on artwork variant form | Yes |
| R16 | Stat buttons visible on a non-artwork variant form | Yes |

---

## Guide 3 — Verify New Artwork Products Get the Paradigm Automatically

**When to use:** To confirm that newly created artwork products are automatically assigned the `unique_object` paradigm and have suppression applied immediately.

### Steps

1. Go to **Artworks** and create a new artwork (click **New**).
2. Save the product.
3. Go to the **General Information** tab.
4. Confirm **Asset Paradigm** shows **Unique Object**.
5. Confirm the suppressed stat buttons and fields are absent.

### Expected outcome

- `asset_paradigm` is set to `unique_object` automatically — no manual step required.
- Suppression is applied immediately on the newly created record.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R17 | New artwork product has Asset Paradigm = Unique Object without manual input | Yes |
| R18 | Suppression applied immediately on new artwork | Yes |

---

## Guide 4 — Verify Pre-Existing Artworks Have the Paradigm

**When to use:** After first installing `sor_asset_paradigm_artwork` on a database that already contains artwork products, to confirm the migration backfilled the paradigm correctly.

### Steps

1. Go to **Artworks** and open an artwork product that existed before the module was installed.
2. Go to the **General Information** tab.
3. Confirm **Asset Paradigm** shows **Unique Object**.
4. Confirm suppression is applied (no stat buttons, no Inventory tab).

### Notes

- The module's migration script (`migrations/19.0.1.0.2/post-migrate.py`) sets both `asset_paradigm='unique_object'` and `is_storable=True` on all pre-existing artworks. The `is_storable=True` setting is required for stock stat buttons to be available to suppress; artworks created before this module may have had `is_storable=False` (the default), which would permanently hide the buttons regardless of the paradigm rule.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R19 | Pre-existing artwork shows Asset Paradigm = Unique Object | Yes |
| R20 | Pre-existing artwork has suppression applied | Yes |
| R21 | Forecast stat button visible on pre-existing artwork when suppression rule is toggled off | Yes |

---

## Guide 5 — Temporarily Disable Suppression for Debugging

**When to use:** When you want to confirm that a missing UI element is hidden by the paradigm suppression system (rather than by some other cause), by toggling the relevant rule off.

### Steps

1. Activate developer mode (`?debug=1` in the URL).
2. Go to **Settings → Technical → SOR → Paradigm Rules**.
3. Find the rule for the element you want to temporarily re-enable (e.g. **Forecasted Stock Display**).
4. Open the rule and uncheck **Suppressed**. Save.
5. Hard refresh the artwork product form (**Cmd+Shift+R** / **Ctrl+Shift+R**).
6. Confirm the element is now visible on artwork products.
7. Return to Paradigm Rules, re-check **Suppressed**, and save to restore the default state.

### Notes

- All 13 rules remain visible in the Paradigm Rules list regardless of their Suppressed state.
- A hard browser refresh is required after any rule toggle — the suppression booleans are computed server-side and cached by the browser.
- Alternatively, set `sor_asset_paradigm.debug_show_quant_ui = True` in System Parameters (**Settings → Technical → Parameters → System Parameters**) to disable all suppression globally without changing any individual rule.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R22 | Paradigm Rules list accessible under Settings → Technical → SOR (developer mode) | Yes |
| R23 | 13 rules listed for `unique_object` paradigm | Yes |
| R24 | Unchecking Suppressed on a rule re-enables that element (after hard refresh) | Yes |
| R25 | Rule remains visible in the list when Suppressed is unchecked | Yes |
| R26 | Re-checking Suppressed restores suppression (after hard refresh) | Yes |

---

## Guide 6 — Replenish Action Behaviour

**When to use:** To verify that the Replenish action is correctly suppressed for artwork products.

### Steps

1. Open an artwork product.
2. Click the **Action** menu (⚙ gear icon) in the form header.
3. Observe that the **Replenish** option may still appear in the menu (visual suppression is a known limitation — see Scope below).
4. If Replenish is triggered on an artwork product, it silently skips the product and produces no replenishment wizard.

### Notes

The Replenish action is suppressed at the server-action level: the code that would open the replenishment wizard is skipped for `unique_object` paradigm products. The menu entry itself may still be visible in the Action menu — full visual removal is a deferred task.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R27 | Triggering Replenish on an artwork product opens no wizard | Yes — silently skipped |
| R28 | Triggering Replenish on a standard (non-artwork) storable product opens the wizard | Yes |

---

## Scope — What is NOT Included

The following are known limitations or deferred items:

- **Replenish menu entry visual suppression** — The Replenish option in the Action menu may still appear for artworks. It is functionally suppressed (no wizard opens) but visual removal is deferred. See Sprint Retrospective v2.md.
- **Change log** — A paradigm change history log (`sor.asset.paradigm.log`) with smart button is a planned future task.

---

## Interoperability

### With Asset Paradigm Foundation (`sor_asset_paradigm`)

This module depends on and extends `sor_asset_paradigm`. The suppression mechanism (rule registry, `is_element_suppressed()`, debug parameter) lives in `sor_asset_paradigm`. This bridge contributes the `unique_object` paradigm value and its 13 rules.

### With other paradigm bridges

If a future paradigm bridge (e.g. for a different asset type) is installed alongside this one, each bridge's rules apply only to its own paradigm value. There is no interference between paradigms.

---

## Quick Reference: Regression Test Checklist

| Ref | Area | Check | Expected |
|-----|------|-------|----------|
| R1 | Form | Forecasted Qty stat button absent | Yes |
| R2 | Form | Reorder Rules stat button absent | Yes |
| R3 | Form | Moves In/Out stat button absent | Yes |
| R4 | Form | Putaway Rules stat button absent | Yes |
| R5 | Form | Storage Capacities stat button absent | Yes |
| R6 | Form | Qty Available inline field absent | Yes |
| R7 | Form | Odoo Product Type field absent | Yes |
| R8 | Form | SOR Product Type field absent | Yes |
| R9 | Form | Track Inventory checkbox absent | Yes |
| R10 | Form | Inventory tab absent from tab bar | Yes |
| R11 | List | Qty Available column fully absent (no header, no cells) | Yes |
| R12 | List | Forecasted Qty column fully absent (no header, no cells) | Yes |
| R13 | Kanban | On Hand line absent from artwork card | Yes |
| R14 | Baseline | All suppressed elements visible on standard-paradigm product | Yes |
| R15 | Variant | Stat buttons absent on artwork variant form | Yes |
| R16 | Variant | Stat buttons visible on non-artwork variant form | Yes |
| R17 | New | New artwork auto-assigned Unique Object paradigm | Yes |
| R18 | New | Suppression applied immediately on new artwork | Yes |
| R19 | Migration | Pre-existing artwork shows Unique Object paradigm | Yes |
| R20 | Migration | Pre-existing artwork has suppression applied | Yes |
| R21 | Migration | Forecast button visible on pre-existing artwork when rule toggled off | Yes |
| R22 | Debug | Paradigm Rules list accessible (developer mode) | Yes |
| R23 | Debug | 13 rules listed for `unique_object` | Yes |
| R24 | Debug | Toggle off re-enables element (after hard refresh) | Yes |
| R25 | Debug | Unsuppressed rule remains visible in list | Yes |
| R26 | Debug | Toggle on re-suppresses element (after hard refresh) | Yes |
| R27 | Replenish | Replenish on artwork produces no wizard | Yes |
| R28 | Replenish | Replenish on standard product opens wizard | Yes |
