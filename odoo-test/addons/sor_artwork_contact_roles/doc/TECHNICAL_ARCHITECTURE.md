# Technical Architecture: sor_artwork_contact_roles

## Overview

`sor_artwork_contact_roles` is a **bridge module** that links `sor_artwork` and `sor_contact_roles`. It resolves the known composability violation in `sor_artwork`'s manifest — the direct dependency on `sor_contact_roles` that existed before this bridge was introduced — and delivers the intersection features that only make sense when both parent modules are installed simultaneously.

```
sor_artwork          sor_contact_roles
      \                    /
       \                  /
   sor_artwork_contact_roles    (auto_install=True, application=False)
```

Neither parent module is modified by this bridge. The bridge activates automatically when both parents are installed.

**What this bridge delivers:**
1. Domain restriction on `product.template.creator_id` — limits the creator picker to `is_creator = True` contacts
2. `artwork_ids`, `artwork_count`, `action_view_artworks()`, and `unlink()` guard on `res.partner`
3. Artworks smart button and Artworks tab on the partner form view

**Story reference:** `.backlog/current/Contact Roles Enhancements/`

---

## Module Pattern

```python
'depends': ['sor_artwork', 'sor_contact_roles'],
'auto_install': True,
'application': False,
'category': 'Hidden/Technical',
```

- `auto_install: True` — Odoo installs the bridge automatically when both `sor_artwork` and `sor_contact_roles` are present.
- `application: False` — Not shown as a top-level App.
- `category: 'Hidden/Technical'` — Excluded from business category listings.

**Why a bridge?** The `creator_id` domain restriction and the Artworks relationship on `res.partner` both reference `is_creator` from `sor_contact_roles`. Neither feature makes sense without `sor_contact_roles` installed, but neither belongs in `sor_artwork` (which must be installable without contact role assignments). The bridge is the correct composition point.

**No post_init_hook, no configuration:** Unlike paradigm bridges, this bridge requires no setup on install. The domain patch applies immediately; the partner fields appear immediately. There are no rule records, no settings toggles, and no sequences to seed.

---

## Architecture Decisions

### Domain patch on `creator_id` — two mechanisms (view + ORM)

The `creator_id` domain restriction is applied in two layers:

1. **View layer** (`views/sor_artwork_contact_roles_views.xml`): XPath patches the `domain` attribute on the `creator_id` field widget in the artwork form view. This filters the search picker in the UI.
2. **ORM layer** (`models/sor_art_product.py`): The `creator_id` field is re-declared with `domain="[('is_creator', '=', True)]"`. This sets the field-level domain on the comodel, which Odoo applies at ORM search time via a JOIN on `res.partner`.

Both are necessary. The view patch controls what the user sees in the picker; the ORM field domain enforces the constraint when records are fetched programmatically.

### Company-scoped `action_view_artworks()`

The smart button action domain includes an explicit company filter:

```python
'|',
('company_id', '=', self.env.company.id),
('company_id', '=', False),
```

This is required by the SOR Definition of Done: any smart button rendered on a `res.partner` form must filter results to `env.company`. The `|`/`False` clause includes shared artworks (globally scoped products with no company) alongside company-specific artworks.

### `artwork_count` is `store=False`

The count is computed from `artwork_ids`. Because `artwork_ids` is a One2many over `product.template`, and `product.template` records can be archived or reassigned, a stored count would go stale under normal operations. `store=False` ensures the count is always fresh when the partner form is loaded.

### `unlink()` guard references `is_creator` from the parent module

The deletion guard calls `partner.is_creator` — a field defined in `sor_contact_roles`. This reference is valid inside the bridge because the bridge explicitly depends on `sor_contact_roles`. A base module must never reference another base module's fields directly; the bridge is the correct place for such cross-module references.

---

## Models

### `product.template` (extended — `models/sor_art_product.py`)

| Field / Method | Type | Purpose |
|----------------|------|---------|
| `creator_id` | Many2one (domain patched) | Domain `[('is_creator', '=', True)]` applied at ORM level. Without bridge: accepts any partner. With bridge: restricted to Creator contacts only. |
| `_check_creator_is_valid` | `@api.constrains('creator_id')` | Validates that the selected creator has `is_creator` or `is_artist` set to True. Only fires for artwork products. Raises `ValidationError` if neither flag is True. **Known limitation — see Special Concerns.** |

### `res.partner` (extended — `models/res_partner.py`)

| Field / Method | Type | Purpose |
|----------------|------|---------|
| `artwork_ids` | One2many → `product.template` (inverse: `creator_id`) | All artworks attributed to this creator. Domain `[('product_type', '=', 'artwork')]`. |
| `artwork_count` | Integer, `store=False`, computed | Count of `artwork_ids`. Used by smart button stat info widget. |
| `_compute_artwork_count` | computed | Sets `artwork_count = len(partner.artwork_ids)` for each partner in the recordset. |
| `action_view_artworks` | `() → dict` | Returns `ir.actions.act_window` for `product.template`. Domain includes `creator_id = self.id`, `product_type = 'artwork'`, and company filter. Used by the smart button. |
| `unlink` | override | Raises `ValidationError` if `partner.is_creator` and `partner.artwork_ids` — prevents deleting a creator with attributed artworks. |

---

## Views

### `view_product_template_form_creator_domain`

| Property | Value |
|----------|-------|
| Type | Form (non-primary inherit) |
| Inherits | `sor_artwork.view_product_template_form_artwork` |
| What it does | XPath `//field[@name='creator_id']` + `position="attributes"` — sets `domain="[('is_creator', '=', True)]"` on the creator field widget in the artwork form |
| Why | Without this patch, the artwork form picker shows all partners. The bridge applies the role restriction at view time. |

### `view_partner_form_artworks`

| Property | Value |
|----------|-------|
| Type | Form (non-primary inherit) |
| Inherits | `base.view_partner_form` |
| What it does | Two XPath patches: (1) inserts Artworks smart button into `//div[@name='button_box']`; (2) inserts Artworks tab before `page[@name='contact_addresses']` and removes the `autofocus` attribute from the Contacts tab so Artworks becomes the default tab for Creator contacts |
| Smart button visibility | `invisible="not is_creator or artwork_count == 0"` — hidden for non-creators and for creators with no artworks |
| Artworks tab visibility | `invisible="not is_creator"` — tab is hidden for all non-Creator contacts |
| Artworks tab content | Inline list of `artwork_ids` with columns: Name, Type (badge), Year, Medium, Width, Height, Active toggle |

---

## Module File Structure

```
sor_artwork_contact_roles/
├── __manifest__.py                          # depends=['sor_artwork','sor_contact_roles']; auto_install=True
├── __init__.py                              # imports models
├── models/
│   ├── __init__.py
│   ├── sor_art_product.py                   # product.template: creator_id domain + _check_creator_is_valid
│   └── res_partner.py                       # res.partner: artwork_ids, artwork_count, action, unlink guard
├── views/
│   └── sor_artwork_contact_roles_views.xml  # Creator domain patch + partner Artworks smart button + tab
├── security/
│   └── ir.model.access.csv                  # Header only — no new models
├── tests/
│   ├── __init__.py
│   └── test_sor_artwork_contact_roles.py    # 3 tests: fields present, count, action domain
└── doc/
    ├── KNOWLEDGE_BASE.md
    └── TECHNICAL_ARCHITECTURE.md
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | `auto_install=True`, `depends=['sor_artwork','sor_contact_roles']` — the composability declaration |
| `models/sor_art_product.py` | Applies `creator_id` domain at ORM level; `_check_creator_is_valid` constraint |
| `models/res_partner.py` | `artwork_ids`, `artwork_count`, company-scoped `action_view_artworks()`, `unlink()` guard |
| `views/sor_artwork_contact_roles_views.xml` | View domain patch on artwork form; Artworks smart button + tab on partner form |
| `tests/test_sor_artwork_contact_roles.py` | 3 automated tests verifying fields present, count, and action company scoping |

---

## Composability Boundary

| Feature | `sor_artwork` only | `sor_contact_roles` only | Both installed (bridge active) |
|---------|-------------------|--------------------------|-------------------------------|
| `creator_id` on artwork | ✅ present (accepts any partner) | ✗ absent | ✅ present + domain restricted to `is_creator = True` |
| `creator_id` picker domain restricted | ✗ no restriction | ✗ absent | ✅ restricted to Creator contacts |
| `artwork_ids` on `res.partner` | ✗ absent | ✗ absent | ✅ present |
| `artwork_count` on `res.partner` | ✗ absent | ✗ absent | ✅ present |
| Artworks smart button on partner form | ✗ absent | ✗ absent | ✅ present (visible to Creator contacts with artworks) |
| Artworks tab on partner form | ✗ absent | ✗ absent | ✅ present (visible for Creator contacts) |
| Creator deletion guard | ✗ absent | ✗ absent | ✅ active |

---

## Special Concerns

### `_check_creator_is_valid` constraint logic — known limitation (Gap 02)

The constraint body is:
```python
if not record.creator_id.is_creator and not record.creator_id.is_artist:
    raise ValidationError(...)
```

The condition checks that **neither** `is_creator` nor `is_artist` is True before raising. In practice this is equivalent to `if not is_creator` — because `is_artist` implies `is_creator` (Artist is a Creator sub-type; `is_creator` is True whenever `is_artist` is True). However, the redundancy creates a subtle theoretical gap: if a future change were to make `is_artist` True independently of `is_creator`, a partner that is `is_artist=True, is_creator=False` would pass the constraint silently.

Additionally, because `is_creator` is a `store=True` computed field, a race condition exists when Creator type is assigned in the same ORM transaction as the artwork's `creator_id`: the constraint may fire before the stored computed value is recalculated, causing a false positive `ValidationError`. This is tracked as Gap 02 in the sprint's Sprint Findings and is deferred to a future sprint.

**Mitigation at present:** In normal gallery workflow, contacts are assigned Creator type long before they are attributed as an artwork creator. The constraint fires at artwork save time — at which point the `is_creator` flag has already been stored and is correct.

### `artwork_ids` — domain filter on the field declaration

`artwork_ids` declares `domain=[('product_type', '=', 'artwork')]`. This domain is applied at ORM search time for all reads of the field — archived artworks (`active=False`) are included by default because Odoo only excludes `active=False` records when `active_test=True` is in the context. The Artworks tab list does not need to show archived artworks in normal use; the `active` toggle column in the tab is the mechanism for archiving works directly.

### No `tests/test_placeholder.py` — stub replaced

At Show & Tell, the placeholder stub `tests/test_placeholder.py` was replaced with `tests/test_sor_artwork_contact_roles.py`. The `tests/__init__.py` was updated from empty to `from . import test_sor_artwork_contact_roles`.

### View autofocus manipulation

The Artworks tab is inserted before `page[@name='contact_addresses']` (Contacts tab) and given `autofocus="autofocus"`. Simultaneously, the Contacts tab has its `autofocus` attribute removed via a separate XPath. Without this two-step approach, both tabs would attempt to claim autofocus and the browser's native resolution would determine which wins — making the result unpredictable.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_artwork_contact_roles
```

Tests require an existing artwork with a `creator_id` set in the database (`setUpClass` searches for one rather than creating). If the database has no artwork with a creator, tests raise `RuntimeError` and are skipped.

Check results:
```bash
docker exec odoo-app tail -50 /var/log/odoo/odoo-server.log | grep -E "FAIL|ERROR|OK|stats"
```

---

## Story Reference

`.backlog/current/Contact Roles Enhancements/`
