# Knowledge Base: SOR Technical Menu

## Overview

`sor_technical_menu` is a pure infrastructure module. It owns a single menu item — `Settings → Technical → SOR` — that acts as the root entry point for all SOR developer menus across the product.

**What this module does:**
- Registers `menu_sor_technical_root`, the `Settings → Technical → SOR` menu root, as a stable XML record that other SOR modules can safely depend on.

**What this module does NOT do:**
- It adds no models, fields, or Python logic.
- It does not own any submenu items. Each dependent module registers its own submenus under this root.
- It does not configure or alter any Odoo settings.

**Dependencies:** `base` only.

**Modules that depend on this module:**

| Module | Submenu added |
|--------|--------------|
| `sor_asset_paradigm` | Settings → Technical → SOR → Paradigm Rules |
| `sor_business_model` | Settings → Technical → SOR → Business Model Rules |
| `sor_events` | Settings → Technical → SOR → Events |
| `sor_legal_agreement` | Settings → Technical → SOR → Agreements |

Before this module existed, `sor_asset_paradigm` owned the SOR root menu. Any module wishing to add an item under it had an undeclared dependency on `sor_asset_paradigm`, adding unnecessary logic overhead. `sor_technical_menu` resolves this by giving the root menu a dedicated, dependency-light home.

---

## Key Features

### SOR Technical root menu

`menu_sor_technical_root` is the canonical anchor point for all SOR developer navigation. It appears at `Settings → Technical → SOR` and is visible only in developer mode. Nothing appears under it unless at least one dependent SOR module is installed.

### `set_menu_active` utility

`utils.py` provides a shared `set_menu_active(env, xmlid, active)` helper that SOR feature modules use to suppress and restore native Odoo menus in a reversible, hook-based way.

```python
from odoo.addons.sor_technical_menu.utils import set_menu_active

def post_init_hook(env):
    set_menu_active(env, 'stock.menu_stock_root', False)   # suppress

def uninstall_hook(env):
    set_menu_active(env, 'stock.menu_stock_root', True)    # restore
```

**Contract:**
- `xmlid` does not need to exist — if the target menu is absent, the call is a no-op (no exception).
- The `active` flag maps directly to `ir.ui.menu.active`. Setting `False` hides the menu and all its children.
- The helper uses `.sudo()` internally so it can be called during hook execution when admin context is not guaranteed.
- Each native surface must be owned by exactly one SOR feature module. That module registers the `post_init_hook` (suppress) and `uninstall_hook` (restore).

**Current suppression registry:**

| Native surface | xmlid | Owner module | Reason |
|----------------|-------|-------------|--------|
| Inventory top-level menu | `stock.menu_stock_root` | `sor_artwork` | SOR Artworks replaces native Inventory navigation |

---

## Configuration

No configuration is required or available. The module installs and the menu root exists. No settings page, no toggles, no data to populate.

Developer mode must be active to see the menu. Activate it via:
- `Settings → General Settings → Developer Tools → Activate the developer mode`, or
- Append `?debug=1` to any Odoo URL.

---

## Developer Menu

The SOR Technical menu IS the feature of this module. Its presence provides a stable parent for all SOR developer submenus.

**Navigation:** `Settings → Technical → SOR` (developer mode required)

What appears under `SOR` depends entirely on which SOR modules are installed:

| Installed module | Submenu visible |
|-----------------|-----------------|
| `sor_asset_paradigm` | Paradigm Rules — list of all `sor.asset.paradigm.rule` records |
| `sor_business_model` | Business Model Rules — list of all `sor.business.model.rule` records |
| `sor_events` | Events — technical event management |
| `sor_legal_agreement` | Agreements — technical agreement management |

If only `sor_technical_menu` is installed (no dependents), the `SOR` menu root is present but has no children and no visible content.

---

## Building on this Module

To add a SOR Technical submenu entry from another module:

1. Add `sor_technical_menu` to your module's `depends` list in `__manifest__.py`:
   ```python
   'depends': ['sor_technical_menu'],
   ```

2. Create a `<menuitem>` in your module's views XML with `parent="sor_technical_menu.menu_sor_technical_root"`:
   ```xml
   <menuitem
       id="menu_my_module_technical"
       name="My Feature"
       parent="sor_technical_menu.menu_sor_technical_root"
       action="action_my_feature_list"
       groups="base.group_no_one"
       sequence="50"/>
   ```

3. Set `groups="base.group_no_one"` to keep the item in developer mode only, consistent with all other SOR Technical submenus.

4. Set `sequence` to control ordering within the SOR submenu. Existing modules use values in the 10–100 range; choose a value that places your entry logically relative to existing items.

Do not modify `menu_sor_technical_root` directly from your module. Create only your own `<menuitem>` record pointing at the root. This preserves the additive-only composability contract: your module's menu entry is removed cleanly when your module is uninstalled, and the root is left untouched.

### Suppressing a native Odoo menu from your module

If your module replaces a native Odoo UI surface (e.g. a custom Movements list replacing Inventory), suppress the native surface via hooks:

1. Add `sor_technical_menu` to your `depends` list.
2. Import `set_menu_active` in `hooks.py`:
   ```python
   from odoo.addons.sor_technical_menu.utils import set_menu_active
   ```
3. Implement `post_init_hook` to suppress and `uninstall_hook` to restore:
   ```python
   def post_init_hook(env):
       set_menu_active(env, 'your.menu_xmlid', False)

   def uninstall_hook(env):
       set_menu_active(env, 'your.menu_xmlid', True)
   ```
4. Register both hooks in `__manifest__.py` and import in `__init__.py`.

Only one SOR module should own suppression of each native surface — do not add a second hook for a surface already owned by another module.

---

## Regression Checks

**R1 — SOR menu root is visible in developer mode**

1. Activate developer mode (`Settings → General Settings → Developer Tools → Activate the developer mode`).
2. Navigate to `Settings → Technical`.
3. Confirm `SOR` appears as an entry in the Technical menu.
4. Expected: `SOR` entry present.

**R2 — Submenu items are present for installed SOR modules**

1. Activate developer mode.
2. Navigate to `Settings → Technical → SOR`.
3. For each SOR module installed that declares a submenu under this root, confirm its entry appears.
4. Expected: one submenu entry per installed dependent module.
5. If a submenu is missing after upgrading a module, run `docker exec odoo-app python3 odoo-bin ... -u <module_name>` to force a view reload.

---

## Interoperability

| Module | Relationship | What it adds |
|--------|-------------|-------------|
| `sor_asset_paradigm` | Depends on `sor_technical_menu` | Paradigm Rules submenu |
| `sor_business_model` | Depends on `sor_technical_menu` | Business Model Rules submenu |
| `sor_events` | Depends on `sor_technical_menu` | Events submenu |
| `sor_legal_agreement` | Depends on `sor_technical_menu` | Agreements submenu |

`sor_technical_menu` itself depends only on `base`. It has no awareness of any of the modules listed above.
