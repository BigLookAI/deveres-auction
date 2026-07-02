# SOR Consignment Agreements × Auction House — Knowledge Base

## 1. Overview

**What it does:** Adds auction commercial terms to consignment agreements. When both `sor_consignment_agreements` and `sor_commercial_auction_house` are installed, this bridge auto-installs and adds an "Auction Terms" notebook page to the `sor.agreement` form with four fields: Catalogue Estimate, Reserve Price, Vendor Commission (%), and Vendor Commission (computed). It also extends the consignment agreement PDF with an "Auction Terms" section rendered before Terms and Conditions.

The Auction Terms page is only visible on `consignment_in` agreements (artworks consigned to the auction house by the vendor). It does not appear on `consignment_out` agreements.

**What it does NOT do:** It does not modify the consignment agreement lifecycle, state machine, or picking creation logic. `vendor_commission_amount` always returns 0.0 at MVP — full computation requires lot-linking (D2 scope). The PDF omits `vendor_commission_amount`.

**Dependencies:** `sor_consignment_agreements`, `sor_commercial_auction_house`
**Auto-installs:** Yes — when both parents are installed.

---

## 2. Key fields and models

| Model | Field | Type | Purpose |
|-------|-------|------|---------|
| `sor.agreement` | `currency_id` | Many2one → `res.currency` (related) | `related='company_id.currency_id'`, `store=False` — required for Monetary widget resolution |
| `sor.agreement` | `catalogue_estimate` | Monetary | Estimated catalogue value of the consigned artwork |
| `sor.agreement` | `reserve_price` | Monetary | Minimum acceptable hammer price agreed with the consignor |
| `sor.agreement` | `vendor_commission_pct` | Float `(5,2)` | Vendor commission rate as a percentage (e.g. 15.0 = 15.00%) |
| `sor.agreement` | `vendor_commission_amount` | Monetary (computed) | Always 0.0 at MVP; full computation pending lot-linking (D2) |

All four auction fields are optional — an agreement can be saved without entering any values.

---

## 3. Methods

| Model | Method | Description |
|-------|--------|-------------|
| `sor.agreement` | `_compute_vendor_commission_amount()` | Returns 0.0 for all agreements; `@api.depends('vendor_commission_pct')` |

---

## 4. Configuration

No configuration required. The bridge auto-installs when both parents are present.

---

## 5. Developer menu

No SOR developer menu entries in this module.

---

## 6. Building on this module

This bridge is purely additive. Future lot-linking (D2) will extend `_compute_vendor_commission_amount` to read `hammer_price` from linked lots. At that point `vendor_commission_amount` will need `store=False` to remain correct across lot updates.

The PDF section guard `t-if="doc.agreement_type == 'consignment_in' and (doc.catalogue_estimate or doc.reserve_price or doc.vendor_commission_pct)"` ensures the section is omitted when all user-editable fields are zero.

---

## 7. Regression checks

**R1 — Auction Terms page visible on consignment_in:** Open a `consignment_in` agreement. Confirm the "Auction Terms" notebook page is visible.

**R2 — Auction Terms page absent on consignment_out:** Open a `consignment_out` agreement. Confirm the Auction Terms page is not shown.

**R3 — Fields editable in draft/active, read-only in terminal states:** Set an agreement to `revoked` or `closed`. Confirm Catalogue Estimate, Reserve Price, and Vendor Commission (%) are read-only.

**R4 — PDF section renders with values:** Set Catalogue Estimate, Reserve Price, and Vendor Commission % on a `consignment_in` agreement. Print the PDF. Confirm an "Auction Terms" section appears before "Terms and Conditions" with the entered values.

**R5 — PDF section absent with no values:** Leave all three user-editable fields at 0.0. Print the PDF. Confirm no Auction Terms section appears.

**R6 — PDF omits zero Vendor Commission amount:** Enter a Vendor Commission % but no other auction values. Print the PDF. Confirm only the commission percentage row appears — no Vendor Commission monetary row (it would show €0.00).

---

## 8. Interoperability

| Module | Interaction |
|--------|------------|
| `sor_consignment_agreements` | Parent — provides `sor.agreement` model with `agreement_type`, `primary_partner_id`, form view, and PDF template; this bridge extends all three |
| `sor_commercial_auction_house` | Parent — its presence signals that auction commercial terms are relevant; no fields from this module are directly read by the bridge at MVP |
| `sor_legal_agreement` | Grandparent (via `sor_consignment_agreements`) — provides the agreement lifecycle and state values; terminal states `revoked` and `closed` are used in the form's `readonly` expressions |
