# SOR Consignment Agreements — Knowledge Base

## 1. Overview

`sor_consignment_agreements` is a Level 1 bridge module that activates when both `sor_legal_agreement` and `sor_tracking` are installed. It introduces two new agreement types — **Consignment In** and **Consignment Out** — and connects the legal agreement lifecycle to the physical movement infrastructure provided by `sor_tracking`.

**What this module does:**
- Adds Consignment In and Consignment Out as selectable agreement types on `sor.agreement`
- Provides "Receive Artwork" and "Release Artwork" pre-signing movement buttons
- Links `stock.picking` records (intake and dispatch movements) to their source agreements
- Computes a compound status ("Active | Consigned out") on a source In agreement when its artwork has been dispatched under a linked Out agreement
- Renders consignment-specific sections on the agreement PDF (source consignment reference, product lines)

**What this module does NOT do:**
- Artist Studio source paths (deferred to `sor_consignment_agreements_locations_external`, Level 3 bridge)
- Intermediate lifecycle states (`partial_return`, `returned`, `sold`) — deferred to business-model bridges
- Financial settlement or invoice generation — deferred to the Sales sprint
- Serial number / lot assignment on consignment movements — handled by `sor_tracking_artwork` automatically when installed

**Dependencies:**
- `sor_legal_agreement` — provides `sor.agreement`, `sor.agreement.line`, `agreement_id` on `stock.picking`, and the agreement lifecycle (draft → pending signature → active → closed / revoked)
- `sor_tracking` — provisions Partners/External pool location, MVI/MVO operation types, and the four-state movement lifecycle

---

## 2. Key fields and models

All additions are extensions to existing models via `_inherit`.

### `sor.agreement` extensions

| Field | Type | Purpose | Default |
|-------|------|---------|---------|
| `agreement_type` | Selection (add) | Adds `consignment_in` and `consignment_out` values | Inherited |
| `source_consignment_id` | Many2one → `sor.agreement` | Links a Consignment Out to its originating Consignment In. Optional — standalone Out agreements are valid | — |
| `picking_count` | Integer (computed) | Count of linked `stock.picking` records. Drives the Movements stat button | `store=False` |
| `move_ids` | One2many (computed) | Flat list of all `stock.move` records across all linked pickings. Read-only display in Movements tab | `store=False` |
| `sor_compound_status` | Char (computed) | Displays "Active \| Consigned out" on an active Consignment In agreement when any linked Out agreement has a confirmed picking. Empty otherwise | `store=False` |

### `stock.picking` extensions

| Method | Purpose |
|--------|---------|
| `action_open_picking_modal()` | Returns a modal (`target: 'new'`) action to open this picking in a popup from the agreement Movements tab |
| `_action_done()` (override) | After the native validation, invalidates `sor_compound_status` on the source In agreement so the compound status recomputes on next read |

---

## 3. Methods

### `_get_partner_location(partner, direction)`

**Signature:** `_get_partner_location(self, partner: res.partner, direction: str) -> stock.location`

**Purpose:** Returns the external location to use as source (Consignment In) or destination (Consignment Out) for a consignment movement. The default Level 1 implementation returns the Partners/External pool location provisioned by `sor_tracking` for the agreement's company.

**Direction argument:** `'in'` for artwork arriving (Consignment In intake) or `'out'` for artwork leaving (Consignment Out dispatch). The direction is accepted for forward compatibility with the Level 3 bridge override but not used in the default implementation.

**Override point:** `sor_consignment_agreements_locations_external` (Level 3 bridge) overrides this method to check for contact-linked external locations first, falling back to Partners/External.

**Raises:** `UserError` if Partners/External pool location is not found for the agreement's company.

---

### `action_receive_artwork()`

**Purpose:** Creates a Receipt (MVI) intake picking pre-signed on a Consignment In agreement.

**Guard:** Raises `UserError` if `state not in ('draft', 'pending_signature')`. Does NOT call `_check_can_trigger_movement` (that base method enforces Active state — the opposite of the required constraint here).

**Picking type:** Explicit lookup — `stock.picking.type` where `code='incoming'` and `warehouse_id.company_id = self.company_id`. The `_sor_infer_picking_type_id` method is not used because Partners/External has `usage='internal'` and would produce an MVT (Internal Transfer) instead of MVI.

**Source location:** `_get_partner_location(primary_partner_id, 'in')` → Partners/External pool.

**Destination location:** `picking_type.default_location_dest_id` → warehouse Stock/Input.

**Moves:** One `stock.move` per `sor.agreement.line`, quantity 1, product from the line.

**Return:** Modal action (`target: 'new'`) opening the created picking.

---

### `action_release_artwork()`

**Purpose:** Creates a Dispatch (MVO) release picking pre-signed on a Consignment Out agreement.

**Guard:** Same as `action_receive_artwork` — `state not in ('draft', 'pending_signature')`.

**Picking type:** Explicit lookup — `stock.picking.type` where `code='outgoing'` and `warehouse_id.company_id = self.company_id`.

**Source location:** `picking_type.default_location_src_id` → warehouse Stock.

**Destination location:** `_get_partner_location(primary_partner_id, 'out')` → Partners/External pool.

**Moves:** One `stock.move` per `sor.agreement.line`, quantity 1.

**Return:** Modal action (`target: 'new'`) opening the created picking.

---

### `action_link_existing_intake()` / `action_link_existing_release()`

**Purpose:** Opens a filtered list of existing pickings so staff can link a picking to an agreement retrospectively — for cases where artwork arrived or departed before the agreement paperwork was completed.

**Guard:** Same pre-signing state guard as the create actions.

**Filter:** Receipt pickings only (Intake) or Delivery pickings only (Release), scoped to the agreement's company, showing unlinked pickings plus any already linked to this agreement.

**Return:** Window action (`target: 'new'`).

---

### `sor_compound_status` computed field

**Trigger:** `@api.depends('agreement_type', 'state')` — minimal declared dependency. The `stock.picking._action_done` override explicitly invalidates the field after a release picking is confirmed, which causes recomputation on next read without a stored write.

**Logic:** For an active `consignment_in` agreement, searches for any linked `consignment_out` agreements (`source_consignment_id = self`) that have at least one `done` picking. If found, returns `'Active | Consigned out'`; otherwise returns `False`.

---

## 4. Configuration

No module-level configuration is required. The bridge installs automatically when both parent modules are installed. The Partners/External pool location is provisioned by `sor_tracking`'s `post_init_hook` — no manual setup is needed.

**Navigation path (Odoo browser):**
- Agreements: **Legal → Agreements**
- Create a new agreement: click **New**, set **Agreement Type** to Consignment In or Consignment Out
- "Receive Artwork" button: visible in the action bar on Draft and Pending Signature Consignment In agreements
- "Release Artwork" button: visible in the action bar on Draft and Pending Signature Consignment Out agreements
- Movements stat button: top of form (control panel area), visible for consignment agreement types
- Compound status: below the statusbar on an Active Consignment In agreement with confirmed out-pickings

---

## 5. Developer menu

No SOR Technical developer menu entries are added by this module.

---

## 6. Building on this module

**Level 2 bridge — `sor_consignment_agreements_artwork`** (planned):
- Depends on `sor_consignment_agreements` + `sor_artwork`
- Will add artwork-specific columns to the Movements tab (serial number traceability, artwork links)
- Will extend the PDF with artwork metadata

**Level 3 bridge — `sor_consignment_agreements_locations_external`** (planned):
- Depends on `sor_consignment_agreements` + `sor_locations_external`
- Overrides `_get_partner_location` to return a contact-linked external location when one exists (e.g. Artist Studio), falling back to Partners/External
- Implement the override as `_inherit = 'sor.agreement'` with a new `_get_partner_location` that calls `partner.sor_external_location_id` before falling back to `super()`

**Business-model bridges** (planned, deferred from Sprint 16):
- Intermediate lifecycle states (`partial_return`, `returned`, `sold`) are deferred to gallery/auction-house business-model bridges
- These bridges will use `selection_add` on the `state` field with appropriate `ondelete` policies
- See Sprint Findings A05 for the rationale

---

## 7. Regression checks

| # | Step | Expected result |
|---|------|----------------|
| R1 | Open a **Base Agreement** type record | No Movements tab, no Source Consignment field, no action buttons — Lines tab visible |
| R2 | Open a **Consignment In** agreement in Draft state | Movements tab visible, Lines tab hidden, **Receive Artwork** and **Link Existing Intake** buttons in action bar |
| R3 | Advance Consignment In to Active | **Receive Artwork** and **Link Existing Intake** buttons disappear |
| R4 | Click **Receive Artwork** on a Draft Consignment In with one agreement line | Picking opens in modal; picking type = Receipts (MVI); source = Partners/External; dest = WH/Stock; 1 move for the product |
| R5 | Confirm the intake picking | Movements stat button on the agreement increments; picking visible in Movements tab |
| R6 | Open a **Consignment Out** agreement in Draft state | Source Consignment field visible; **Release Artwork** and **Link Existing Release** buttons in action bar |
| R7 | Click **Release Artwork** on a Draft Consignment Out with one agreement line | Picking opens in modal; picking type = Delivery Orders (MVO); source = WH/Stock; dest = Partners/External; 1 move |
| R8 | Confirm the release picking when Out agreement has source_consignment_id set | Source In agreement shows **"Active \| Consigned out"** in status area |
| R9 | Install `sor_consignment_agreements` without `sor_tracking` | Module does not install |
| R10 | Install `sor_consignment_agreements` without `sor_legal_agreement` | Module does not install |

---

## 8. Interoperability

| Installed combination | Result |
|-----------------------|--------|
| `sor_legal_agreement` only | `sor_consignment_agreements` does not install. Base Agreement type works as normal. |
| `sor_tracking` only | `sor_consignment_agreements` does not install. Movement infrastructure works as normal. |
| Both `sor_legal_agreement` + `sor_tracking` | `sor_consignment_agreements` auto-installs. Consignment In and Out types available. Movements linked to agreements. |
| + `sor_tracking_artwork` | Serial number column in Movements tab populated automatically for artwork products. No additional bridge code needed. |
| + `sor_consignment_agreements_locations_external` (planned Level 3) | `_get_partner_location` returns contact-linked external location instead of Partners/External pool where available. |
| + business-model bridge (planned) | Intermediate lifecycle states (`partial_return`, `returned`, `sold`) added via `selection_add`. |
