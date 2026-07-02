# Knowledge Base: SOR Base

## What is SOR Base?

`sor_base` is the foundational infrastructure module for every SOR deployment. It declares the two horizontal mechanism modules — `sor_asset_paradigm` and `sor_business_model` — as its dependencies, so installing `sor_base` sets up the complete SOR horizontal infrastructure in a single step.

`sor_base` contains no models, views, or logic of its own. It is a **meta-module** — its only purpose is to establish the infrastructure baseline that all SOR vertical modules depend on.

**What it installs when you install `sor_base`:**
- `sor_asset_paradigm` — asset type classification and inventory UI suppression mechanism
- `sor_business_model` — company-level business model field and commerce UI suppression mechanism

**What auto-installs once `sor_artwork` is added on top of `sor_base`:**
- `sor_asset_paradigm_artwork` — bridge: suppresses inventory quant UI for unique artwork objects
- `sor_business_model_non_commercial` — bridge: suppresses commerce UI for non-commercial organisations

**What it does NOT do:**
- Add any fields, views, or logic to existing models
- Create any menus
- Install automatically (it requires explicit installation as the first deployment step)

---

## Prerequisites

No SOR prerequisites. `sor_base` depends on `sor_asset_paradigm` and `sor_business_model`, which in turn depend on the Odoo `product` module. A standard Odoo 19 Community installation with the product module present is sufficient.

---

## Guide 1 — Install SOR Base (first-time deployment)

**When to use:** When setting up a new SOR deployment on a clean Odoo instance, before installing any SOR vertical module.

### Steps

1. Go to **Settings → Apps**.
2. Search for **SOR Base** (note: the module is listed as `Hidden/Technical` — use the search bar, it does not appear in the default category list).
3. Click **Install**.

### Expected outcome

- `sor_base`, `sor_asset_paradigm`, and `sor_business_model` are all installed.
- No errors appear in the upgrade log.
- No new menus or models appear — `sor_base` is a technical foundation module with no user-visible output.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R1 | `sor_base` state = `installed` after installation | Yes |
| R2 | `sor_asset_paradigm` installed automatically | Yes |
| R3 | `sor_business_model` installed automatically | Yes |
| R4 | No new top-level menu items visible after sor_base install alone | Yes — Hidden/Technical; no menus |

---

## Guide 2 — Install a Vertical Module (e.g. sor_artwork)

**When to use:** After `sor_base` is in place, install a vertical domain module to add a specific asset type.

### Steps

1. Go to **Settings → Apps**.
2. Search for **SOR Artwork Management** (or the vertical module you need).
3. Click **Install**.

### Expected outcome

- `sor_artwork` installs along with its bridge modules.
- `sor_asset_paradigm_artwork` and `sor_business_model_non_commercial` appear in the installed module list.
- The **Artworks** top-level menu appears in the navigation bar.
- No manual installation of bridge modules is required.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R5 | `sor_asset_paradigm_artwork` installed automatically after sor_artwork install | Yes |
| R6 | `sor_business_model_non_commercial` installed automatically after sor_artwork install | Yes |
| R7 | Artworks top-level menu visible in navigation | Yes |
| R8 | sor_base can be confirmed as a dependency of sor_artwork in the module dependency list | Yes |

---

## Interoperability

| Module | Role | Relationship to sor_base |
|--------|------|--------------------------|
| `sor_asset_paradigm` | Horizontal mechanism | Declared dependency — installed by sor_base |
| `sor_business_model` | Horizontal mechanism | Declared dependency — installed by sor_base |
| `sor_artwork` | Vertical domain module | Declares sor_base as prerequisite |
| All future SOR verticals | Vertical domain modules | Must declare sor_base as prerequisite |
| `sor_contact_roles` | Contact role hierarchy | Independent of sor_base — no relationship |
| `sor_locations` | Viewing locations | Independent of sor_base — no relationship |

> **Convention for future vertical modules:** All future SOR vertical modules (`sor_antiques`, `sor_jewellery`, etc.) must declare `sor_base` in their `depends` list rather than depending directly on `sor_asset_paradigm` or `sor_business_model`. This ensures no vertical can be installed on an incomplete infrastructure and centralises the horizontal dependency declaration in one place.
