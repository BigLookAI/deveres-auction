# Technical Architecture: sor_bidding

## Overview

`sor_bidding` is a **bridge module** that delivers bid recording for auction lots — a feature that only makes sense when both `sor_lotting` and `sor_contact_roles` are installed simultaneously:

```
sor_lotting          sor_contact_roles
      \                   /
       \                 /
    sor_bidding   (auto_install=True, application=False)
```

`sor_lotting` provides the `sor.lot` model. `sor_contact_roles` provides the Bidder contact type that identifies auction participants. Neither parent module is modified. The bridge introduces `sor.bid`, extends `sor.lot` with bid relationship fields, overrides `action_mark_sold()` to auto-derive `hammer_price`, and patches the lot form view with a Bids tab and stat button.

---

## Module Pattern

**Manifest flags:**

```python
'category': 'Hidden/Technical',
'depends': ['sor_lotting', 'sor_contact_roles'],
'auto_install': True,
'application': False,
```

- `auto_install: True` — Odoo installs the bridge automatically when both `sor_lotting` and `sor_contact_roles` are present. No manual installation step required.
- `application: False` — The bridge does not appear as a top-level App.
- `category: 'Hidden/Technical'` — Kept out of business category listings.
- No `summary` — bridge modules carry no marketing metadata.

**Why a bridge?** `sor_lotting` must be installable without contact role features (a pure catalogue tool). `sor_contact_roles` must be installable without lot features (a pure contact management tool). The bid model requires both: it links a lot (`lot_id` → `sor.lot`) and a bidder (`bidder_id` → `res.partner` scoped by contact type). Placing this coupling in either parent would violate SOR composability constraints.

---

## Architecture Decisions

### company_id as a related stored field

`sor.bid.company_id` is not an independent required field — it is a `related='lot_id.company_id'` stored field:

```python
company_id = fields.Many2one(
    comodel_name='res.company',
    related='lot_id.company_id',
    store=True,
)
```

**Rationale:** Bids have no company identity independent of their lot. A bid's company is always and only the company of the lot it belongs to. Using `related=` and `store=True` makes the value queryable at the database level (required by the `ir.rule` domain) without adding a separate write-path for company assignment. If a lot's company were ever changed, bids would update automatically on the next ORM flush — consistent without custom logic.

`store=True` is correct here because `company_id` depends on a stored Many2one field (`lot_id.company_id`), not on session-time `env.company`. The "store=False for company-context-dependent computed fields" convention applies to fields that read `env.company`; this field reads a stored record attribute.

### check_company=True on lot_id but NOT on bidder_id

`lot_id` carries `check_company=True`:

```python
lot_id = fields.Many2one(
    comodel_name='sor.lot',
    check_company=True,
    ...
)
```

`bidder_id` does **not** carry `check_company=True`:

```python
bidder_id = fields.Many2one(
    comodel_name='res.partner',
    ...  # no check_company
)
```

**Rationale:** `res.partner` does not have a simple `company_id` field that Odoo's `_check_company_auto` mechanism can validate against. In Odoo 19, adding `check_company=True` to a Many2one targeting `res.partner` raises an ORM error on write. Bidder contact records are global (not company-scoped) — a bidder may participate in auctions across multiple companies. Company isolation is achieved through the `ir.rule` on `sor.bid` (which filters records by `company_id in company_ids`), not through ORM-level validation on the partner link.

This is consistent with the `sor_multi_company.md` documented exception: `check_company=True` must not be added to fields targeting models without a canonical `company_id`.

### Sold action override — guard, winning bid, chain-safe super() call

`action_mark_sold()` is overridden in `sor_lot_bidding.py`:

```python
def action_mark_sold(self):
    for lot in self:
        if not lot.bid_ids:
            raise UserError(
                _('Lot "%s" cannot be marked Sold because it has no bids. '
                  'At least one bid must be recorded before marking a lot as Sold.')
                % lot.lot_reference,
            )
        winning_bid = lot.bid_ids.sorted('amount', reverse=True)[0]
        lot.hammer_price = winning_bid.amount
        winning_bid.is_winning_bid = True
    return super().action_mark_sold()
```

The bridge operates **before** calling `super()`:
1. **Guard:** Raises `UserError` if `bid_ids` is empty — a lot with no bids cannot be sold through the UI or programmatically.
2. **Winning bid selection:** Sorts by `amount` descending; the first record is the winning bid.
3. **hammer_price:** Set before the state transition — future bridge modules see the hammer price populated when their `super()` chain runs.
4. **Winning bid lock:** `is_winning_bid = True` is written on the winning bid record. The view uses this boolean to make all editable fields on that bid read-only (standalone form and inline Bids tab).
5. The `UserError` guards in the base `action_mark_sold()` (state must be `catalogued` or `live`) still apply — the bridge does not bypass them.

### type="object" stat button — why not type="action"

The Bids stat button on the lot form uses `type="object"` (calling `action_view_bids()`) rather than `type="action"` (referencing the standalone window action). `type="action"` stat buttons execute the window action directly with no record context — the `domain` in the action XML cannot reference `active_id` to filter by the current lot. Switching to `type="object"` allows the Python method to construct a domain with `('lot_id', '=', self.id)`, giving a correctly filtered list per lot. The same pattern is used for the partner Bids stat button.

### Bidder auto-classification hook — create() override on sor.bid

When a bid is created, the bridge auto-assigns the **Contact parent type** and **Bidder sub-type** to the bidder partner if not already present:

```python
@api.model_create_multi
def create(self, vals_list):
    records = super().create(vals_list)
    for bid in records:
        if bid.bidder_id:
            bid._assign_bidder_contact_type()
    return records

def _assign_bidder_contact_type(self):
    partner = self.bidder_id
    ContactType = self.env['sor.contact.type']
    contact_type = ContactType.search(
        [('code', '=', 'contact'), ('parent_type_id', '=', False)], limit=1,
    )
    bidder_subtype = ContactType.search(
        [('code', '=', 'bidder'), ('parent_type_id', '!=', False)], limit=1,
    )
    if contact_type and contact_type not in partner.contact_types:
        partner.contact_types = [(4, contact_type.id)]
    if bidder_subtype and bidder_subtype not in partner.contact_subtypes:
        partner.contact_subtypes = [(4, bidder_subtype.id)]
```

**Why `(4, id)` commands:** Odoo's Many2many command `(4, id)` adds the record if not already present and is a no-op if it is. The hook is therefore idempotent — calling it multiple times for the same partner (multiple bids) does not duplicate type records.

**Why here, not in `sor_contact_roles`:** The auto-classification rule ("bidding earns Bidder type") is a cross-cutting concern that only makes sense when both the lot/bid infrastructure and the contact type infrastructure are present. The bridge is the correct home.

### bidder_id domain removed — context-based default filter instead

The `bidder_id` field previously carried `domain=[('contact_types.code', '=', 'bidder')]`, restricting the field to contacts already classified as Bidder type. This was removed because:

1. **Chicken-and-egg:** A first-time bidder has no Bidder type before their first bid. They could not be selected as a bidder if the domain were active, which would prevent the hook from ever firing.
2. **Correct UX pattern:** `context={'search_default_filter_contacts': 1}` activates the `filter_contacts` filter (defined in `sor_contact_roles`) by default in both the autocomplete and the Search More modal. Unlike a hard domain, this filter is removable by the user in the Search More modal, allowing staff to select Artists or untyped contacts when needed.

**Odoo constraint:** A hard `domain` on a Many2one field applies to both the autocomplete dropdown and the Search More modal and cannot be overridden by the user. `context={'search_default_<filter>': 1}` applies the filter as a default that the user can remove in Search More, but does not filter the autocomplete. There is no standard Odoo mechanism for "filtered autocomplete, unfiltered Search More" — this would require a custom widget (tracked as Sprint Finding F-10).

### external_bid_id — forward-looking import infrastructure

`external_bid_id` is a `Char` field with `index=True`. It carries no constraint or uniqueness requirement at this stage. Its purpose is to give future import scripts a stable handle for idempotent upsert operations — checking `search([('external_bid_id', '=', platform_bid_id)])` before creating avoids duplicate bid records when importing from auction platforms.

The index is applied at this stage (not deferred) because import deduplication queries will run at high frequency during live sale imports and require indexed lookup performance.

### active_id → id fix in view context (Odoo 19 breaking change)

The Bids tab on the lot form uses `context="{'default_lot_id': id}"` to pre-populate `lot_id` on inline bid creation:

```xml
<field name="bid_ids" context="{'default_lot_id': id}">
```

In Odoo 19, view validators reject `active_id` in field `context=` attributes — `active_id` is a context variable, not a model field, and the validator raises an "Access Rights Inconsistency" error at registry load time. `id` is the correct substitution: it resolves to the current record's `id` field and is always available in the arch context.

---

## Models

### sor.bid (new model)

Defined in `models/sor_bid.py`.

| Field | Type | Notes |
|-------|------|-------|
| `lot_id` | Many2one `sor.lot` | Required. `check_company=True`. `ondelete='cascade'` — bids are deleted when their lot is deleted. `index=True` for performance on `bid_ids` One2many traversal. |
| `company_id` | Many2one `res.company` | `related='lot_id.company_id'`, `store=True`. Drives multi-company record rule. |
| `currency_id` | Many2one `res.currency` | `related='lot_id.currency_id'`, `store=True`. Required for Monetary field widget resolution. |
| `bidder_id` | Many2one `res.partner` | Required. `context={'search_default_filter_contacts': 1}` — defaults the autocomplete and Search More to Contact-type partners; user can remove the filter in Search More to select any partner. No hard domain (removed in Contact Roles Enhancements sprint — any partner may bid). No `check_company=True` — see Architecture Decisions. |
| `bid_type` | Selection | `floor`, `absentee`, `commission`, `online`, `phone`. Required. |
| `amount` | Monetary | Required. `currency_field='currency_id'`. |
| `max_amount` | Monetary | Optional. `currency_field='currency_id'`. Used for commission bids only — hidden by view `invisible` expression for other types. |
| `bid_datetime` | Datetime | Required. Default: `fields.Datetime.now`. |
| `external_bid_id` | Char | Optional. `index=True`. Import deduplication handle. |
| `is_winning_bid` | Boolean | Default `False`. `copy=False`. Set to `True` on the winning bid by `action_mark_sold()`. Drives `readonly` expressions in both the standalone form and the inline Bids tab. |
| `notes` | Text | Optional. Internal notes. |

Model-level attributes:
- `_order = 'bid_datetime desc'` — most recent bid first in default display
- `_check_company_auto = True` — ORM validates `check_company=True` fields on write

### sor.lot (extended)

Defined in `models/sor_lot_bidding.py` via `_inherit = 'sor.lot'`.

| Field / Method | Type | Notes |
|----------------|------|-------|
| `bid_ids` | One2many `sor.bid` | Inverse of `lot_id`. All bids linked to this lot. |
| `bid_count` | Integer (computed, `store=False`) | `@api.depends('bid_ids')`. Count of bids. Not stored — recalculated on every form load. |
| `action_mark_sold()` | Method override | Guards against no bids (raises `UserError`). Writes `hammer_price` from highest bid, sets `is_winning_bid=True` on that bid, then calls `super()`. |
| `action_view_bids()` | Method | Returns `ir.actions.act_window` dict with `domain=[('lot_id', '=', self.id)]`. Used by the `type="object"` stat button. |

### res.partner (extended)

Defined in `models/res_partner_bidding.py` via `_inherit = 'res.partner'`.

| Field / Method | Type | Notes |
|----------------|------|-------|
| `bid_ids` | One2many `sor.bid` / `bidder_id` | All bids where this partner is the bidder. |
| `bid_count` | Integer (computed, `store=False`) | Count of bids for this partner scoped to `env.company`. Uses `search_count` with `company_id` filter — not `len(bid_ids)` — to ensure multi-company isolation. |
| `action_view_bids()` | Method | Returns `ir.actions.act_window` dict with `domain=[('bidder_id', '=', self.id), ('company_id', '=', self.env.company.id)]`. Used by the `type="object"` stat button on the partner form. |

---

## Views

### sor.bid standalone form (`sor_bid_view_form`)

A standalone form for the `sor.bid` model. Used when the Bids stat button opens the full bid list and a user drills into a single bid.

- `currency_id` is declared with `invisible="1"` — required in the arch for Monetary widget resolution in Odoo 19 even though the column is not shown to the user.
- `max_amount` carries `invisible="bid_type != 'commission'"` — the field is hidden unless the bid type is Commission.

### sor.bid standalone list (`sor_bid_view_list`)

A list view for the `sor.bid` model. Used by the window action behind the stat button.

- `max_amount` uses `optional="hide"` — visible on demand, not shown by default.

### sor.lot form patch — Bids tab (`sor_lot_view_form_bids_tab`)

Inherits `sor_lotting.sor_lot_view_form` (non-primary). Inserts a **Bids** page inside the lot's notebook.

- The embedded list is `editable="bottom"` — bids can be added inline without opening a separate form.
- `currency_id` is declared `column_invisible="1"` — required for Monetary widget resolution in Odoo 19 list views; suppressed as a visible column.
- Context `{'default_lot_id': id}` pre-populates `lot_id` on new inline bids. Uses `id` (not `active_id`) — Odoo 19 view validator constraint.

### sor.lot form patch — Bids stat button (`sor_lot_view_form_bid_count_button`)

Inherits `sor_lotting.sor_lot_view_form` (non-primary). Inserts a `div.oe_button_box` with a stat button before the first group in the sheet.

- Positioned before `//sheet/group[1]` because the base `sor.lot` form has no existing `button_box` — the bridge creates it.
- Uses `type="object"` calling `action_view_bids()` so the action domain is constructed server-side with `('lot_id', '=', self.id)`. A `type="action"` stat button cannot pass the current record context into the domain.

### sor.lot form patch — hammer_price readonly when Sold (`sor_lot_view_form_hammer_price_readonly`)

Inherits `sor_lotting.sor_lot_view_form`. Adds `readonly="state == 'sold'"` to `hammer_price` so the field cannot be modified after the lot outcome is confirmed.

### res.partner form patch — Bids stat button + Bid History tab (`res_partner_view_form_bid_history`)

Inherits `base.view_partner_form`. Adds two elements:

1. **Stat button** — `type="object"` calling `action_view_bids()`. Visible only when `bid_count > 0`. Uses `type="object"` for the same reason as the lot stat button.
2. **Bid History tab** — An embedded read-only list (`create="0" delete="0"`) showing this bidder's bids. Visible only when `bid_count > 0`. Columns: Bid Date/Time, Lot, Bid Type, Amount, Winning Bid.

---

## Module File Structure

```
addons/sor_bidding/
├── __init__.py
├── __manifest__.py                   # depends=['sor_lotting','sor_contact_roles'], auto_install=True
├── models/
│   ├── __init__.py
│   ├── res_partner_bidding.py        # res.partner extension: bid_ids, bid_count, action_view_bids
│   ├── sor_bid.py                    # sor.bid model definition (includes is_winning_bid)
│   └── sor_lot_bidding.py            # sor.lot extension: bid_ids, bid_count, action_mark_sold, action_view_bids
├── views/
│   └── sor_bidding_views.xml         # sor.bid form/list; sor.lot Bids tab, hammer_price, stat button; res.partner bid history
├── security/
│   ├── ir.model.access.csv           # sor.bid: read/write/create/unlink for all users
│   └── sor_bidding_rules.xml         # Multi-company ir.rule on sor.bid (noupdate="1")
├── data/
│   └── sor_bidding_data.xml          # Empty — Bidder contact type owned by sor_contact_roles
├── i18n/
│   └── sor_bidding.pot               # Translatable strings export
├── tests/
│   ├── __init__.py
│   └── test_sor_bidding.py           # 22 automated tests
└── doc/
    ├── KNOWLEDGE_BASE.md             # User-facing feature documentation
    └── TECHNICAL_ARCHITECTURE.md    # This file
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | `auto_install=True`, `depends=['sor_lotting','sor_contact_roles']` — the composability declaration |
| `models/sor_bid.py` | `sor.bid` model: all fields including `is_winning_bid`, `_check_company_auto`, `_order` |
| `models/sor_lot_bidding.py` | `sor.lot` extension: `bid_ids`, `bid_count`, `action_mark_sold()` override, `action_view_bids()` |
| `models/res_partner_bidding.py` | `res.partner` extension: `bid_ids`, `bid_count`, `action_view_bids()` |
| `views/sor_bidding_views.xml` | All view records: `sor.bid` form/list, Bids tab patch, hammer_price readonly patch, lot stat button, res.partner bid history patch |
| `security/sor_bidding_rules.xml` | Multi-company `ir.rule` — `noupdate="1"` |
| `security/ir.model.access.csv` | `sor.bid` full access for `base.group_user` |
| `tests/test_sor_bidding.py` | 27 tests covering creation, computed fields, Sold transition, is_winning_bid, action_view_bids, partner bid history, multi-company isolation, composability, bidder hook assignment and idempotency |

---

## Composability Boundary

| Scenario | `bid_ids` on `sor.lot` | Bids tab | Stat button | `hammer_price` auto-population |
|----------|-----------------------|----------|-------------|-------------------------------|
| `sor_lotting` only | ✗ absent | ✗ absent | ✗ absent | ✗ not active |
| `sor_contact_roles` only | ✗ absent | ✗ absent | ✗ absent | ✗ not active |
| Both installed | ✓ present (bridge auto-activates) | ✓ present | ✓ present | ✓ active |

This boundary is verified by automated tests `test_17_bid_ids_present_on_sor_lot` and `test_18_bid_count_present_on_sor_lot`.

---

## Special Concerns

### Bidder contact type ownership

The `sor.contact.type` record with `code='bidder'` is seeded by `sor_contact_roles` (XMLID: `sor_contact_roles.sor_contact_type_bidder`). This bridge does **not** re-create it. `sor_bidding/data/sor_bidding_data.xml` is intentionally empty.

If `sor_contact_roles` is uninstalled, the Bidder contact type record is removed. The `_assign_bidder_contact_type()` hook searches for the type by code — if not found, it is a no-op. Existing `bidder_id` values on `sor.bid` records remain — there is no database-level constraint linking bids to contact types.

### Multi-company record rule uses company_id

The `ir.rule` on `sor.bid` filters by `company_id`:

```xml
<field name="domain_force">['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]</field>
```

This relies on `company_id` being populated. Since `company_id` is a stored related field derived from `lot_id.company_id`, it is always set when `lot_id` is set (and `lot_id` is `required=True`). The `company_id = False` clause is a safety guard for records that might exist without a lot (e.g. imported records with ORM bypass) — in normal operation it never fires.

### currency_id declaration in views — Odoo 19 constraint

Odoo 19's view and list arch parsers require `currency_id` to be declared in the arch when `Monetary` fields are present. Two patterns are used:

- **Form view:** `<field name="currency_id" invisible="1"/>` — hidden but present.
- **List view (Bids tab):** `<field name="currency_id" column_invisible="1"/>` — removes the column entirely including its header. `optional="hide"` is not a valid substitute here: Odoo 19 does not fetch data for `optional="hide"` columns by default, so the Monetary widget's currency dependency cannot be satisfied.

### No data migration on sor_bidding uninstall

Uninstalling `sor_bidding` drops the `sor_bid` table and removes the `bid_ids`, `bid_count`, and `hammer_price`-override extensions from `sor.lot`. Any recorded bid data is permanently lost. The underlying `sor.lot` records survive uninstall. This is the standard Odoo additive-only uninstall behaviour — no recovery mechanism is provided.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_bidding
```

---

## Story Reference

Original: `.backlog/previous/09 Auction Engine/stories/02_Bid-Recording.md` — Sprint 09 Auction Engine

Extended: `.backlog/current/Contact Roles Enhancements/stories/05_Bidder-Hook.md` — Contact Roles Enhancements (bidder auto-classification hook; `bidder_id` domain removal)
