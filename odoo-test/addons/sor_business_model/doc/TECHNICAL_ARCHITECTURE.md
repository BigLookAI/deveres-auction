# SOR Business Model — Technical Architecture

## Overview

`sor_business_model` is a horizontal SOR paradigm module that records an organisation's business model at the company level and provides a rule-based suppression mechanism for commerce fields on product forms. It follows the same paradigm pattern as `sor_asset_paradigm`: the base module owns the mechanism, bridge modules own the rules.

The module ships with four built-in selection values (`non_commercial`, `primary_market_gallery`, `secondary_market_gallery`, `auction_house`) representing the four art-market business models currently in scope for SOR. Bridge modules that implement suppression for any of these values depend on `sor_business_model` and install `sor.business.model.rule` records.

**Dependency:** `product`, `base`

---

## Module Pattern

```python
{
    'depends': ['product', 'base'],
    'auto_install': False,
    'application': False,
    'category': 'Hidden/Technical',
}
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `False` | Installed explicitly — it is a standalone horizontal module |
| `application` | `False` | Not a top-level app; navigation is provided by domain bridges |
| `category` | `Hidden/Technical` | Infrastructure; not surfaced in the App Store |
| `depends: product` | Required | `product.template` is extended with `effective_business_model` and `is_field_suppressed` |
| `depends: base` | Required | `res.company` is extended with `business_model`; `res.config.settings` is extended for the settings UI |

---

## Architecture Decisions

**Business model is set at company level, not product level**
Commerce behaviour varies by organisation type (non-commercial collection vs. auction house), not by individual product. Setting the value on `res.company` means all products in a company share the same suppression rules without per-record configuration. A multi-company Odoo instance can have SO Fine Art set to `primary_market_gallery` while SETU is `non_commercial` — they operate independently.

**Four values in the base module; bridges extend via `selection_add`**
The four built-in values represent the complete set of art-market business models in the current SOR scope. They are declared directly in `res_company.py` (not via `selection_add`) because they are core product definitions, not optional bridge additions. A bridge module that targets one of these values uses `is_field_suppressed()` with rules — it does not need to `selection_add` a new value unless it is introducing a genuinely new model type beyond the four.

**`effective_business_model` is `store=False`**
The computed field on `product.template` reads `env.company.business_model` at call time. It must be `store=False` because: (1) the value changes when the company's business model is updated in Settings and (2) a multi-company user switching active company would need a separate stored value per company per product — impractical. The `store=False` approach reads the live context value on every form load.

**`is_field_suppressed` uses `search_count`**
`is_field_suppressed(field_key)` executes a `search_count` against `sor.business.model.rule` rather than `search` + truth test. `search_count` maps to a single SQL `COUNT(*)` with no record loading. Both `business_model` and `field_key` are indexed fields on the rule model, making this a fast lookup even with large rule tables. The explicit `('active', '=', True)` filter is required — `search_count` respects `active_test: True` by default, but the developer menu action uses `active_test: False`, so being explicit prevents confusion.

**Settings block placed after Companies, not in a new page**
The Business Model setting is surfaced via a `<block>` inside the standard General Settings page. Creating a dedicated settings page for a single field would be disproportionate. The `xpath` anchor `//block[@name='companies_setting_container']` places it immediately below the Companies block, which is the most logical grouping — the business model is a company-level property.

**Rule `active` field is named `active` (Odoo archive field)**
The `active` field on `sor.business.model.rule` follows Odoo's archive convention: `active=True` means the record is active/in-use (suppression is on); `active=False` means it is archived/inactive (suppression is off). This integrates automatically with ORM filter behaviour and developer tools. The field label is `Suppressed` in the UI to communicate its purpose to the operator, while the field name preserves Odoo archive semantics.

**Manifestation model for developer transparency**
`sor.business.model.rule.manifestation` documents exactly which UI elements each rule suppresses. This model is read-only in the developer menu — bridge modules install manifestation records alongside their rule records. Static manifestations (suppressed at the XML level, not toggleable at runtime) are marked with `is_static=True` and annotated in the form view.

---

## Models

### res.company (extended)

| Field | Type | Notes |
|-------|------|-------|
| `business_model` | Selection | Default `non_commercial`; required; four built-in values |

**Selection values:**

| Value | Label |
|-------|-------|
| `non_commercial` | Non-Commercial |
| `primary_market_gallery` | Primary Market Gallery |
| `secondary_market_gallery` | Secondary Market Gallery |
| `auction_house` | Auction House |

### res.config.settings (extended)

| Field | Type | Notes |
|-------|------|-------|
| `business_model` | Selection | Related to `company_id.business_model`; `readonly=False` for settings write |

### product.template (extended)

| Field / Method | Type | Notes |
|---|---|---|
| `effective_business_model` | Char (computed) | `store=False`; returns `env.company.business_model` |
| `is_field_suppressed(field_key)` | method → bool | Returns `True` if active rule exists for current model + field_key |

### sor.business.model.rule

| Field | Type | Notes |
|-------|------|-------|
| `business_model` | Char | Required; indexed; e.g. `'non_commercial'` |
| `field_key` | Selection | From `SUPPRESSIBLE_FIELDS` in `const.py`; required |
| `active` | Boolean | Default `True`; label `Suppressed`; Odoo archive field |
| `description` | Char | Optional human-readable note |
| `field_code` | Char (computed) | `store=False`; echoes `field_key` for display |
| `manifestation_ids` | One2many → `rule.manifestation` | UI element records installed by bridges |
| `manifestation_count` | Integer (computed) | Count of linked manifestations |
| `has_static_manifestation` | Boolean (computed) | True if any linked manifestation is `is_static=True` |

**Model attributes:**
- `_order = 'business_model, field_key'`
- No `_check_company_auto` — rule records are global (company-agnostic); the company context is encoded in the `business_model` string value, not a company FK

### sor.business.model.rule.manifestation

| Field | Type | Notes |
|-------|------|-------|
| `rule_id` | Many2one → `sor.business.model.rule` | Required; `ondelete='cascade'` |
| `element_name` | Char | Human-readable name (e.g. `Can be Sold Toggle`) |
| `element_key` | Char | Odoo technical identifier (e.g. `sale_ok`) |
| `ui_element_type` | Char | Element type (e.g. `Toggle`, `Field`, `Form Tab`) |
| `ui_location` | Char | UI path (e.g. `Product Template Form > Sales Tab`) |
| `is_static` | Boolean | Default `False`; True = suppressed at XML level, not runtime-toggleable |
| `static_marker` | Char (computed) | Renders `*` when `is_static=True` |

---

## Views

### sor_business_model_rule_view_list (primary)

List view for `sor.business.model.rule`. Columns: business_model, feature (field_key), instances (manifestation_count), suppressed (active). `create="0"` and `delete="0"` — rules are managed by bridge module data, not created manually.

### sor_business_model_rule_view_form (primary)

Form view for `sor.business.model.rule`. Displays identity fields (read-only), the `Suppressed` toggle (editable), description, and the manifestations list. A static-suppression notice appears when `has_static_manifestation = True`. `create="0"` and `delete="0"`.

### res_config_settings (inherited)

Inherits `base_setup.res_config_settings_view_form`. Inserts a `<block>` after `companies_setting_container` containing the `business_model` field.

### Window action (action_sor_business_model_rules)

Mode: `list,form`. Context: `{'active_test': False}` — ensures inactive (unchecked Suppressed) rules remain visible in the developer list.

---

## Module File Structure

```
sor_business_model/
├── __init__.py
├── __manifest__.py
├── doc/
│   ├── KNOWLEDGE_BASE.md
│   └── TECHNICAL_ARCHITECTURE.md
├── i18n/
│   └── sor_business_model.pot
├── models/
│   ├── __init__.py
│   ├── const.py                           SUPPRESSIBLE_FIELDS vocabulary
│   ├── product_template.py                effective_business_model; is_field_suppressed()
│   ├── res_company.py                     business_model Selection field (4 values)
│   ├── res_config_settings.py             settings proxy field
│   ├── sor_business_model_rule.py         sor.business.model.rule model
│   └── sor_business_model_rule_manifestation.py  sor.business.model.rule.manifestation
├── security/
│   └── ir.model.access.csv               rule: read for users, write for system; manifestation same
├── tests/
│   ├── __init__.py
│   └── test_sor_business_model.py
└── views/
    ├── res_config_settings_views.xml      Business Model block in General Settings
    └── sor_business_model_rule_views.xml  Rule list+form; window action; developer menu
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/const.py` | `SUPPRESSIBLE_FIELDS` vocabulary — all bridge modules must use these keys |
| `models/res_company.py` | Four built-in business model values; default `non_commercial` |
| `models/product_template.py` | `effective_business_model` computed field; `is_field_suppressed()` method |
| `models/sor_business_model_rule.py` | Rule model — the central data structure for suppression decisions |
| `views/sor_business_model_rule_views.xml` | Developer menu + window action with `active_test: False` |
| `views/res_config_settings_views.xml` | Settings page integration |

---

## Composability Boundary

| Modules installed | Behaviour |
|-------------------|-----------|
| `sor_business_model` only | Business Model field on company (4 values). Rule lookup mechanism. Developer menu. No suppression rules installed. |
| `sor_business_model` + `sor_business_model_non_commercial` | Bridge auto-installs. `non_commercial` rules installed: Can be Sold, Sales Price, Sales tab, etc. suppressed for non-commercial companies. |
| Any of the 4 values without a bridge | `is_field_suppressed()` returns `False` — no rules installed for that value. Full product form visible. |
| `sor_business_model` + `sor_asset_paradigm` | Both mechanisms active independently. Asset Paradigm suppresses inventory elements by product type; Business Model suppresses commerce elements by company type. No interaction. |

---

## Special Concerns

**`active_test: False` required in the developer window action**
Without `context={'active_test': False}`, unchecked rules (Suppressed=False, `active=False`) are excluded from the list by Odoo's default archive filter. Developers need to see all rules regardless of toggle state. The window action in `sor_business_model_rule_views.xml` includes this context explicitly.

**`effective_business_model` triggers a page refresh requirement**
Because `effective_business_model` reads `env.company` at form load time and is `store=False`, changing the company's business model in General Settings does not immediately update already-open product forms. A hard browser refresh (Cmd+Shift+R / Ctrl+Shift+R) is required. This is by design and matches the same behaviour as other context-dependent computed fields in Odoo.

**Bridge modules must use `noupdate="1"` on rule data**
Rule data records installed by bridge modules (e.g. `sor_business_model_non_commercial/data/sor_business_model_rules.xml`) must use `<data noupdate="1">`. Without this, running `-u <bridge_module>` resets any developer toggles made at runtime — a support and debugging burden.

**`is_field_suppressed` does not check `env.company` directly**
It reads `self.effective_business_model`, which in turn reads `env.company.business_model`. This indirection means the method respects the `with_company()` context pattern used in tests and multi-company scenarios. A direct `env.company` lookup in `is_field_suppressed` would miss the context override.

**Access control: users read-only, system read-write**
Regular users can read rules (needed to evaluate `is_field_suppressed`) but cannot create, modify, or delete them. This is enforced in `ir.model.access.csv`. Bridge modules install their rule records using the module's own data loading (runs as system), bypassing the user restriction.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  --http-port=8099 \
  -d odoo --test-enable --stop-after-init \
  --test-tags='sor_business_model' \
  -u sor_business_model
```

**Note:** Tests for suppression use `business_model='auction_house'` rather than `'non_commercial'` to avoid interference from pre-existing rules installed by `sor_business_model_non_commercial`. The `auction_house` value has no bridge module installed, guaranteeing a clean rule table for each test.

---

## Story Reference

- Story 01: `.backlog/current/Auction Foundations/stories/01_Business-Model-Selection-Values.md`
