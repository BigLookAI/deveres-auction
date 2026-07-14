# Technical Architecture: sor_technical_menu

## Overview

`sor_technical_menu` is a **pure infrastructure stub module** that owns exactly one record: `menu_sor_technical_root`, the `Settings → Technical → SOR` menu root. It has no Python code beyond an empty `__init__.py`, no models, and no data beyond the single menu item XML record.

Its sole function is to give the SOR technical menu root a stable, dependency-light home. Before it existed, `sor_asset_paradigm` owned the root — forcing every module that wanted a SOR Technical submenu to take an undeclared dependency on `sor_asset_paradigm` and all its logic. `sor_technical_menu` costs only a `base` dependency.

Dependency diagram:

```
base
 └── sor_technical_menu
          ├── sor_asset_paradigm   (adds: Paradigm Rules submenu)
          ├── sor_business_model   (adds: Business Model Rules submenu)
          ├── sor_events           (adds: Events submenu)
          └── sor_legal_agreement  (adds: Agreements submenu)
```

---

## Module Pattern

**Manifest flags:**

```python
'application': False,
'category': 'Hidden/Technical',
'auto_install': False,
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `application` | `False` | Infrastructure module — not a user-facing application |
| `category` | `'Hidden/Technical'` | Kept out of business category listings in the Apps menu |
| `auto_install` | `False` | Explicit install required; dependents declare it in their `depends` list |
| `depends` | `['base']` | No SOR logic dependencies — pure menu infrastructure |

`auto_install` is `False` because this module is not the intersection of two parents — it is a common dependency that other modules opt into explicitly. This is distinct from bridge modules, which use `auto_install=True` because they activate at a module intersection point.

---

## Architecture Decisions

**Why a dedicated stub module instead of keeping the menu in `sor_asset_paradigm`?**

`sor_asset_paradigm` introduced the SOR Technical root menu as an implementation detail — it needed a place to put its Paradigm Rules submenu. Subsequent modules (`sor_business_model`, `sor_events`, `sor_legal_agreement`) needed submenus under the same root and therefore took undeclared or implicit dependencies on `sor_asset_paradigm`. This is a composability violation: a module depending on another for navigation infrastructure rather than for functional reasons.

Extracting the root menu to a stub module gives it a declared, purposeful home with minimal dependency weight (`base` only).

**Why not put the menu in `base` or a global settings module?**

The SOR Technical menu is SOR-specific and developer-mode-only. Placing it in `base` would pollute the base module with product-specific UI. Placing it in an Odoo settings module would create a dependency on Odoo app modules. `sor_technical_menu` as a minimal stub is the correct scope.

**Why not inline the menu in every module that needs it?**

An `ir.ui.menu` record has a unique `id` constraint. If two modules both declared `menu_sor_technical_root`, the second install would overwrite or conflict with the first. The root must be owned by exactly one module.

**No `noupdate` needed**

Menu records are not runtime-togglable and are not customised by administrators in production. `noupdate="1"` is not applied. Upgrades may safely refresh the menu record.

---

## Models

None. This module defines no models and extends no models.

---

## Python Utilities

`utils.py` provides one shared function used by SOR feature modules to suppress and restore native Odoo menus in a reversible, hook-based way.

### `set_menu_active(env, xmlid, active)`

```python
def set_menu_active(env, xmlid, active):
```

| Parameter | Type | Purpose |
|-----------|------|---------|
| `env` | `Environment` | The Odoo environment (from `post_init_hook` or `uninstall_hook`) |
| `xmlid` | `str` | Fully-qualified XML ID of the `ir.ui.menu` record to toggle |
| `active` | `bool` | `False` to suppress; `True` to restore |

**Contract:**
- If `xmlid` does not exist, the call is a no-op — no exception is raised.
- Uses `.sudo()` internally so it is safe to call during hook execution when admin context is not guaranteed.
- Maps directly to `ir.ui.menu.active`. Setting `False` hides the menu and all its children.

**Import pattern:**
```python
from odoo.addons.sor_technical_menu.utils import set_menu_active
```

**Current suppression registry** — each native surface is owned by exactly one SOR feature module:

| Native surface | xmlid | Owner module | Delivered |
|----------------|-------|-------------|-----------|
| Inventory top-level menu | `stock.menu_stock_root` | `sor_artwork` | Story 06 — Movement Layer Completion |

---

## Views

One record defined in `views/sor_technical_menu_menus.xml`:

| Record | Type | XML ID | Notes |
|--------|------|--------|-------|
| SOR Technical root menu | `ir.ui.menu` | `sor_technical_menu.menu_sor_technical_root` | Parent: `base.menu_custom` (Settings → Technical). Groups: `base.group_no_one` (developer mode only). Sequence: 100. |

The record is a plain `<menuitem>` — no action attached. It is a navigation container only. The Odoo menu system renders it without error even when it has no children; when dependents are installed, their submenu `<menuitem>` records reference this record as their parent.

---

## Module File Structure

```
sor_technical_menu/
├── __manifest__.py          # Module manifest — depends on base only
├── __init__.py              # Empty — no Python code in this module
├── utils.py                 # set_menu_active() — shared menu suppression utility
├── views/
│   └── sor_technical_menu_menus.xml  # Single menuitem: menu_sor_technical_root
├── i18n/
│   └── sor_technical_menu.pot        # Translatable strings (menu name only)
├── tests/
│   ├── __init__.py          # Imports test_sor_technical_menu
│   └── test_sor_technical_menu.py   # Menu existence, name, parent, group, composability
└── doc/
    ├── KNOWLEDGE_BASE.md    # User-facing reference
    └── TECHNICAL_ARCHITECTURE.md    # This document
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | Module declaration — `depends: ['base']`, `auto_install: False` |
| `utils.py` | `set_menu_active(env, xmlid, active)` — shared menu suppression/restoration utility |
| `views/sor_technical_menu_menus.xml` | Owns `menu_sor_technical_root` — the single SOR Technical menu root |
| `tests/test_sor_technical_menu.py` | Verifies menu existence, name, parent, group restriction, and composability |

---

## Composability Boundary

| Installation state | Menu root present | SOR submenus present |
|-------------------|-------------------|----------------------|
| `sor_technical_menu` only | Yes | No |
| `sor_technical_menu` + `sor_asset_paradigm` | Yes | Paradigm Rules |
| `sor_technical_menu` + `sor_business_model` | Yes | Business Model Rules |
| `sor_technical_menu` + `sor_events` | Yes | Events |
| `sor_technical_menu` + `sor_legal_agreement` | Yes | Agreements |
| All of the above | Yes | All four submenus |

The composability contract is additive: each dependent module adds its own submenu entry and no dependent can modify or remove the root record owned by `sor_technical_menu`.

---

## Special Concerns

**Developer-mode-only visibility**

The menu is restricted via `groups="base.group_no_one"`. `base.group_no_one` is the Odoo group that maps to developer mode — only users with developer mode active belong to it. This keeps the SOR Technical navigation invisible to end users in production.

All SOR Technical submenus added by dependent modules must also declare `groups="base.group_no_one"` on their own `<menuitem>` records. If a dependent omits this, its submenu becomes visible to all users even though the parent is developer-only. This is a per-module responsibility — `sor_technical_menu` does not enforce group inheritance on children.

**Sequence value**

`sequence="100"` places the SOR entry towards the end of the Settings → Technical menu. When adding submenus from dependent modules, choose sequence values that produce a logical ordering within the SOR group (existing modules use 10–50 range).

**No action on the root**

The root `<menuitem>` has no `action` attribute. Clicking it in the UI expands the submenu without navigating anywhere. This is standard Odoo behaviour for menu container nodes.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_technical_menu
```

All five tests should pass. The composability tests (`test_composability_*`) are meaningful only when at least one dependent SOR module is installed in the test database — they are written to pass as long as one known dependent submenu is present.

---

## Story Reference

`.backlog/current/D1 Completions/stories/01_SOR-Technical-Menu.md`
