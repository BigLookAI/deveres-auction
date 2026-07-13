# sor_lotting_contact_roles — Knowledge Base

## 1. Overview

**What it does:** Bridge module that connects `sor_lotting` and `sor_contact_roles`. When both parent modules are installed, it:

- Adds a **Consigned Lots** smart button and notebook tab to the contact form, showing all lots for which the contact is the consignor (scoped to the current company).
- Automatically assigns the **Consignor** earned sub-type (`sor.contact.type` with `code='consignor'`) to any partner set as `consignor_id` on a `sor.lot` — at create time, on `consignor_id` change, and retroactively for existing lots on first install.
- Automatically assigns the **Buyer** earned sub-type (`sor.contact.type` with `code='buyer'`) to any partner set as `buyer_id` on a `sor.lot` — at create time and on `buyer_id` change. This covers the fallback path for deployments without `sor_bidding`, where `buyer_id` is set directly on the lot. When `sor_bidding` is installed, buyer sub-type assignment is handled by `sor_bidding` via `sor.bid` create.

**What it does NOT do:**

- Does not create new Odoo models (no new DB tables).
- Does not modify the lot state machine or lifecycle.
- Does not remove the Consignor or Buyer sub-type if a partner is later removed from a lot — sub-type assignment reflects historical activity (activity-earned pattern).
- Does not display a Consigned Lots tab for contacts with no consigned lots (tab and smart button are both hidden when `consigned_lot_count = 0`).

**Dependencies:** `sor_lotting` (provides `sor.lot` with `consignor_id`), `sor_contact_roles` (provides `sor.contact.type` and `contact_subtypes`).

**Auto-install:** Yes — activates automatically when both parents are installed.

---

## 2. Key Fields and Models

### On `res.partner`

| Field | Type | Purpose | Default |
|-------|------|---------|---------|
| `consigned_lot_count` | `Integer` (computed, `store=False`) | Count of lots where this partner is consignor, scoped to current company. Always recomputed from DB — never cached. | 0 |
| `consigned_lot_ids` | `One2many` → `sor.lot` (via `consignor_id`) | Inline list of consigned lots. Used for the notebook tab display only. | — |

### On `sor.lot` (inherited)

No new fields. The bridge adds `create` and `write` overrides to call `_assign_consignor_subtype()` when `consignor_id` is set and `_assign_buyer_subtype()` when `buyer_id` is set.

---

## 3. Methods

### `res.partner._compute_consigned_lot_count()`

- **Signature:** `def _compute_consigned_lot_count(self)`
- **Returns:** Sets `consigned_lot_count` on each partner in the recordset.
- **Behaviour:** Runs `search_count` on `sor.lot` filtered by `consignor_id = partner.id` and `company_id = self.env.company.id`.
- **Performance:** O(n) DB queries for n partners. Suitable for form views and stat button counts. Not suitable for grouping across large partner lists.

### `res.partner.action_view_consigned_lots()`

- **Signature:** `def action_view_consigned_lots(self)`
- **Returns:** `dict` — `ir.actions.act_window` opening `sor.lot` list + form, domain filtered to this consignor and current company. Sets `default_consignor_id` in context.
- **Called by:** The smart button on the partner form (`type="object"`).

### `sor.lot._assign_consignor_subtype()`

- **Signature:** `def _assign_consignor_subtype(self)`
- **Returns:** None.
- **Behaviour:** Searches for `sor.contact.type` with `code='consignor'` and `parent_type_id != False`. For each lot in `self` where `consignor_id` is set, assigns the sub-type to the partner via `[(4, id)]` if not already present. Fully idempotent.
- **If the sub-type is not found** (e.g. `sor_contact_roles` demo data not loaded): returns silently without assigning.

### `sor.lot._assign_buyer_subtype()`

- **Signature:** `def _assign_buyer_subtype(self)`
- **Returns:** None.
- **Behaviour:** Searches for `sor.contact.type` with `code='buyer'` and `parent_type_id != False`. For each lot in `self` where `buyer_id` is set, assigns the Contact parent type and Buyer sub-type to the partner via `[(4, id)]` if not already present. Fully idempotent.
- **When `sor_bidding` is installed:** `buyer_id` is hidden from the lot form; this method still fires if `buyer_id` is set programmatically, but that path is not used in the bidding deployment.

### `sor.lot.create()` / `sor.lot.write()` (overrides)

Overrides that call `_assign_consignor_subtype()` and `_assign_buyer_subtype()` after the record is created or after `consignor_id` / `buyer_id` changes. The `write` override fires each assignment only when the relevant field appears in `vals`.

---

## 4. Configuration

No manual configuration required. The bridge activates automatically.

The Consignor sub-type must exist in `sor.contact.type` for sub-type assignment to occur. This record is part of `sor_contact_roles` demo/data — verify via: **Settings → Technical → Contact Types** (developer mode).

---

## 5. Developer Menu

None. This module adds no developer menu entries.

---

## 6. Building on This Module

Bridges that extend the consignor relationship further should:

1. Read `consigned_lot_count` and `consigned_lot_ids` from `res.partner` directly — these fields are available whenever this bridge is installed.
2. Call `lot._assign_consignor_subtype()` if your bridge adds a new code path that sets `consignor_id` without going through the standard `sor.lot.create/write` (e.g. a batch import). The method is idempotent.
3. Use `('consignor_id', '!=', False)` on `sor.lot` to find all lots with a consignor. Add a `company_id` filter for company-scoped counts.

Do **not** add a second `post_init_hook` in another bridge to assign the Consignor sub-type — this bridge already owns that retroactive assignment on install.

---

## 7. Regression Checks

**R1 — Smart button visible for consignors.**
Navigate to **Contacts**, open a partner who is set as `consignor_id` on at least one lot. Confirm:
- A gavel smart button labelled "Lots" with a count > 0 appears in the button box.
- Clicking the button opens a lot list filtered to this consignor and the current company.

**R2 — Consignor sub-type assigned on lot creation.**
Navigate to **Lots → New**. Set a partner as the consignor. Save. Navigate to the partner's contact form. Confirm the partner's contact sub-types include "Consignor".

**R3 — Smart button absent for non-consignors.**
Navigate to **Contacts**, open a partner with no consigned lots. Confirm:
- No gavel smart button is present.
- No "Consigned Lots" notebook tab is visible.

**R4 — Consigned Lots tab shows correct lots.**
Navigate to **Contacts**, open a partner with consigned lots. Click the "Consigned Lots" tab. Confirm the inline list shows the correct lots with columns: Lot Reference, Lot No., Item, State, Hammer Price (default-visible, added Auction Refinements 01 Story 2).

**R5 — Sub-type assigned on consignor_id write.**
Navigate to **Lots**, open an existing lot with no consignor. Edit: set the consignor to a partner. Save. Navigate to the partner form. Confirm the Consignor sub-type is now present.

**R6 — Buyer sub-type assigned when buyer_id is set (fallback path — BUG-U17).**
In a deployment without `sor_bidding`: navigate to **Lots**, open a Sold lot. Set `buyer_id` to a test partner. Save. Navigate to that partner's contact form. Under System-Assigned Roles, confirm the `Buyer` sub-type and `Contact` parent type are now visible.

---

## 8. Interoperability

| Module | Interaction |
|--------|------------|
| `sor_lotting` | Reads `sor.lot.consignor_id`; overrides `sor.lot.create/write` |
| `sor_contact_roles` | Reads `sor.contact.type` (code=consignor); writes to `res.partner.contact_subtypes` |
| `sor_lotting_tracking` | No direct interaction; both bridges independently extend `sor.lot` |
| `sor_commercial_auction_house` | No direct interaction; `consignor_id` is owned by `sor_lotting` |
| `sor_events_auction` | No interaction |
