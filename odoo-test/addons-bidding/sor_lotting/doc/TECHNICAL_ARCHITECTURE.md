# SOR Lotting — Technical Architecture

## Overview

`sor_lotting` is a horizontal SOR base module that provides the `sor.lot` model — the central catalogue entry for an auction sale. It sits at the root of the Auction Foundations track (Track D), providing the lot record that auction lot catalogues, buyer registrations, and sale results will extend in subsequent D2 bridge modules.

The module is event-agnostic at the base level: it knows nothing about which auction a lot belongs to. The event association (`event_id → sor.event`) is added by `sor_events_auction` (D2) via bridge inheritance.

**Dependency:** `product`

---

## Module Pattern

```python
{
    'depends': ['product', 'mail'],
    'auto_install': False,
    'application': False,
    'category': 'Hidden/Technical',
    'post_init_hook': 'post_init_hook',
}
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `False` | Installed explicitly — standalone base module, not a bridge |
| `application` | `False` | Not a top-level app; complex navigation comes from D2 bridges |
| `category` | `Hidden/Technical` | Infrastructure; not surfaced in the App Store |
| `depends: product` | Required | `product.template` is the reference model for `product_id`; `Monetary` field type and currency infrastructure come from the product stack |
| `depends: mail` | Required | `mail.thread` and `mail.activity.mixin` are inherited by `sor.lot` for chatter and state tracking (added Sprint 24) |
| `post_init_hook` | `post_init_hook` | Creates per-company `ir.sequence` records for all companies existing at install time |

---

## Architecture Decisions

**`lot_reference` is the primary system identifier; `lot_number` is the auctioneer's catalogue number**
Two identification concepts exist for lots: a system reference for record management and a catalogue number for the sale catalogue. These have different lifecycles. The system reference (`lot_reference`) is required and assigned at creation — it uniquely identifies the record regardless of which auction or catalogue it appears in. The catalogue number (`lot_number`) is an integer assigned by the auctioneer when building the sale catalogue — it may be assigned later (at cataloguing time) or not at all. Separating them prevents a dependency on the auctioneer's workflow before a lot can be created and stored in the system.

**`lot_number` is `fields.Char(size=10)`, not Integer (Sprint 24 change)**
Initially implemented as `fields.Integer`. Changed to `fields.Char(size=10)` in Sprint 24 (BUG-S02-F01). The Integer widget in Odoo 19 applies locale-specific thousand-separator formatting at render time — e.g. lot number `1982` displayed as `1,982` on `en_IE` locale. There is no standard widget attribute to suppress this, making `fields.Integer` unsuitable for any field whose value must render exactly as stored. `fields.Char` renders the raw stored value and defaults to `False` (blank) rather than `0` when empty, which is correct for an optional catalogue number.

**`lot_reference` format: `LOT/YYYY/NNNNN` via per-company `ir.sequence`**
The reference is system-generated at record creation using `ir.sequence` with code `sor.lot`. The year-prefix format is the SOR convention for operational identifiers (matching `sor_legal_agreement`). Per-company sequences ensure SO Fine Art and SETU maintain independent counters starting from `LOT/2026/00001`. The `with_company(company)` call in `create()` ensures the counter used belongs to the record's company, not the user's session company — these can differ when a multi-company user creates records on behalf of another company.

**`lot_number` is editable in Draft and Catalogued states**
The form view sets `lot_number` to `readonly="state not in ('draft', 'catalogued')"`. Lot numbers are typically assigned while the sale catalogue is being built (Catalogued state), so the field must remain editable at Catalogued. Once the lot advances to Sold, Passed, or beyond, the catalogue is finalised and the number must not change.

**Action buttons added at D1 (not deferred to D2)**
The D1 specification originally deferred action buttons to D2. Revised during D1 Completions (Story 02): the core state machine is fully defined at the base module level and requires no event context. D2 bridges extend the workflow but do not own the base transitions.

**`live` state removed in Sprint 24 (Auction Completions)**
The `live` selection value was removed from the state field. In practice, the "Live" state (lot is open for bidding) was not operationally distinguishable from "Catalogued" in the workflow — auctioneers move directly from catalogue management to sale outcome recording. Removing it simplifies the state machine from six to five states. The `action_mark_sold` and `action_mark_passed` guards accept `state in ('catalogued', 'live')` for backwards compatibility with any lots that were set to `live` before this change.

**`action_mark_collected` and `is_collected` flag added in Sprint 24 (Auction Completions)**
Collection of a lot is recorded via the `is_collected` boolean flag, not a state transition. Clicking **Mark as Collected** sets `is_collected = True`; the lot state remains `sold` or `passed`. This preserves auction outcome visibility in list views and reports. `auction_result` (set at Sold/Passed transition) persists through collection. The `collected_display` computed Char field returns `'Collected'` when `is_collected=True` and renders in the form header next to the statusbar. The former `collected` state was removed in BUG-U13. `sor_lotting_tracking` extends `action_mark_collected` to also create an outbound picking.

**`mail.thread` added in Sprint 24 (Auction Completions)**
`sor.lot` now inherits `['mail.thread', 'mail.activity.mixin']` and has `state` with `tracking=True`. Previously documented as a deferred capability — added once the five-state lifecycle was stabilised. This required adding `mail` to the manifest `depends` list. Bridge modules that call `self.message_post()` on lot records rely on this inheritance.

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

**`mail.thread` added in Sprint 24 — previously absent**
The prior architecture decision to defer `mail.thread` to bridge modules was reversed in Sprint 24 (BUG-S05-F05). The `sor.lot` state machine has a five-state lifecycle and every state transition has audit value. `mail.thread` + `tracking=True` on `state` provides automatic chatter logging with no additional code. The `sor_lotting_tracking` bridge requires `message_post` on `sor.lot` records — that method only exists when `mail.thread` is inherited. Requiring `mail` in the base module is the correct architectural choice; deferring it to a bridge would make the bridge a prerequisite for basic audit functionality.

**`lot_title`/`lot_description` lock at Catalogued (Auction MVP Refinements Story 05)**
Previously these two fields had no `readonly` gating at all. Direct auctioneer consultation established the correct test: does a field's value get printed in, or otherwise committed to, an external document (the printed catalogue) such that a later change would create a visible mismatch? `lot_title`/`lot_description` are catalogue-facing content — once a lot is Catalogued, its title and description are committed to the printed catalogue, so both now lock (`readonly="state != 'draft'"`). This is the inverse of the Fees tab's own field-locking correction in the same story (see `sor_commercial_auction_house`'s Technical Architecture, Architecture Decision §8) — Fees tab content stays negotiable and unlocked at every state because none of it is ever printed in the catalogue, while `lot_title`/`lot_description` is exactly the content that is. `consignor_id` was explicitly confirmed out of scope — it fails the same catalogue-commitment test (never printed) but was not touched, since it was already unlocked and PO confirmed no change was needed.

---

## Models

### sor.lot

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `lot_reference` | Char | Yes | `'New Lot'` → sequence on create | System-generated `LOT/YYYY/NNNNN`; `readonly=True`; `copy=False`; `index=True` |
| `lot_number` | Char(10) | No | — | Optional catalogue number; editable in draft/catalogued only; Char to avoid locale-formatted display |
| `lot_title` | Char | No | — | Human-readable lot title; searchable via `_name_search`. `readonly="state != 'draft'"` (Story 05, see Architecture Decisions) |
| `lot_description` | Html | No | — | Rich-text lot description for catalogue copy. Same `readonly="state != 'draft'"` as `lot_title` (Story 05) |
| `lot_item_name` | Char | — | — | Computed; `store=False`; returns `product_id.name` or `lot_title` |
| `product_id` | Many2one → `product.template` | No | — | Domain: `type != 'service'`; no longer required (Sprint 24) |
| `consignor_id` | Many2one → `res.partner` | No | — | Consignor/vendor; `check_company=True` |
| `buyer_id` | Many2one → `res.partner` | No | — | Winning buyer; `check_company=True` |
| `company_id` | Many2one → `res.company` | Yes | `env.company` | `_check_company_auto = True` |
| `currency_id` | Many2one → `res.currency` | — | — | Related: `company_id.currency_id`; `store=True` |
| `estimate_low` | Monetary | No | — | `currency_field='currency_id'` |
| `estimate_high` | Monetary | No | — | `currency_field='currency_id'` |
| `reserve_price` | Monetary | No | — | `currency_field='currency_id'` |
| `no_reserve` | Boolean | No | `False` | Independent of `reserve_price`; both can coexist |
| `starting_bid` | Monetary | No | — | `currency_field='currency_id'` |
| `hammer_price` | Monetary | No | — | `currency_field='currency_id'` |
| `break_even_value` | Monetary | — | — | Computed; `store=False`; `@api.depends('reserve_price')` |
| `state` | Selection | Yes | `'draft'` | Five values: draft, catalogued, sold, passed, withdrawn (Sprint 24 — `live` and `collected` removed); `tracking=True`; `copy=False` |
| `auction_result` | Selection | No | — | Set by `action_mark_sold` (`'sold'`) / `action_mark_passed` (`'passed'`); persists after `is_collected`; `copy=False` |
| `is_collected` | Boolean | No | `False` | Set by `action_mark_collected()`; state unchanged; `copy=False`; `tracking=True` |
| `collected_display` | Char | — | — | Computed; `store=False`; `@api.depends('is_collected')`; returns `'Collected'` or blank |
| `internal_notes` | Html | No | — | Rich-text; rendered as editor directly in page (not in group) |

**Model attributes:**
- `_name = 'sor.lot'`
- `_inherit = ['mail.thread', 'mail.activity.mixin']` — chatter and activity tracking (added Sprint 24)
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

**State values (Sprint 24 — five states; `collected` removed in BUG-U13):**

| Value | Label |
|-------|-------|
| `draft` | Draft |
| `catalogued` | Catalogued |
| `sold` | Sold |
| `passed` | Passed |
| `withdrawn` | Withdrawn |

**Methods:**

| Method | Decorator | Return | Guard | Notes |
|--------|-----------|--------|-------|-------|
| `create` | `@api.model_create_multi` | recordset | — | Assigns `lot_reference` from `ir.sequence` with `with_company(company)` |
| `unlink` | — | bool | Raises `UserError` if `state != 'draft'` | Deletion guard |
| `_compute_lot_item_name` | `@api.depends('product_id', 'lot_title')` | void | — | Returns `product_id.name` or `lot_title` |
| `_compute_break_even_value` | `@api.depends('reserve_price')` | void | — | Sets `break_even_value = reserve_price or 0.0` |
| `_name_search` | `@api.model` | list | — | Searches `lot_reference`, `lot_number`, `lot_title` in addition to default |
| `action_catalogue` | — | void | `state == 'draft'`; also raises if any lot has no `lot_number` | Transitions to `catalogued` |
| `action_mark_sold` | — | void | `state in ('catalogued', 'live')` | Transitions to `sold`; sets `auction_result='sold'`; `live` accepted for backwards compat |
| `action_mark_passed` | — | void | `state in ('catalogued', 'live')` | Transitions to `passed`; sets `auction_result='passed'`; `live` accepted for backwards compat |
| `action_mark_collected` | — | void | `state in ('sold', 'passed')` | Sets `is_collected=True`; state unchanged; extended by `sor_lotting_tracking` |
| `action_withdraw` | — | void | `state in ('draft', 'catalogued')` | Transitions to `withdrawn` |
| `_compute_collected_display` | `@api.depends('is_collected')` | void | — | Returns `'Collected'` or blank for the form header field |
| `action_open_product` | — | dict (act_window) | `ensure_one()` | Opens product in modal dialog (`target: 'new'`) |

### models/res_company.py

Extends `res.company` with a `create` override that creates an `ir.sequence` (code `sor.lot`, prefix `LOT/%(year)s/`, padding 5) for each newly created company. Ensures every company has an independent lot reference counter from day one.

### models/product_template.py

Extends `product.template` to override `_compute_display_name`. When the context key `suppress_product_code` is set (used by the `product_id` field on the lot form), the display name renders as the product name only, without the internal reference prefix. This prevents the form and list from showing `[REF] Product Name` in the lot context where the reference code is irrelevant.

---

## Views

### sor_lot_view_form (primary)

Form view with:
- `<header>`: Five action buttons — Catalogue (visible when draft), Mark Sold (visible when catalogued), Mark Passed (visible when catalogued), Mark as Collected (visible when sold or passed and not yet collected), Withdraw (visible when draft or catalogued). `state` statusbar widget with `statusbar_visible="draft,catalogued,sold,passed,withdrawn"`. `collected_display` field renders "Collected" text after the statusbar when `is_collected=True`.
- `<sheet>`: Two groups — Identification (lot_reference readonly, lot_number with state-based readonly for draft+catalogued only, lot_title with `readonly="state != 'draft'"` (Story 05) and `invisible="1"` when `sor_lotting_base` is installed, product_id with modal open button, consignor_id (unaffected by Story 05 — no readonly), buyer_id, company_id with multi-company guard) and Financial (currency_id invisible, estimates, reserve, no_reserve, starting_bid, hammer_price, break_even_value read-only).
- `<notebook>`: Lot Description page (Html field direct in page, `readonly="state != 'draft'"` per Story 05), Internal Notes page (Html field direct in page, never locked).
- `<chatter/>` — state transitions logged automatically via `mail.thread`.
- D2 injection comment marks where `auction_id` and fee tabs are added by the bridge.

### sor_lot_view_list (primary)

List view with columns, in order: `currency_id` (`optional="hide"` — Monetary widget currency resolution), `lot_reference`, `lot_number`, `lot_item_name`, `state`, `is_collected` (`optional="show"`, labelled "Collected"), `estimate_low` (`optional="hide"`), `estimate_high` (`optional="hide"`), `reserve_price`, `hammer_price`. `estimate_low`/`estimate_high` were changed from `optional="show"` to `optional="hide"` in Auction Refinements 01, Story 2 — the PO's original intent was for these to declutter the default view (reachable but not shown by default), overriding an initial Development-time judgment call that kept them visible by default (BUG-S02).

### sor_lot_view_search (primary)

Search view with:
- Field search: lot_reference, lot_number, lot_title, product_id
- Individual state filters: Draft, Catalogued, Sold, Passed, Withdrawn

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
| `sor_lotting` only | `sor.lot` model with full field set, per-company sequence, five-state lifecycle with action buttons, chatter, estimate constraint. User-facing Lots menu. No event link. |
| `sor_lotting` + `sor_events` | No change to either module. Independent horizontals — no bridge yet. |
| `sor_lotting` + `sor_events_auction` (D2) | Bridge auto-installs. Lots gain `event_id` → `sor.event`. Auction-contextual Lots access via Auctions menu. |
| `sor_lotting` + `sor_contact_roles` | `sor_lotting_contact_roles` auto-installs. Consignor earned sub-type assigned on lot create/write. Partner form gains Consigned Lots smart button and tab. |
| `sor_lotting` + `sor_tracking` | `sor_lotting_tracking` auto-installs. Mark as Collected creates and auto-validates a Movement Out picking; chatter links both records. |
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
`lot_number` uses `readonly="state not in ('draft', 'catalogued')"` — an inline OWL expression, not a separate `attrs` dict. This is the Odoo 19 form rendering pattern. The field is editable in Draft and Catalogued states (catalogue is still being built), then becomes read-only from Sold onwards.

**`lot_number` type change from Integer to Char — Sprint 24**
The field type change from `fields.Integer` to `fields.Char(size=10)` did not require a migration script because no view arch references `lot_number` by type in invisible/domain expressions. The column type change from `int4` to `varchar` on the PostgreSQL table is handled by the module upgrade. Existing integer values in the DB are coerced to string representations without precision loss (e.g. `42` → `'42'`). The `filter_domain` in the search view was updated from exact-integer to string contains for consistency.

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
- Auction MVP Refinements Story 05 — Fees Tab / Catalogue Content Field Locking (locked `lot_title`/`lot_description` at Catalogued): `.backlog/current/Auction MVP Refinements/stories/05_Fees-Tab-Catalogue-Content-Field-Locking.md`
