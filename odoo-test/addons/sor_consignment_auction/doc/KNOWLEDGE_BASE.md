# sor_consignment_auction — Knowledge Base

## Overview

`sor_consignment_auction` is a bridge module that connects the consignment agreements layer (`sor_consignment_agreements`) with the auction document layer (`sor_auction_documents`). It activates automatically when both parent modules are installed.

When the bridge is active, the consignor on an auction lot is **resolved automatically** from physical intake records rather than entered manually. The resolution traverses a four-node chain:

```
sor.lot.product_id
  → stock.lot (serial, same product + company)
    → stock.picking (incoming, all states, serial in move_line_ids)
      → picking.agreement_id.agreement_type == 'consignment_in'
        → picking.agreement_id.primary_partner_id  =  consignor
```

The bridge provides three resolution entry points:

1. **At lot creation** — auto-populates `consignor_id` silently if the chain is complete
2. **Fetch Consignor button** — on-demand per-lot resolution with a success notification or a structured diagnostic for staff to act on
3. **Batch resolution before document generation** — runs automatically whenever Pre-Sale Advice, Post-Sale Advice, or Vendor Settlement generation is triggered on an event

**What this module does NOT do:**

- Generate PDF documents — it resolves consignors before calling `super()`, which remains a stub until D3b Stories 04–06
- Allow staff to edit `consignor_id` directly — the field is read-only in the lot form view when this bridge is installed; the Fetch Consignor / Refresh buttons are the only write mechanism
- Re-query lots that already have `consignor_id` set — batch population skips any lot with a non-empty consignor

**Auto-installs with:** `sor_consignment_agreements` + `sor_auction_documents` both present

---

## Key Fields and Models

This bridge introduces no new models. It adds behaviour to existing models via `_inherit`.

### Changes to sor.lot

| Field / Method | Type | Description |
|---------------|------|-------------|
| `_resolve_consignor()` | Method → `(partner\|False, reason\|None)` | Core traversal. Returns `(partner, None)` on success; `(False, reason_code)` on failure. Reason codes: `missing_serial`, `missing_movement`, `missing_consignment`. Called by at-create, by `action_fetch_consignor`, and by the event batch. |
| `action_fetch_consignor()` | Action method | On-demand resolution. On success: sets `consignor_id`, sends success bus notification, returns `False`. On failure: returns `display_notification` dict with sticky warning and structured diagnostic. |
| `create()` override | ORM hook | Auto-populates `consignor_id` after super().create() for any newly created lot where `product_id` is set and the chain resolves. Silent — no notification on auto-populate. |
| `consignor_id` view | View patch | Replaces the plain editable field from `sor_auction_documents` with a `label + div` layout: readonly field + conditional Fetch Consignor / Refresh buttons. |

### Changes to sor.event

| Method | Description |
|--------|-------------|
| `_resolve_consignors_for_event()` | Batch traversal: iterates `lot_ids`, skips lots with `consignor_id` already set, calls `_resolve_consignor()` on the rest. Returns `{'resolved': recordset, 'unresolved': [{lot, ref, reason}, ...]}`. |
| `_format_consignor_diagnostic(unresolved)` | Formats the unresolved list into a user-facing warning string listing each lot reference and its failure reason. |
| `_notify_consignor_gaps(unresolved)` | Sends a sticky bus notification when any lots remain unresolved after batch. No-op if `unresolved` is empty. |
| `action_generate_pre_sale_advices()` override | Calls batch resolution + gap notification, then `super()`. |
| `action_generate_post_sale_advices()` override | Same pattern. |
| `action_generate_vendor_settlements()` override | Same pattern. |

---

## Resolution Diagnostics

When `_resolve_consignor()` cannot resolve a consignor, it returns one of three reason codes. Staff see these as actionable messages in the Fetch Consignor warning notification or the batch gap notification:

| Reason code | Meaning | Message shown to staff |
|------------|---------|----------------------|
| `missing_serial` | No serial intake record exists for this lot's product | "No intake record found for this artwork. Add this artwork to a consignment intake movement and set the movement to Ready, then try again." |
| `missing_movement` | A serial exists but no incoming picking references it | "No incoming movement found for this artwork. Ensure a consignment intake movement has been created for this object." |
| `missing_consignment` | An incoming picking exists but is not linked to a Consignment In agreement | "An incoming movement exists but it is not linked to a Consignment In agreement. Open the movement and attach the relevant consignment agreement." |

---

## Configuration

No configuration is required. The bridge activates automatically and is transparent to staff once consignors are resolving correctly. To surface the Fetch Consignor button, the lot must be in Draft or Catalogued state.

**When the Fetch Consignor button is visible:** `consignor_id` is empty and lot state is `draft` or `catalogued`.
**When the Refresh icon button is visible:** `consignor_id` is already set and lot state is `draft` or `catalogued`.

---

## Developer Menu

This bridge adds no developer menu items.

---

## Building on this Module

Bridge modules that extend the consignment-auction layer should:

1. Depend on `sor_consignment_auction` if they need access to the resolved consignor at document-generation time.
2. Override `_resolve_consignors_for_event` if additional pre-generation checks are needed, calling `super()` first to preserve the core batch resolution.
3. Do not override `_resolve_consignor` — it is the single source of truth for the traversal chain. To extend the traversal (e.g. for a different intake agreement type), consider a separate resolution method and call both from the override.

---

## Regression Checks

**R1 — Consignor auto-populates at lot creation (chain complete):**
Create a lot whose product has a serial, an incoming consignment-in intake picking, and a linked consignment agreement with a primary partner. Confirm `consignor_id` is set immediately after save without any manual action.

**R2 — Fetch Consignor button appears when consignor is empty:**
Open a lot in Draft state with no consignor. Confirm the "Fetch Consignor" button is visible. Click it. Confirm consignor is resolved and a success notification appears.

**R3 — Refresh icon appears when consignor is already set:**
Open a lot in Draft state with a consignor already populated. Confirm the Refresh icon (not "Fetch Consignor") is visible. Click it. Confirm consignor is re-resolved.

**R4 — Diagnostic warning on failure:**
On a lot whose product has no intake movement, click Fetch Consignor. Confirm a sticky warning notification appears with a user-friendly message — it should reference "intake record" and must not mention `stock.lot` or "serial tracking enabled".

**R5 — Fetch Consignor buttons hidden in locked states:**
Open a lot in Sold, Passed, or Withdrawn state. Confirm neither the Fetch Consignor button nor the Refresh icon is visible.

**R6 — Batch resolution runs before Pre-Sale Advice generation:**
Open an auction event with at least one lot whose consignor is unresolved. Click Pre-Sale Advice. Confirm a sticky warning notification appears listing the unresolved lot(s) with their reason codes. Confirm lots that resolve are updated.

**R7 — Batch skips already-set consignors:**
On a lot with a manually assigned consignor, trigger Pre-Sale Advice generation. Confirm the lot's consignor is unchanged after the batch runs.

**R8 — Composability (standalone sor_auction_documents):**
Install `sor_auction_documents` without `sor_consignment_agreements`. Confirm `sor_consignment_auction` is not installed. Confirm the lot form shows an editable Consignor field with no buttons.

---

## Interoperability

| Module | Relationship | Effect |
|--------|-------------|--------|
| `sor_auction_documents` | Parent dependency | Provides `consignor_id` on `sor.lot` (editable, standalone); provides the three document action stubs on `sor.event` that this bridge overrides |
| `sor_consignment_agreements` | Parent dependency | Provides `agreement_id` on `stock.picking`; provides `agreement_type = 'consignment_in'`; ensures `sor_tracking` is in the chain (serial infrastructure) |
| `sor_tracking` | Transitive dependency (via `sor_consignment_agreements`) | Provides `stock.lot` serial infrastructure and incoming movement (stock.picking) records |
| D3b Stories 04–06 (planned) | Future extensions | PDF generation modules will call `super()` through this bridge's action overrides; batch resolution runs first, then PDF rendering proceeds against resolved `consignor_id` values |
