# sor_bidding — Knowledge Base

## Overview

`sor_bidding` is a bridge module that adds **bid recording** to auction lots. It activates automatically when both `sor_lotting` and `sor_contact_roles` are installed. When the bridge is active, every lot gains a Bids tab where staff can record bids from registered bidder contacts, and the Mark as Sold action auto-populates the hammer price from the highest recorded bid.

**What this module does NOT do:**

- Conduct live auctions or manage real-time bidding state
- Enforce bid increment rules or minimum bid logic
- Import bids from external platforms automatically (the `external_bid_id` field is infrastructure for future import scripts — no import UI is included)
- Re-seed the Bidder contact type — that record is owned and seeded by `sor_contact_roles`

**Depends on:** `sor_lotting` (lots), `sor_contact_roles` (bidder contact type)

**Auto-activates with:** both `sor_lotting` and `sor_contact_roles` installed simultaneously

---

## Key Fields and Models

### sor.bid

The central model introduced by this module. Each record represents a single bid placed against an auction lot.

| Field | Type | Description |
|-------|------|-------------|
| `lot_id` | Many2one `sor.lot` | The lot this bid is against. Required. `check_company=True`. Cascades on lot deletion. |
| `company_id` | Many2one `res.company` | Related stored from `lot_id.company_id`. Drives the multi-company record rule. |
| `currency_id` | Many2one `res.currency` | Related stored from `lot_id.currency_id`. Required by Monetary widget. |
| `bidder_id` | Many2one `res.partner` | The bidder. Required. Autocomplete defaults to Contact-type partners (`search_default_filter_contacts` context). Any partner is selectable via Search More. On save, the hook auto-assigns Contact parent type and Bidder sub-type to the partner if not already present. |
| `bid_type` | Selection | How the bid was placed. Five values — see Bid Types table below. Required. |
| `amount` | Monetary | The bid amount at the time placed. Required. |
| `max_amount` | Monetary | Commission bid ceiling only. See commission bid pattern below. Optional. |
| `bid_datetime` | Datetime | When the bid was placed. Defaults to `fields.Datetime.now`. Required. |
| `external_bid_id` | Char | External platform reference. Indexed. Used for idempotent import deduplication. |
| `is_winning_bid` | Boolean | Set to `True` by `action_mark_sold()` on the bid that determines the hammer price. `copy=False`. When `True`, locks all editable fields on the bid record (form and inline Bids tab). |
| `notes` | Text | Internal free-text notes on this bid. |

### Bid Types

| Value | Label | When to use |
|-------|-------|-------------|
| `floor` | Floor | Bid placed by someone physically present in the room |
| `absentee` | Absentee | Written/sealed bid submitted before the sale; auctioneer bids on behalf up to the stated amount |
| `commission` | Commission | Auctioneer acts as agent for an absent bidder, bidding up to `max_amount` |
| `online` | Online | Bid placed via an online platform during the live sale |
| `phone` | Phone | Bid relayed by a specialist on behalf of a bidder on the telephone |

### Fields added to sor.lot

| Field | Type | Description |
|-------|------|-------------|
| `bid_ids` | One2many `sor.bid` | All bids linked to this lot. Visible in the Bids tab. |
| `bid_count` | Integer (computed, not stored) | Count of bids on this lot. Displayed as a stat button. |

### Fields added to res.partner

| Field | Type | Description |
|-------|------|-------------|
| `bid_ids` | One2many `sor.bid` | All bids where this partner is the bidder. Drives the Bid History tab. |
| `bid_count` | Integer (computed, not stored) | Count of bids for this partner in the current company. Displayed as a stat button on the partner form. Hidden when 0. |

---

## Methods

### SorLotBidding.action_mark_sold()

Override of `sor.lot.action_mark_sold()`. Before calling `super()`:

1. **Guards against no bids:** raises `UserError` if `bid_ids` is empty. At least one bid must be recorded before a lot can be marked Sold.
2. **Selects the winning bid:** sorts `bid_ids` by `amount` descending; the first record is the winning bid.
3. **Sets hammer price:** writes `hammer_price = winning_bid.amount`.
4. **Locks the winning bid:** sets `winning_bid.is_winning_bid = True`, which causes all editable fields on that bid record to become read-only (in both the standalone form and the inline Bids tab on the lot).

```python
# Logic summary:
if not lot.bid_ids:
    raise UserError(...)
winning_bid = lot.bid_ids.sorted('amount', reverse=True)[0]
lot.hammer_price = winning_bid.amount
winning_bid.is_winning_bid = True
return super().action_mark_sold()
```

**Ordering note:** `sor.bid` records are ordered by `bid_datetime desc` for display. The hammer price is derived from the maximum amount — these may differ from the most-recently-recorded bid if bids are entered out of chronological order.

### SorLotBidding.action_view_bids()

Returns a window action that opens the `sor.bid` list filtered to bids for this specific lot. Used by the Bids stat button on the lot form (`type="object"`) so the button can pass the current record's ID into the domain.

```python
# Returns an ir.actions.act_window dict with domain=[('lot_id', '=', self.id)]
```

### ResPartnerBidding.action_view_bids()

Returns a window action that opens the `sor.bid` list filtered to bids placed by this partner in the current company. Used by the Bids stat button on the partner form.

```python
# Returns domain=[('bidder_id', '=', self.id), ('company_id', '=', self.env.company.id)]
```

---

## Configuration

`sor_bidding` requires no configuration after installation. It activates automatically and all features are immediately available.

**Prerequisites:**

1. `sor_lotting` must be installed — provides `sor.lot`.
2. `sor_contact_roles` must be installed — provides the Bidder contact type (`code='bidder'`) used as the `bidder_id` domain filter.

Once both prerequisites are installed, `sor_bidding` auto-installs. Navigate to **Inventory → Lots** (or the relevant auction catalogue view) to see the Bids tab on any lot form.

### Commission bid max_amount pattern

`max_amount` is displayed on the bid form only when `bid_type == 'commission'`. For all other bid types the field is hidden. Staff should record:

- `amount`: the opening or current bid entered for this bidder
- `max_amount`: the ceiling the bidder has authorised the auctioneer to bid up to

During a live auction, the auctioneer increments `amount` per bid round and adds a new commission bid record each time they bid on behalf of the commission bidder, up to `max_amount`.

---

## Developer Menu

`sor_bidding` adds no items to the SOR Technical developer menu. The `sor.bid` model is accessible via the standard **Settings → Technical → Models** inspector (developer mode required), or through the standalone bid list action referenced in the Bids stat button on the lot form.

---

## Building on This Module

A module that needs to extend bid behaviour (e.g. `sor_bidding_online_platform` to sync bids from an external API) should:

1. Declare `depends=['sor_bidding']` in the manifest.
2. Use `_inherit = 'sor.bid'` to add fields or override methods.
3. Use `external_bid_id` for deduplication when importing records — query `search([('external_bid_id', '=', platform_bid_id)])` before creating to avoid duplicates.
4. Use `_inherit = 'sor.lot'` to extend `action_mark_sold()` further if the new module needs additional sold-state logic — always call `super()` so the bridge chain is preserved.

For bridge modules that cross `sor_bidding` with another concern, add `sor_bidding` (not `sor_lotting` + `sor_contact_roles` separately) as the dependency, unless the new module genuinely requires access to features in both parents independently.

---

## Regression Checks

These checks confirm the feature is still working correctly after any future change to `sor_bidding`, `sor_lotting`, or `sor_contact_roles`.

**R1 — Bid tab appears on lot form**
1. Open Odoo and navigate to an auction lot.
2. Confirm a **Bids** tab is present in the lot's notebook alongside other tabs.
3. Click the Bids tab and confirm the embedded list is visible and editable.

**R2 — Bid can be created inline**
1. On a lot form, open the Bids tab.
2. Click **Add a line**.
3. Set Bidder (must be tagged as Bidder contact type), Bid Type, Amount, and Bid Date/Time.
4. Save the lot.
5. Confirm the bid row persists after save.

**R3 — max_amount visibility**
1. On a lot form, open the Bids tab and add a new bid line.
2. Set Bid Type to any value other than **Commission** — confirm the **Maximum** column is hidden.
3. Change Bid Type to **Commission** — confirm the **Maximum** column becomes visible.

**R4 — Stat button shows bid count and opens lot-filtered list**
1. Open a lot with at least two recorded bids.
2. Confirm the **Bids** stat button in the form header shows the correct count (e.g. "2 Bids").
3. Click the stat button — confirm it opens a bid list filtered to this lot only (no bids from other lots appear).

**R5 — Hammer price auto-population**
1. Create a lot and catalogue it.
2. Add three bids with amounts 1,000, 3,500, and 2,200.
3. Click **Mark as Sold**.
4. Confirm **Hammer Price** is automatically set to 3,500 (the highest bid amount).
5. Confirm the winning bid row is now read-only (locked) in the Bids tab.

**R6 — Mark as Sold blocked with no bids**
1. Create a lot and catalogue it.
2. Add no bids.
3. Click **Mark as Sold**.
4. Confirm a clear error message appears: "Lot … cannot be marked Sold because it has no bids."
5. Confirm the lot remains in Catalogued state and is not moved to Sold.

**R9 — Bids tab hidden on Draft lots**
1. Create a new lot (state = Draft).
2. Navigate to the lot form.
3. Confirm the **Bids** tab is absent.
4. Click **Catalogue** to move the lot to Catalogued.
5. Confirm the Bids tab appears.

**R10 — Winning bid row is read-only after Mark as Sold**
1. Open a Sold lot.
2. Navigate to the Bids tab.
3. Confirm the winning bid row (highest amount) has read-only fields — clicking cells does not make them editable.
4. Confirm non-winning bid rows (if any) remain editable.

**R11 — Bid History on partner**
1. Open a contact who has been recorded as a bidder on at least one lot.
2. Confirm a **Bids** stat button is visible in the form header with the correct count.
3. Click the stat button — confirm it opens a bid list filtered to this bidder in the current company.
4. On the partner form, navigate to the **Bid History** tab.
5. Confirm the embedded list shows the bidder's bids.

**R7 — Multi-company isolation**
1. Ensure two companies exist (e.g. SO Fine Art and SETU).
2. In Company A, create a lot and add a bid.
3. Switch to Company B in the session company switcher.
4. Navigate to **Settings → Technical → Models → sor.bid** and inspect all records.
5. Confirm the Company A bid does not appear in the Company B context.

**R8 — Bidder field default filter and Search More**
1. Open a lot form, go to the Bids tab, and add a line.
2. Click the **Bidder** field dropdown — confirm the autocomplete shows Contact-type partners (the Contacts filter is active by default).
3. Click **Search More** — confirm the modal opens with a **Contacts** filter chip active.
4. Click the × on the Contacts filter chip — confirm all partners (including Creators/Artists) now appear in the list.
5. A partner of any type should be selectable via Search More.

**R12 — Bidder auto-classification hook**
1. Identify a contact who has no Contact type and no Bidder sub-type assigned.
2. Open a lot form, add a bid line, and set that contact as the Bidder.
3. Save the lot.
4. Open the contact's record — confirm **Contact** is now listed in their Contact Types and **Bidder** in their Sub-Types.
5. Create a second bid for the same contact on any lot and save.
6. Open the contact's record again — confirm Contact type and Bidder sub-type each appear exactly once (no duplicates).

---

## Interoperability

| Module combination | Effect |
|--------------------|--------|
| `sor_lotting` only | `bid_ids`, `bid_count`, and Bids tab are absent from lot forms |
| `sor_contact_roles` only | No effect on lots; Bidder contact type seeded but unused by lots |
| `sor_lotting` + `sor_contact_roles` | `sor_bidding` auto-installs: Bids tab, stat button, hammer_price auto-population all active |
| `sor_bidding` + `sor_events` | No interaction — `sor_events` manages event metadata; `sor_bidding` manages per-lot bids independently |
| `sor_bidding` + `sor_business_model` | No interaction — business model suppression acts on product fields, not bid fields |
