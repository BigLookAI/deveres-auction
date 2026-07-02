# sor_business_model_non_commercial — Knowledge Base

## Overview

`sor_business_model_non_commercial` is a bridge module that suppresses commerce fields on product forms when the active company's business model is set to **Non-Commercial**.

It auto-installs automatically when `sor_business_model` is installed — no manual install step is required.

**Intended for:** Permanent collections, university art collections, municipal museums — any organisation with no commercial sales activity.

---

## What is suppressed

When the company's business model is **Non-Commercial**, the following elements are hidden on **all** product forms regardless of product type:

| Element | Field key | Location on product form |
|---|---|---|
| Can be Sold toggle | `can_be_sold` | Header options area |
| Sales Price (list_price) | `sale_price_field` | General Information tab |
| Sales tab | `sales_tab` | Tab bar |

> **Cost (standard_price) is not suppressed.** Cost remains visible in non-commercial contexts — it is relevant for insurance valuations and acquisition cost records.

---

## Applies to all product types

Suppression is **company-wide**. All products — artworks, storable products, services — are affected equally. The suppression is not artwork-specific.

---

## Configuration

Set the company's business model in:

**General Settings → Business Model section (below Companies) → Non-Commercial**

The default value on install is **Non-Commercial**, so suppression is active immediately after installing the module.

---

## Toggling rules

Individual suppression rules can be enabled or disabled without code changes:

1. Enable developer mode (Settings → Activate Developer Mode)
2. Navigate to **Settings → Technical → SOR → Business Model Rules**
3. The list shows all three rules for the non-commercial model
4. Click a rule row to open the form view, then uncheck **Suppressed** to re-enable that element
5. Perform a hard browser refresh (Cmd+Shift+R / Ctrl+Shift+R) to observe the change on open product forms

> **Hard refresh is required.** Suppression booleans are `store=False` computed fields re-evaluated on page load. An already-open form does not update without a refresh.

---

## Regression checks

### R1 — Can be Sold not visible (non_commercial)
Navigate to any product form. With business model set to Non-Commercial: the Can be Sold toggle is not visible in the header area.

### R2 — Sales Price not visible (non_commercial)
Navigate to any product form → General Information tab. With business model set to Non-Commercial: the Sales Price field and its label are not visible.

### R3 — Sales tab not visible (non_commercial)
Navigate to any product form. With business model set to Non-Commercial: the Sales tab is not visible in the tab bar.

### R4 — Cost field remains visible (non_commercial)
Navigate to any product form → General Information tab. With business model set to Non-Commercial: the Cost field is still visible.

### R5 — All three elements visible when model is not non_commercial
Change the company's business model to any value other than Non-Commercial (e.g. via the Odoo shell or a future bridge install). Hard refresh. Can be Sold, Sales Price, and Sales tab are all visible.

### R6 — Suppression applies to a non-artwork product
Create a new storable product (not an artwork). With business model set to Non-Commercial: Can be Sold, Sales Price, and Sales tab are suppressed on that product too.

### R7 — Business Model Rules list shows all three rules
Enable developer mode → Settings → Technical → SOR → Business Model Rules. Three rules are visible: `can_be_sold`, `sale_price_field`, `sales_tab`, all with Suppressed checked.

### R8 — Unchecking a rule causes the element to reappear
In the Business Model Rules list, uncheck Suppressed on the `can_be_sold` rule. Hard refresh. The Can be Sold toggle reappears on product forms.

### R9 — Re-checking a rule suppresses the element again
Re-check Suppressed on the `can_be_sold` rule. Hard refresh. The Can be Sold toggle is suppressed again.

### R10 — Module installs cleanly
On a fresh database with `sor_business_model` installed, `sor_business_model_non_commercial` installs automatically without errors. Three rule records exist in `sor.business.model.rule`.

---

## Interoperability with sor_asset_paradigm_artwork

Both bridges can be active simultaneously with no conflict.

| Layer | Module | Scope | Effect |
|---|---|---|---|
| Asset Paradigm | `sor_asset_paradigm_artwork` | Per product (`asset_paradigm = unique_object`) | Hides Forecasted Qty, Reorder Rules, quant columns |
| Business Model | `sor_business_model_non_commercial` | Per company (`business_model = non_commercial`) | Hides Can be Sold, Sales Price, Sales tab |

An artwork in a non-commercial collection has both layers applied simultaneously — quant UI and commerce UI are both suppressed.
