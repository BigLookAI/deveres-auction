# SOR Lotting — Technical Architecture

## Overview

`sor_lotting` is a horizontal SOR base module that provides the `sor.lot` model — the central catalogue entry for an auction sale. It sits at the root of the Auction Foundations track (Track D), providing the lot record that auction lot catalogues, buyer registrations, and sale results will extend in subsequent D2 bridge modules.

The module is event-agnostic at the base level: it knows nothing about which auction a lot belongs to. The event association (`event_id → sor.event`) is added by `sor_events_auction` (D2) via bridge inheritance.

**Dependency:** `product`

---

## Module Pattern

```python
{
    'depends': ['product'],
    'auto_install': False,
    'application': False,
    'category': 'Hidden/Technical',
    'post_init_hook': 'post_init_hook',
    'post_migrate': 'post_migrate',
}
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `False` | Installed explicitly — standalone base module, not a bridge |
| `application` | `False` | Not a top-level app; complex navigation comes from D2 bridges |
| `category` | `Hidden/Technical` | Infrastructure; not surfaced in the App Store |
| `depends: product` | Required | `product.template` is the reference model for `product_id`; `Monetary` field type and currency infrastructure come from the product stack |
| `post_init_hook` | `post_init_hook` | Creates per-company `ir.sequence` records for all companies existing at install time |
| `post_migrate` | `post_migrate` | Registered for future migration use; currently a no-op |

---

## Architecture Decisions

**`lot_reference` is the primary system identifier; `lot_number` is the auctioneer's catalogue number**
Two identification concepts exist for lots: a system reference for record management and a catalogue number for the sale catalogue. These have different lifecycles. The system reference (`lot_reference`) is required and assigned at creation — it uniquely identifies the record regardless of which auction or catalogue it appears in. The catalogue number (`lot_number`) is an integer assigned by the auctioneer when building the sale catalogue — it may be assigned later (at cataloguing time) or not at all. Separating them prevents a dependency on the auctioneer's workflow before a lot can be created and stored in the system.

**`lot_number` is optional Integer**
Lot numbers in auction catalogues are always numeric (1, 2, 3 … 450). Defining as Integer enables direct numeric ordering without cast functions and prevents non-numeric entry at the ORM level. The field is optional (`required=False`) because catalogue sequencing is a later workflow step — lots exist in the system before they are assigned their catalogue position. Split lots use `lot_suffix` (Char 3) to carry alphabetic suffixes (e.g. lot 15A, 15B).

**`lot_reference` format: `LOT/YYYY/NNNNN` via per-company `ir.sequence`**
The reference is system-generated at record creation using `ir.sequence` with code `sor.lot`. The year-prefix format is the SOR convention for operational identifiers (matching `sor_legal_agreement`). Per-company sequences ensure SO Fine Art and SETU maintain independent counters starting from `LOT/2026/00001`. The `with_company(company)` call in `create()` ensures the counter used belongs to the record's company, not the user's session company — these can differ when a multi-company user creates records on behalf of another company.

**`lot_number` is editable in Draft state only**
The form view sets `lot_number` to `readonly="state != 'draft'"`. Once a lot is Catalogued, the catalogue number is part of the printed sale catalogue and must not change. Restricting edits at Catalogued prevents inadvertent re-sequencing after the catalogue has been issued.

**Action buttons added at D1 (not deferred to D2)**
The D1 specification originally deferred action buttons to D2 on the grounds that meaningful lifecycle control required auction event context. This was revised during D1 Completions (Story 02): the core state machine (Draft → Catalogued → Live → Sold/Passed, with Withdraw) is fully defined at the base module level and requires no event context to function correctly. Scaffolding button-driven workflow in D2 would have delayed a complete and testable state machine for no architectural benefit. D2 bridges extend the workflow (e.g. post-sale offer handling) but do not own the base transitions.

**`break_even_value` is `store=False`**
Break-even value is a derived financial quantity. In the base module it equals `reserve_price`. In `sor_commercial_auction_house` (future sprint) it becomes `reserve_price + fee_amount`. Storing the value would require triggers to recompute when fees are changed. `store=False` keeps the computation always current without invalidation logic and imposes no storage cost.

**`currency_id` is `store=True`**
`currency_id` is a related field from `company_id.currency_id` with `store=True`. Monetary fields in Odoo require a `currency_field` attribute pointing to a persisted currency field; a non-stored related field would fail during ORM write operations involving grouping and aggregation. Storing it also avoids an extra join for report queries that need to display currency symbols.

**`currency_id` uses `optional="hide"` in the list view**
The list view needs `currency_id` present in the field list for the Monetary widget to resolve currency per row. Using `column_invisible="1"` or `invisible="1"` removes the DOM element and breaks Monetary widget resolution. `optional="hide"` hides the column by default (preserving the field in the arch) while keeping the DOM data available.

**`_order = 'lot_reference asc'`**
The primary sort key is `lot_reference` rather than `lot_number`, because `lot_number` is optional and cannot serve as a reliable primary sort key. Lots without a catalogue number assigned would sort ambiguously if `lot_number` were the primary key. `lot_reference` is always assigned at creation and is unique per company, making it a reliable default sort.

**`product_id` domain: `is_storable = True`**
Lots represent physical objects going to auction. Service products and consumables-without-tracking have no meaningful place in an auction catalogue. The domain restricts selection to storable products to prevent catalogue data entry errors.

**No `mail.thread` at the base level**
Unlike `sor.event`, lot records do not inherit `mail.thread`. Collaborative annotation (bidder notes, condition reports) is added by domain bridge modules when the full auction context is present. The base lot record is intentionally lightweight.

---

## Models

### sor.lot

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `lot_reference` | Char | Yes | `'New Lot'` → sequence on create | System-generated `LOT/YYYY/NNNNN`; `readonly=True`; `copy=False`; `index=True` |
| `lot_number` | Integer | No | — | Optional catalogue number; editable in draft/catalogued only |
| `lot_suffix` | Char(3) | No | — | Optional alpha suffix for split lots |
| `product_id` | Many2one → `product.template` | Yes | — | Domain: `is_storable=True` |
| `company_id` | Many2one → `res.company` | Yes | `env.company` | `_check_company_auto = True` |
| `currency_id` | Many2one → `res.currency` | — | — | Related: `company_id.currency_id`; `store=True` |
| `estimate_low` | Monetary | No | — | `currency_field='currency_id'` |
| `estimate_high` | Monetary | No | — | `currency_field='currency_id'` |
| `reserve_price` | Monetary | No | — | `currency_field='currency_id'` |
| `no_reserve` | Boolean | No | `False` | Independent of `reserve_price`; both can coexist |
| `starting_bid` | Monetary | No | — | `currency_field='currency_id'` |
| `hammer_price` | Monetary | No | — | `currency_field='currency_id'` |
| `break_even_value` | Monetary | — | — | Computed; `store=False`; `@api.depends('reserve_price')` |
| `state` | Selection | Yes | `'draft'` | Six values; see state table below; `copy=False` |
| `internal_notes` | Html | No | — | Rich-text; rendered as editor directly in page (not in group) |

**Model attributes:**
- `_name = 'sor.lot'`
- `_rec_name = 'lot_reference'` — `lot_reference` is the display name used in breadcrumbs, Many2one dropdowns, and window titles; raw `id` is not shown to users
- `_order = 'lot_reference asc'`
- `_check_company_auto = True`

**Constraint:**
```python
_estimate_check = models.Constraint(
    'CHECK(estimate_low IS NULL OR estimate_high IS NULL OR estimate_low <= estimate_high)',
    'Low estimate must not exceed high estimate.',
)
```

**State values:**

| Value | Label |
|-------|-------|
| `draft` | Draft |
| `catalogued` | Catalogued |
| `live` | Live |
| `sold` | Sold |
| `passed` | Passed |
| `withdrawn` | Withdrawn |

**Methods:**

| Method | Decorator | Return | Guard | Notes |
|--------|-----------|--------|-------|-------|
| `create` | `@api.model_create_multi` | recordset | — | Assigns `lot_reference` from `ir.sequence` with `with_company(company)` |
| `unlink` | — | bool | Raises `UserError` if `state != 'draft'` | Deletion guard |
| `_compute_break_even_value` | `@api.depends('reserve_price')` | void | — | Sets `break_even_value = reserve_price or 0.0` |
| `action_catalogue` | — | void | `state == 'draft'` | Transitions to `catalogued` |
| `action_go_live` | — | void | `state == 'catalogued'` | Transitions to `live` |
| `action_mark_sold` | — | void | `state == 'live'` | Transitions to `sold` |
| `action_mark_passed` | — | void | `state == 'live'` | Transitions to `passed` |
| `action_withdraw` | — | void | `state in ('draft', 'catalogued')` | Transitions to `withdrawn` |
| `action_open_product` | — | dict (act_window) | `ensure_one()` | Opens product in modal dialog (`target: 'new'`) |

### models/res_company.py

Extends `res.company` with a `create` override that creates an `ir.sequence` (code `sor.lot`, prefix `LOT/%(year)s/`, padding 5) for each newly created company. Ensures every company has an independent lot reference counter from day one.

### models/product_template.py

Extends `product.template` to override `_compute_display_name`. When the context key `suppress_product_code` is set (used by the `product_id` field on the lot form), the display name renders as the product name only, without the internal reference prefix. This prevents the form and list from showing `[REF] Product Name` in the lot context where the reference code is irrelevant.

---

## Views

### sor_lot_view_form (primary)

Form view with:
- `<header>`: Five action buttons — Catalogue (visible when draft), Go Live (visible when catalogued), Mark Sold (visible when live, primary), Mark Passed (visible when live), Withdraw (visible when draft or catalogued). `state` statusbar widget with `statusbar_visible="draft,catalogued,live,sold,passed,withdrawn"`.
- `<sheet>`: Two groups — Identification (lot_reference readonly, lot_number with state-based readonly, lot_suffix, product_id with modal open button, company_id with multi-company guard) and Financial (currency_id invisible, estimates, reserve, no_reserve, starting_bid, hammer_price, break_even_value read-only).
- `<notebook>`: Internal Notes page with `fields.Html` rendered directly in the page (not in a group) to enable the rich text editor.
- D2 injection comment marks where `auction_id` and fee tabs are added by the bridge.

### sor_lot_view_list (primary)

List view with columns: currency_id (`optional="hide"`), lot_reference, lot_number, lot_suffix, product_id, state, estimate_low, estimate_high, reserve_price.

### sor_lot_view_search (primary)

Search view with:
- Field search: lot_reference, lot_number (exact integer match via `filter_domain`), product_id
- Individual state filters: Draft, Catalogued, Live, Sold, Passed, Withdrawn

### Window action (sor_lot_action)

Mode: `list,form`. Domain: `[('company_id', '=', allowed_company_ids[0])]`.

---

## Module File Structure

```
sor_lotting/
├── __init__.py                     imports models package; imports post_init_hook, post_migrate from hooks
├── __manifest__.py                 module metadata; post_init_hook and post_migrate registered
├── hooks.py                        post_init_hook (per-company sequence creation); post_migrate (no-op)
├── data/
│   └── sor_lot_sequence.xml        ir.sequence for base.main_company (noupdate="1")
├── doc/
│   ├── KNOWLEDGE_BASE.md           user-facing module documentation
│   └── TECHNICAL_ARCHITECTURE.md  this file
├── i18n/
│   └── sor_lotting.pot             translatable string catalogue
├── models/
│   ├── __init__.py                 imports product_template, res_company, sor_lot
│   ├── product_template.py         suppress_product_code display name override
│   ├── res_company.py              create override — generates ir.sequence for new companies
│   └── sor_lot.py                  sor.lot model, state machine, sequence assignment, deletion guard
├── security/
│   ├── ir.model.access.csv         read/write/create/delete for base.group_user
│   └── sor_lotting_rules.xml       multi-company ir.rule (noupdate="1")
├── tests/
│   ├── __init__.py                 wires test_sor_lotting into the test runner
│   └── test_sor_lotting.py         full test suite (module install, sequence, state machine, guards)
└── views/
    └── sor_lot_views.xml           form, list, search views; window action; user menu
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/sor_lot.py` | Core model, fields, constraint, state machine, sequence assignment, deletion guard |
| `models/res_company.py` | Generates `ir.sequence` for new companies — without this, new companies have no lot reference counter |
| `hooks.py` | Generates `ir.sequence` for all companies existing at install time |
| `data/sor_lot_sequence.xml` | Seeds the sequence for `base.main_company` — the install-time starting point |
| `views/sor_lot_views.xml` | All views, window action, and user navigation menu |
| `security/sor_lotting_rules.xml` | Multi-company record rule — without this, `company_id` is just a label |
| `security/ir.model.access.csv` | Without this, no user can read or write lot records |

---

## Composability Boundary

| Modules installed | Behaviour |
|-------------------|-----------|
| `sor_lotting` only | `sor.lot` model with full field set, per-company sequence, six-state lifecycle with action buttons, estimate constraint. User-facing Lots menu. No event link. |
| `sor_lotting` + `sor_events` | No change to either module. Independent horizontals — no bridge yet. |
| `sor_lotting` + `sor_events_auction` (D2) | Bridge auto-installs. Lots gain `event_id` → `sor.event`. Auction-contextual Lots access via Auctions menu. |
| `sor_lotting` + `sor_commercial_auction_house` (future) | Bridge adds fee structure. `break_even_value` computed override includes buyer's premium. |

---

## Special Concerns

**SQL constraint syntax (Odoo 19)**
`_sql_constraints` is silently ignored in Odoo 19. The estimate check uses `models.Constraint(definition, message)` as a class-level attribute. The constraint name on the database table is derived from the attribute name: `sor_lot_estimate_check`.

**`currency_id` in list view — `optional="hide"` workaround**
Monetary widgets require the `currency_field` to be present in the list arch for per-row currency resolution. Three approaches were evaluated:
- `column_invisible="1"` — removes the element from the DOM; Monetary widget resolution breaks.
- `invisible="1"` — keeps data in DOM; column header still renders visibly.
- `optional="hide"` — hides column by default; column data remains in DOM; Monetary widget resolves correctly. **This is the current approach.**

Side effect: grouping by `state` may append `currency_id` value to group headers in some Odoo 19 versions. Deferred to D2 when the view architecture changes.

**Per-company sequence bootstrap — three-step pattern**
The sequence infrastructure follows the three-step pattern established in `sor_multi_company.md`:
1. `data/sor_lot_sequence.xml` seeds the sequence for `base.main_company` (with `noupdate="1"`).
2. `hooks.py` `post_init_hook` creates sequences for all other existing companies at install time.
3. `models/res_company.py` `create` override creates sequences for any company added after install.

The `with_company(company)` call in `sor_lot.create()` ensures the correct company's counter is incremented when a multi-company user creates a lot on behalf of a different company than their current session company.

**`lot_number` readonly rule in the form**
`lot_number` uses `readonly="state not in ('draft', 'catalogued')"` — an inline Owl expression, not a separate `attrs` dict. This is the Odoo 19 form rendering pattern. The field becomes read-only from `live` onwards to preserve catalogue integrity once bidding opens.

**Multi-company record rule**
The rule in `security/sor_lotting_rules.xml` uses `noupdate="1"`. Domain: `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`. The `company_id = False` clause is a safety guard for records where `company_id` was not set — in practice, `required=True` prevents this.

**`_check_company_auto`**
Set to `True` on `sor.lot`. `product_id → product.template` does not carry `check_company=True` because products in SOR are company-agnostic objects (an artwork product is shared across companies; the lot that references it is company-scoped). This matches the established SOR exception for product references documented in `sor_multi_company.md`.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  --http-port=8099 \
  -d odoo --test-enable --stop-after-init \
  --test-tags='sor_lotting' \
  -u sor_lotting
```

---

## Story Reference

- Story 03: `.backlog/previous/07 Auction Foundations/stories/03_Lotting-Base-Module.md`
- Story 04: `.backlog/previous/07 Auction Foundations/stories/04_Lotting-Views-and-Menus.md`
- D1 Completions Story 02: `.backlog/previous/D1 Completions/stories/02_Lotting-State-Machine-and-Sequence.md`
