# Technical Architecture — sor_asset_paradigm

## Overview

`sor_asset_paradigm` is a horizontal SOR mechanism module. It provides the infrastructure that any asset-type bridge module can use to declare and enforce inventory UI suppression for products of a particular paradigm. It does not suppress any UI elements itself — it only provides the field, the rule registry, the query method, and the debug escape hatch.

The module introduces three things onto `product.template`: an `asset_paradigm` Selection field that bridges extend via `selection_add`; a `sor.asset.paradigm.rule` model that stores one rule per element-per-paradigm; and an `is_element_suppressed(element_key)` method that bridges call from their computed suppression booleans. A companion `sor.asset.paradigm.rule.manifestation` sub-model enumerates the specific UI locations each rule affects, for developer inspection.

```
product / stock / mail (Odoo core)
       |
sor_asset_paradigm            ← horizontal mechanism (this module)
       |
       ├── sor_asset_paradigm_baseline   ← auto_install companion
       └── sor_asset_paradigm_artwork    ← bridge (also depends on sor_artwork)
```

---

## Module Pattern

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `False` | Must be explicitly installed; it is not a consequence of any other module being present |
| `application` | `False` | Technical mechanism; not a standalone app |
| `category` | `'Hidden/Technical'` | Excluded from business app listings; surfaced only in developer mode |
| `depends` | `['product', 'stock', 'mail']` | `product` provides `product.template`; `stock` provides `stock.quant` for the audit snapshot; `mail` provides `tracking=True` on `asset_paradigm` |

---

## Architecture Decisions

### Element key vocabulary in `const.py`

All suppression element keys are defined as a Python constant list `SUPPRESSIBLE_ELEMENTS` in `models/const.py`. This list is the `selection` value for the `element_key` field on `sor.asset.paradigm.rule`. Centralising it in one place ensures that bridge modules cannot install rules for keys that are not in the vocabulary, and that the developer UI always reflects the full set of suppressible elements.

### `active` field naming on the rule model

The suppression toggle field is named `active` (not `suppressed` or `enabled`). This is intentional: Odoo's ORM treats `active` as the standard archive field and automatically excludes `active=False` records from default domain searches via the `active_test` context key. Using `active` means:

- The Paradigm Rules list action uses `context={'active_test': False}` to show all rules regardless of their toggle state — without this, unchecked rules would disappear from the list.
- Standard Odoo archive UI patterns work correctly without custom code.
- The field is displayed with `string='Suppressed'` so the user sees "Suppressed" rather than "Active".

A rule with `active=True` means the element **is** suppressed. A rule with `active=False` means suppression is **disabled** for that element (the element reappears). This naming is counterintuitive but correct for the Odoo archive pattern.

### `is_element_suppressed()` uses `search_count`

The `is_element_suppressed(element_key)` method on `product.template` uses `search_count([...])` rather than `search([...])`. This issues a single SQL `COUNT` query rather than loading a recordset. The filter uses only indexed columns (`paradigm`, `element_key`, `active`), making it an index-covered count — effectively a single B-tree lookup. This is important because suppression booleans are `store=False` computed fields that re-evaluate on every page load for every product.

### `store=False` for suppression booleans on bridge modules

Suppression booleans (defined by bridge modules that call `is_element_suppressed()`) are intentionally `store=False`. They depend not only on the product's `asset_paradigm` field value but also on the current state of `sor.asset.paradigm.rule` records, which a developer may toggle at runtime. If the booleans were stored, toggling a rule would not affect any already-stored boolean values — the developer would need to trigger a recompute across all products. With `store=False`, the booleans re-evaluate from the rule registry on every page load. A hard browser refresh is sufficient to see a rule toggle take effect.

### `context={'active_test': False}` in the Paradigm Rules action

The `ir.actions.act_window` for the Paradigm Rules developer menu uses `context={'active_test': False}`. Without this, Odoo's default `search()` behaviour excludes `active=False` records (i.e. rules where Suppressed is unchecked). This would cause those rules to disappear from the developer list the moment a developer unchecked them — defeating the purpose of the UI. The `active_test: False` context shows all rules regardless of their suppression state.

### Manifestation sub-model

`sor.asset.paradigm.rule.manifestation` records enumerate the specific Odoo UI locations (form tab, stat button, list column, kanban element, search filter) that each rule suppresses. These are installed by bridge modules alongside the rule records themselves. They serve as developer documentation embedded in the database — visible in the detail view of a rule — and do not drive any runtime suppression logic. The actual suppression is performed by view `invisible` expressions referencing computed booleans; manifestation records are informational only.

### `write()` override stub for change log

`product_template.py` contains a `write()` override that checks for the presence of `sor.asset.paradigm.log` in the environment before creating an audit entry. The log model itself is not implemented (AC6 Won't Fix — see story Developer Notes). The stub remains in place as a future insertion point. It causes no runtime errors because the guard `if 'sor.asset.paradigm.log' in self.env` evaluates to `False` in all current installations.

### Debug parameter as `ir.config_parameter`

`sor_asset_paradigm.debug_show_quant_ui` is seeded as an `ir.config_parameter` record with `noupdate="1"`. The `noupdate="1"` flag ensures that a developer who sets the value to `True` for debugging will not have it reset to `False` by a subsequent module upgrade (`-u sor_asset_paradigm`). The `is_element_suppressed()` method reads this parameter and short-circuits to `False` when the value is `'True'` (string comparison — `ir.config_parameter` stores all values as strings).

---

## Models

### `product.template` (extended)

| Field / Method | Type | Purpose |
|----------------|------|---------|
| `asset_paradigm` | `Selection(selection=[('standard', 'Standard')], default=False, index=True, tracking=True)` | Classifies what kind of asset the product is. Bridges extend this via `selection_add`. `index=True` because `is_element_suppressed()` filters on this column. `tracking=True` records changes in the chatter. |
| `is_element_suppressed(element_key)` | `def` → `bool` | Returns `True` if an active `sor.asset.paradigm.rule` exists for `self.asset_paradigm` and `element_key`. Returns `False` if: no paradigm is set, the debug parameter is `'True'`, or no active rule exists. Called by bridge computed booleans. |
| `_serialize_quant_snapshot()` | `def` → `str` (JSON) | Captures the current `stock.quant` rows for this product as a JSON string. Called by the `write()` stub when `asset_paradigm` changes. Returns location name, lot ID, quantity, and reserved quantity per quant row. |
| `write(vals)` | override | Stub: checks for `sor.asset.paradigm.log` model presence before creating an audit entry. Currently a no-op; change log model is not implemented. |

### `sor.asset.paradigm.rule`

| Field | Type | Purpose |
|-------|------|---------|
| `paradigm` | `Char(required=True, index=True)` | The `asset_paradigm` value this rule applies to (e.g. `'unique_object'`). Indexed for `is_element_suppressed()` filtering. |
| `element_key` | `Selection(from SUPPRESSIBLE_ELEMENTS, required=True)` | The vocabulary key for the UI element this rule suppresses. Constrained to entries in `const.SUPPRESSIBLE_ELEMENTS`. |
| `active` | `Boolean(default=True, string='Suppressed')` | When `True`, the element is suppressed for this paradigm. When `False`, suppression is disabled. Named `active` to participate in Odoo's archive mechanism. |
| `description` | `Char` | Human-readable note on what is suppressed and why. Installed by bridge data files. |
| `element_code` | `Char(computed, store=False)` | Displays the raw `element_key` value in the form view for developer reference. |
| `manifestation_ids` | `One2many → sor.asset.paradigm.rule.manifestation` | The specific UI locations suppressed by this rule. Installed by bridge data files. |
| `manifestation_count` | `Integer(computed, store=False)` | Count of `manifestation_ids`. Displayed as "Instances" in the list view. |
| `has_static_manifestation` | `Boolean(computed, store=False)` | `True` if any linked manifestation has `is_static=True`. Drives a conditional footer note in the form view. |

SQL constraint: `UNIQUE(paradigm, element_key)` — one rule per paradigm + element combination.

`_order = 'paradigm, element_key'`

### `sor.asset.paradigm.rule.manifestation`

| Field | Type | Purpose |
|-------|------|---------|
| `rule_id` | `Many2one(sor.asset.paradigm.rule, required=True, ondelete='cascade', index=True)` | Parent rule. |
| `element_name` | `Char(required=True)` | Human-readable label for this UI element (e.g. `'Forecasted Qty Smart Button'`). |
| `element_key` | `Char(required=True)` | Odoo's technical identifier for the element (field name, page name, or button name). |
| `ui_element_type` | `Char(required=True)` | Type per Odoo nomenclature (e.g. `'Smart Button'`, `'Form Tab'`, `'List Column'`). |
| `ui_location` | `Char(required=True)` | Odoo UI path where suppression is applied (e.g. `'Product Template Form > General Information Tab'`). |
| `is_static` | `Boolean(default=False)` | `True` if suppression is applied statically (e.g. via `column_invisible="True"`) and will not respond to rule toggle. Used to warn developers in the detail view. |
| `static_marker` | `Char(computed, store=False)` | Displays `'*'` when `is_static=True`. Shown in the manifestation table in the form view. |

`_order = 'rule_id, id'`

---

## Views

### `product_template_views.xml`

**`view_product_tmpl_asset_paradigm_field`** — inherits `product.product_template_form_view`

XPath: `//page[@name='general_information']//field[@name='categ_id']` position `after`

Inserts `asset_paradigm` with `widget="badge"` immediately below the Category field in the General Information tab. The badge widget renders coloured pill-style text when a value is set, and nothing when the value is `False` (default). Visible at all times regardless of paradigm assignment.

### `sor_asset_paradigm_rule_views.xml`

**List view** — `view_sor_asset_paradigm_rule_list`

Columns: Paradigm | Feature (`element_key`) | Instances (`manifestation_count`) | Suppressed (`active`, readonly in list). `create="0"` and `delete="0"` — rules are installed by bridge data files; list manipulation via UI is not supported.

**Form view** — `view_sor_asset_paradigm_rule_form`

Two groups: identity (paradigm + element_key, both readonly) and rule (active / Suppressed + description). Below the groups: a readonly inline `manifestation_ids` table showing all UI Manifestations for this rule, with a conditional footer note when `has_static_manifestation` is `True` explaining that `*` indicates statically-suppressed elements unaffected by the toggle.

**Action** — `action_sor_asset_paradigm_rule`

`context={'active_test': False}` ensures rules with `active=False` (Suppressed unchecked) remain visible in the list. Without this context, the Odoo ORM's default domain excludes inactive records, causing toggled-off rules to disappear.

**SOR root menu** — `menu_sor_technical_root`

The canonical `Settings → Technical → SOR` entry point for all SOR developer menus. Parented to `base.menu_custom`. `groups="base.group_no_one"` restricts visibility to developer mode. `sequence=100`. Other SOR modules attach their submenus here.

**Paradigm Rules submenu** — `menu_sor_asset_paradigm_rules`

Parented to `menu_sor_technical_root`. `sequence=10`. Points to the Paradigm Rules action.

---

## Module File Structure

```
sor_asset_paradigm/
├── __init__.py                                      # Imports models package
├── __manifest__.py                                  # Module declaration
├── models/
│   ├── __init__.py                                  # Imports const, product_template, rules, manifestation
│   ├── const.py                                     # SUPPRESSIBLE_ELEMENTS vocabulary list
│   ├── product_template.py                          # asset_paradigm field, is_element_suppressed(), write() stub
│   ├── sor_asset_paradigm_rule.py                  # Rule registry model
│   └── sor_asset_paradigm_rule_manifestation.py    # UI manifestation sub-model
├── views/
│   ├── product_template_views.xml                  # asset_paradigm badge field on product form
│   └── sor_asset_paradigm_rule_views.xml           # Rule list, form, action, SOR menu
├── security/
│   └── ir.model.access.csv                         # Read-only for all users; CRUD for sys admin
├── data/
│   └── ir_config_parameter_data.xml               # Seeds debug_show_quant_ui = False
├── tests/
│   ├── __init__.py                                 # Imports test module
│   └── test_sor_asset_paradigm.py                 # Tests for AC1–AC5, AC7–AC9
└── doc/
    ├── KNOWLEDGE_BASE.md                           # User guides and regression checks
    └── TECHNICAL_ARCHITECTURE.md                  # This file
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/const.py` | Single source of truth for all suppressible element keys. Changes here affect every bridge's rule data and every view's `invisible` expression. |
| `models/sor_asset_paradigm_rule.py` | Rule registry model. The `active` field naming and the SQL UNIQUE constraint are the two most critical design choices here. |
| `models/product_template.py` | `is_element_suppressed()` is the method every bridge calls. Its performance characteristics (`search_count`, indexed columns) matter for page load time. |
| `data/ir_config_parameter_data.xml` | Seeds the debug parameter with `noupdate="1"`. Must keep `noupdate` to preserve developer-set values across upgrades. |
| `views/sor_asset_paradigm_rule_views.xml` | Contains `menu_sor_technical_root` — the shared SOR developer submenu root that every other SOR developer menu attaches to. Do not remove. |

---

## Composability Boundary

| Module combination | `asset_paradigm` field | Rule registry | `is_element_suppressed()` | Developer menu |
|--------------------|------------------------|---------------|--------------------------|----------------|
| `sor_asset_paradigm` alone | Present; value is `False` by default | Empty | Returns `False` (no rules) | Paradigm Rules list (empty); SOR root menu present |
| `+ sor_asset_paradigm_baseline` | `'standard'` value available | Still empty | Returns `False` | Baseline Product menu added |
| `+ sor_asset_paradigm_artwork` | `'unique_object'` value available | 13 rules for `unique_object` | Returns `True` for artwork elements | Paradigm Rules list populated |
| All three installed | As above | 13 rules | As above | Both submenus present |

---

## Special Concerns

### `base.group_no_one` and developer mode

All SOR developer menus use `groups="base.group_no_one"`. In Odoo 19, `base.group_no_one` is the group that maps to developer mode — members of this group see developer-mode-only UI elements. The group is populated automatically when a user activates developer mode. Do not confuse it with `base.group_system` (admin); developer mode visibility is separate from admin access.

### `tracking=True` requires `mail` dependency

The `asset_paradigm` field uses `tracking=True`, which causes paradigm changes to be logged in the product's chatter. This requires the `mail` module as a dependency. Without `mail`, the `tracking` attribute is silently ignored in some Odoo versions; in others it causes an import error. The dependency is declared to be explicit.

### `noupdate="1"` on the debug parameter

The `ir_config_parameter_data.xml` uses `noupdate="1"` (or equivalent) on the `sor_asset_paradigm.debug_show_quant_ui` record. This prevents module upgrades from resetting a value of `'True'` that a developer has set for debugging. If you need to reset the parameter to `'False'` after an upgrade, do so manually via Settings → Technical → Parameters → System Parameters.

### The `write()` override is a stub

The `write()` override in `product_template.py` is intentionally non-functional. The change-log model (`sor.asset.paradigm.log`) was descoped (AC6 Won't Fix). The stub remains to provide a future insertion point without requiring a new model-level override at that time. The guard `if 'sor.asset.paradigm.log' in self.env` evaluates to `False` at all times in the current installation, so the block is never entered and there is no performance impact.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init \
  --http-port=8071 \
  -u sor_asset_paradigm,sor_asset_paradigm_baseline,sor_asset_paradigm_artwork
```

All three modules are upgraded together because the test suite relies on bridge rules being present to test suppression-active and suppression-inactive paths.

---

## Story Reference

Parent story: [01 Asset Paradigm Foundation](../../../.backlog/00%20Asset%20Paradigm/stories/01_Asset-Paradigm-Foundation.md)
