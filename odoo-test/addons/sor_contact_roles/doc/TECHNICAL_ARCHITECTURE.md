# Technical Architecture: SOR Contact Roles

## Overview

`sor_contact_roles` extends Odoo's contact model (`res.partner`) with an art-market contact type system. It defines a two-level type hierarchy (Creator/Contact as parent types; Artist/Bidder/Buyer/Consignor/Donor/Lender as sub-types), adds computed boolean flags used as domain filters across all SOR modules, and implements an activity-earned sub-type assignment mechanism.

**Dependency diagram:**

```
contacts (Odoo core)
       │
       ▼
sor_contact_roles
       │
       ├── sor_locations_external (bridge: auto_install)
       ├── sor_locations_artist_studios (bridge: auto_install)
       ├── sor_artwork (known violation — tracked as sor_artwork_contact_roles spike)
       └── sor_bidding (bridge: auto_install)
```

**Story reference:** `.backlog/current/Contact Roles Enhancements/stories/02_Contact-Type-Hierarchy-Restructure.md`

---

## Module pattern

```python
'name': 'SOR Contact Roles',
'depends': ['contacts'],
'auto_install': False,   # base module — user-installed
'application': False,
'category': 'Hidden/Technical',
```

---

## Architecture decisions

### Two-field Many2many split

`res.partner` uses two separate Many2many fields: `contact_types` (parent types only) and `contact_subtypes` (sub-types only). Both point to `sor.contact.type` but with different `domain` constraints. This split:

- Allows the form widget to render parent types and sub-types in separate sections with distinct UX semantics
- Enables sub-type assignments from external modules (e.g. `sor_bidding` writes to `contact_subtypes`) without touching the parent-type field
- Allows `contact_types` to enforce `domain=[('parent_type_id', '=', False)]` and `contact_subtypes` to enforce `domain=[('parent_type_id', '!=', False)]`

**Critical pitfall:** The `domain` on a Many2many field is applied at ORM search time via a JOIN on the comodel table (not just in the UI widget). Once a contact type has `parent_type_id` set, `env['res.partner'].search([('contact_types', 'in', [type.id])])` returns 0 — the JOIN filters out any type with a parent. Migration hooks that need to find stale M2M rows must use raw SQL to bypass this domain. See `odoo_conventions.md` for the raw SQL + flush/invalidate pattern.

### Activity-earned sub-type auto-assignment (C5 fix)

Contact sub-types (Bidder, Buyer, Consignor, Donor, Lender) are assigned by the system when a contact participates in a relevant transaction. When a Contact sub-type is assigned and the Contact parent type is not yet present, the parent type is auto-assigned.

**Implementation:** `create()` and `write()` overrides on `res.partner` call `_ensure_parent_type_for_subtypes()` after any contact_subtypes change. This was moved from `@api.constrains` (which must not write) to write/create overrides.

### noupdate="1" on seed data

All seeded contact type records use `noupdate="1"`. Administrator changes to type records at runtime are preserved on module upgrade.

### Upgrade migration versioning

Each breaking change to the data model bumps the module version and adds a migration script in `migrations/<version>/`. The current version is `19.0.1.5.0`. The migration chain is:

| Version | Script | Purpose |
|---------|--------|---------|
| 19.0.1.2.0 | pre-migrate.py | Delete stale view records referencing `is_customer`/`has_customer_type` before data files load |
| 19.0.1.3.0 | post-migrate.py | First pass — migrate Customer→Contact rename |
| 19.0.1.4.0 | post-migrate.py | Second pass — generalise migration loop to cover all activity-earned types |
| 19.0.1.5.0 | post-migrate.py | Fix stale M2M rows using raw SQL (ORM domain bypass) |

---

## Models

### `sor.contact.type`

| Field | Type | Purpose |
|-------|------|---------|
| `name` | Char | Display name |
| `code` | Char | Technical identifier — unique, used in computed flags |
| `type_category` | Selection (`creator`, `contact`) | Category grouping for flag computation |
| `parent_type_id` | Many2one (self) | Parent type reference; `False` for parent types |
| `child_ids` | One2many (self) | Sub-types of this type |
| `company_id` | Many2one (res.company) | `False` for globally shared types |
| `active` | Boolean | Archive field — inactive types are hidden from default searches |

**Constraints:**
- `models.Constraint('unique(code)', ...)` — database-level code uniqueness
- `@api.constrains('parent_type_id')` — prevents circular references in the hierarchy

**Multi-company rule:** `sor_contact_type_rule_multi_company` — domain `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`. All seeded types have `company_id=False` (globally shared).

### `res.partner` (extended)

**Many2many fields:**

| Field | Domain on comodel | Purpose |
|-------|------------------|---------|
| `contact_types` | `[('parent_type_id', '=', False)]` | Parent type assignments |
| `contact_subtypes` | `[('parent_type_id', '!=', False)]` | All sub-type assignments (staff + earned) — source of truth |
| `staff_subtype_ids` | computed (no comodel domain) | Non-earned sub-types only; inverse writes back to `contact_subtypes` preserving earned; used by the editable form widget |
| `activity_earned_subtype_ids` | computed (no comodel domain) | Earned sub-types only; read-only display in form |
| `creator_subtypes` | computed (no comodel domain) | Sub-types from `contact_subtypes` where `parent_type_id.code == 'creator'`; used in Creator list view to prevent contact sub-types (e.g. Bidder) appearing in a creator context |
| `contact_role_subtypes` | computed (no comodel domain) | Sub-types from `contact_subtypes` where `parent_type_id.code == 'contact'`; used in Contact and Collector list views |
| `preferred_artist_ids` | `[('is_creator', '=', True)]` | Preferred artist contacts |

**Computed flag fields (all `store=True`, `readonly=True`):**

| Field | True when |
|-------|-----------|
| `is_creator` | Creator type or any Creator sub-type assigned |
| `is_artist` | Artist sub-type assigned |
| `is_contact` | Contact parent type assigned |
| `has_contact_type` | Contact parent type or any Contact sub-type assigned |
| `has_creator_type` | Creator parent type or any Creator sub-type assigned |
| `is_bidder` | Bidder sub-type assigned |
| `is_consignor` | Consignor sub-type assigned |
| `is_donor` | Donor sub-type assigned |

**UI helper fields (all `store=False`):**

| Field | Purpose |
|-------|---------|
| `show_subtypes` | `True` when Creator or Contact is in `contact_types` — controls sub-types widget visibility |

**Creator-specific fields:** `biography`, `birth_date`, `nationality`, `website`, `social_media_ids` (One2many to `sor.contact.social.media`)

**Contact-specific fields:** `collection_focus`, `preferred_artist_ids`

**Methods:**

| Method | Signature | Purpose |
|--------|-----------|---------|
| `create` | `(vals_list) → records` | Auto-sets `company_id`; calls `_ensure_parent_type_for_subtypes` |
| `write` | `(vals) → bool` | Calls `_ensure_parent_type_for_subtypes` when `contact_subtypes` changes |
| `_ensure_parent_type_for_subtypes` | `() → None` | For each sub-type assigned, auto-assigns its parent type if missing |
| `_compute_contact_type_flags` | computed | Sets all `is_*` and `has_*` boolean flags |
| `_compute_creator_subtypes` | computed | Filters `contact_subtypes` to creator-parent sub-types only |
| `_compute_contact_role_subtypes` | computed | Filters `contact_subtypes` to contact-parent sub-types only |
| `_onchange_contact_types` | onchange | Auto-assigns Artist when Creator is selected; clears invalid sub-types |

---

## Views

| View | Type | Inherits | What it adds |
|------|------|----------|-------------|
| `view_partner_form_inherit_contact_roles` | form | `base.view_partner_form` | `contact_types`, `contact_subtypes`, `show_subtypes` toggle, Creator fields group, Contact fields group |
| `view_partner_list_inherit_contact_roles` | list | `base.view_partner_list` | `is_creator`, `is_contact` columns |
| `view_partner_tree_artists` | list | primary | Creator-specific list: Name, Email, Phone (default); Nationality, Birth Date, Website, Contact Types (optional); `creator_subtypes` (default, visible) |
| `view_partner_tree_contacts` | list | primary | Contact-specific list: Name, Email, Phone (default); Contact Types (optional); `contact_role_subtypes` (default, visible) |
| `view_partner_tree_collectors` | list | primary | Collector-specific list: Name, Email, Phone (default); Preferred Artists, Contact Types (optional); `contact_role_subtypes` (default, visible) |
| `action_sor_contact_type` | act_window | — | Window action for `sor.contact.type` list |
| `view_sor_contact_type_list` | list | — | Contact type list view |
| `view_sor_contact_type_form` | form | — | Contact type form view |

**View binding records** (`ir.actions.act_window.view`): Explicit bindings wire `view_partner_tree_artists` to both `action_sor_creators` (top-level Creators menu) and `action_partner_artists` (sub-menu). `view_partner_tree_contacts` is wired to `action_sor_contacts` (top-level Contacts menu). Without these bindings, Odoo falls back to the default `res.partner` list view — setting `view_id` directly on the action record does not work in Odoo 19.

---

## Module file structure

```
sor_contact_roles/
├── __manifest__.py              # version 19.0.1.5.0; post_init_hook
├── __init__.py                  # imports models, hooks
├── hooks.py                     # post_init_hook; _migrate_contact_types
├── models/
│   ├── __init__.py
│   ├── sor_contact_type.py      # sor.contact.type model
│   ├── res_partner.py           # res.partner extension
│   └── sor_contact_social_media.py  # sor.contact.social.media model
├── views/
│   ├── res_partner_views.xml    # Partner form/list views
│   ├── sor_contact_type_views.xml  # Contact type list/form views
│   └── sor_contact_type_menus.xml  # Developer menu (under Settings → Technical → SOR)
├── security/
│   ├── ir.model.access.csv
│   └── sor_contact_roles_security.xml  # Multi-company ir.rule
├── data/
│   └── sor_contact_type_data.xml  # Seeded types (noupdate="1")
├── migrations/
│   ├── 19.0.1.2.0/pre-migrate.py   # Delete stale views before field-rename load
│   ├── 19.0.1.3.0/post-migrate.py  # Customer → Contact rename
│   ├── 19.0.1.4.0/post-migrate.py  # Generalise migration loop
│   └── 19.0.1.5.0/post-migrate.py  # Fix stale M2M rows via raw SQL
├── i18n/
│   └── sor_contact_roles.pot
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical files

| File | Purpose |
|------|---------|
| `__manifest__.py` | Module version (must match migrations/ directory); `post_init_hook` |
| `hooks.py` | `_migrate_contact_types()` — called both at install (post_init_hook) and upgrade (migration scripts) |
| `models/res_partner.py` | All `res.partner` extensions: fields, computed flags, write/create overrides |
| `data/sor_contact_type_data.xml` | Canonical type registry — `noupdate="1"` |
| `migrations/19.0.1.5.0/post-migrate.py` | Latest migration — raw SQL M2M fix |

---

## Composability boundary

| Feature | sor_contact_roles only | With sor_bidding | With sor_locations_external | With sor_artwork |
|---------|----------------------|-----------------|---------------------------|-----------------|
| Creator type + Artist | ✅ | ✅ | ✅ | ✅ |
| Contact type + sub-types | ✅ | ✅ | ✅ | ✅ |
| `is_bidder` flag | ✅ (field present) | ✅ (auto-assigned) | ✅ | ✅ |
| `is_contact` flag | ✅ | ✅ | ✅ | ✅ |
| External Locations smart button | ❌ | ❌ | ✅ | ❌ |
| Artist Studio locations | ❌ | ❌ | ❌ | ❌ (needs sor_locations_artist_studios) |
| `artwork_ids` on creator | ❌ | ❌ | ❌ | ✅ (violation — tracked) |

---

## Special concerns

### Many2many domain applied at ORM search time

The `domain` on `contact_types` (`[('parent_type_id', '=', False)]`) and `contact_subtypes` (`[('parent_type_id', '!=', False)]`) is enforced by Odoo at ORM search time via a JOIN, not just in the UI. This means:

- `env['res.partner'].search([('contact_types', 'in', [bidder_id])])` returns 0 after Bidder gains a `parent_type_id`, because the JOIN filters it out.
- Migration hooks that search for partners with stale M2M assignments must use raw SQL (`env.cr.execute`) to bypass this domain.
- After raw SQL writes to M2M tables, call `env.flush_all()` and `records.invalidate_recordset(['contact_types', 'contact_subtypes'])` before resuming ORM operations.

### `ir_model_data.noupdate` and migration ordering

Contact type records with `noupdate=False` (no `<data noupdate="1">` wrapper) have their fields written by the data file on every upgrade — **before** post-migrate scripts run. This means any migration logic that guards on `if not record.parent_type_id` will always see the field already set by the data file. The correct pattern is to not guard on field state; instead, use raw SQL to detect and fix stale M2M rows unconditionally (the fix is idempotent when no stale rows exist).

### `post_migrate` is not a valid manifest key

Odoo only recognises `post_init_hook` and `uninstall_hook` as manifest hook keys. `post_migrate` is silently ignored. For logic that must run on every upgrade, use migration scripts in `migrations/<version>/post-migrate.py`. Call the same function from both the manifest `post_init_hook` (install) and the migration script (upgrade).

---

## Running the tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  --http-port=8070 \
  -d odoo --test-enable --stop-after-init -u sor_contact_roles
```

Check results in `/var/log/odoo/odoo-server.log` — Odoo writes all output to the log file, not stdout.

---

## Story reference

`.backlog/current/Contact Roles Enhancements/stories/02_Contact-Type-Hierarchy-Restructure.md`
