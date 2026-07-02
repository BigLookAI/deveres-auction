# Technical Architecture: sor_base

## Overview

`sor_base` is a manifest-only meta-module in the SOR stack. It serves as the canonical installation entry point for SOR horizontal infrastructure — a single installable unit that guarantees both `sor_asset_paradigm` and `sor_business_model` are present before any vertical module is installed.

```
sor_asset_paradigm    sor_business_model
         \                    /
          \                  /
               sor_base          (auto_install=False, application=False)
                   |
               sor_artwork  (and all future verticals)
```

---

## Module Pattern

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `False` | Explicitly installed by the administrator as the first deployment step; must not auto-activate as a side effect of installing individual horizontals |
| `application` | `False` | Not a top-level App — a technical infrastructure module |
| `category` | `'Hidden/Technical'` | Excluded from business category listings; findable via search |
| `depends` | `['sor_asset_paradigm', 'sor_business_model']` | Pulls in the full horizontal mechanism stack |
| `summary` | present | Unlike bridge modules (which deliberately omit it), sor_base needs a summary so administrators can find and identify it in the Apps screen |

---

## Architecture Decisions

**Why a separate meta-module rather than direct cross-dependencies?**

The alternative would be for `sor_artwork` (and every other vertical) to depend directly on `sor_asset_paradigm` and `sor_business_model`. This works for the current pair of horizontals but creates a maintenance problem: adding or removing a horizontal mechanism module requires updating every vertical manifest.

`sor_base` centralises the horizontal dependency declaration. All verticals depend on `sor_base`; only `sor_base` depends on the horizontals. Adding a new horizontal requires changing one manifest.

**Why `auto_install: False`?**

Auto-install modules activate automatically when all their declared dependencies are satisfied. For `sor_base`, this would mean it installs the moment `sor_asset_paradigm` and `sor_business_model` are both present — but in a phased deployment those modules might be installed as prerequisites for something else entirely. `auto_install: False` makes the installation intentional and controllable by the administrator.

**Why no models, views, or logic?**

`sor_base` is a dependency declaration, not a feature. Its stability as a foundation module depends on having no logic that could change. If shared infrastructure logic is ever needed across verticals in the future, a new dedicated module with a clear feature boundary should be created — not added to `sor_base`.

---

## Models

None. `sor_base` defines no models.

---

## Views

None. `sor_base` defines no views or menu items.

---

## Module File Structure

```
sor_base/
├── __init__.py          # Empty Python package file
├── __manifest__.py      # Module manifest (dependencies and flags only)
├── doc/
│   ├── KNOWLEDGE_BASE.md         # User-facing reference
│   └── TECHNICAL_ARCHITECTURE.md # This file
└── tests/
    ├── __init__.py      # Imports test_sor_base
    └── test_sor_base.py # Installation and dependency cascade tests
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | The only substantive file — declares all dependencies and module flags |
| `tests/test_sor_base.py` | Verifies module installation, dependency cascade, and bridge activation |

---

## Composability Boundary

| Installed modules | sor_base present | Horizontals present | Bridge modules |
|-------------------|-----------------|---------------------|----------------|
| Neither horizontal | ✗ | ✗ | ✗ |
| Both horizontals only | only if explicitly installed | ✓ | ✗ |
| `sor_base` installed | ✓ | ✓ | ✗ (until a vertical is added) |
| `sor_base` + `sor_artwork` | ✓ | ✓ | ✓ (auto-install on both parents present) |

---

## Special Concerns

**Convention for future verticals:** Every future SOR vertical module (`sor_antiques`, `sor_jewellery`, etc.) must declare `sor_base` in its `depends` list — not the individual horizontal modules directly. This is an enforced convention, not an Odoo framework requirement, documented here for continuity.

**`sor_artwork`'s direct `sor_contact_roles` dependency:** `sor_artwork` currently has a direct dependency on `sor_contact_roles` in its manifest. This is a known composability violation — contact role features should be delivered via a bridge module (`sor_artwork_contact_roles`), not via a base module dependency. It is tracked as a spike and annotated with a comment in `sor_artwork/__manifest__.py`. This violation is independent of `sor_base`; `sor_base` covers only the horizontal mechanism modules.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init \
  -u sor_base --http-port=8072
```

---

## Story Reference

Parent story: `.backlog/current/Module Foundations/stories/05_sor-base-Scaffold.md`
Sprint: Module Foundations
