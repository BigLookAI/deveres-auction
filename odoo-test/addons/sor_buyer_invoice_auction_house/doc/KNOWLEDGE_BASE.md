# SOR Buyer Invoice × Auction House — Knowledge Base

## 1. Overview

**What it does:** Activates all auction-house-specific invoice functionality. When both `sor_buyer_invoice` and `sor_commercial_auction_house` (and `sor_bidding`) are installed, this bridge auto-installs and adds:
- An **Auction Sales journal** (code `AUC`) provisioned per company
- A **per-company buyer invoice sequence** (code `sor.buyer.invoice`)
- A **Generate Buyer Invoices** button on the auction event form
- Lot fields on `account.move` (`sor_lot_ids`) and `account.move.line` (`sor_lot_id`, `sor_line_type`, `sor_buyers_premium_pct`)
- Invoice number format: `{sequential}/{sale_number}` (e.g. `100109/A132`)
- **Buyer's premium lines** computed from `sor.lot.buyers_premium_pct`
- **Lot breakdown table** in the invoice PDF with Hammer, Buyer's Premium columns
- **VAT treatment columns** (VAT indicator M-, VAT on Hammer) when `company.hammer_price_vat_included` is True
- **Statutory VAT notice** text from `company.auction_vat_notice`
- **Duplicate invoice guard**: generating invoices for an event that already has invoices raises a UserError

**What it does NOT do:** It does not modify the base `sor_buyer_invoice` module. Gallery invoice formatting is a separate future bridge. Lot-to-agreement linking is D2 scope.

**Dependencies:** `sor_buyer_invoice`, `sor_commercial_auction_house`, `sor_bidding`
**Auto-installs:** Yes — when all three parents are installed.

---

## 2. Key fields and models

| Model | Field | Type | Purpose |
|-------|-------|------|---------|
| `account.move` | `sor_lot_ids` | Many2many → `sor.lot` | Links an invoice to the lots it covers |
| `account.move.line` | `sor_lot_id` | Many2one → `sor.lot` | The specific lot this line represents |
| `account.move.line` | `sor_line_type` | Selection (`hammer` / `buyers_premium`) | Identifies whether the line is a hammer price or a buyer's premium |
| `account.move.line` | `sor_buyers_premium_pct` | Float | The rate applied when this premium line was generated |
| `account.journal` | AUC journal | Provisioned record | `type=sale`, `code=AUC`, one per company — used for all buyer invoices |
| `ir.sequence` | `sor.buyer.invoice` | Provisioned record | Per-company sequential counter for invoice numbers |

---

## 3. Methods

| Model | Method | Description |
|-------|--------|-------------|
| `sor.event` | `action_generate_buyer_invoices()` | Finds winning bids, groups by buyer, calls `_prepare_buyer_invoice_lines`, creates one `account.move` per buyer, assigns invoice number |
| `sor.event` | `_prepare_buyer_invoice_lines(lots, buyer)` | Returns `(0, 0, {...})` command tuples for hammer lines and buyer's premium lines; designed as an extension point for bridge overrides |

---

## 4. Configuration

**Auction Sales journal:** The AUC journal is provisioned automatically on install with `default_account_id` set to the company's primary income account (the first `account_type = 'income'` account associated with the company). No manual journal configuration is required after a standard install with a chart of accounts applied.

**Hammer Price VAT Scheme:** Settings → General Settings → SOR — Auction House → enable `Hammer Price VAT Included`. When enabled, the invoice PDF shows the VAT indicator (M-), VAT on Hammer column (displays €0.00), and the VAT notice text.

**VAT Notice Text:** Settings → General Settings → SOR — Auction House → `Auction VAT Notice`. Enter the statutory notice text verbatim. Rendered on the PDF when `Hammer Price VAT Included` is enabled and the notice field is non-empty.

---

## 5. Generating buyer invoices

1. Navigate to an auction event with winning bids recorded.
2. Click **Generate Buyer Invoices**.
3. One invoice per buyer is created, covering all lots that buyer won.
4. Invoice numbers are assigned immediately in format `{sequential}/{sale_number}`.
5. The action redirects to the invoice list filtered to this event.

If invoices already exist for the event, a `UserError` is raised: "Buyer invoices have already been generated for this auction. Delete the existing invoices first to regenerate."

---

## 6. Building on this module

The `_prepare_buyer_invoice_lines(lots, buyer)` method on `sor.event` is the designated extension point. A future gallery invoice bridge can override this method via `_inherit` to change line structure without modifying `action_generate_buyer_invoices`.

The PDF template `report_invoice_document_sor_auction_house_bridge` inherits `sor_buyer_invoice.report_invoice_document_sor_buyer_invoice`. Further PDF extensions should inherit from this bridge template (not from the base) if they need to add content within the lot breakdown context.

---

## 7. Regression checks

**R1 — AUC journal exists after install:** Settings → Invoicing → Journals. Confirm "Auction Sales" journal with code AUC is present.

**R2 — Generate button appears on event with winning bids:** Navigate to an auction event with at least one `is_winning_bid=True` bid. Confirm "Generate Buyer Invoices" button is visible.

**R3 — Generate button absent with no winning bids:** Navigate to an auction event with no winning bids. Confirm the button is absent.

**R4 — Invoice number format:** Generate invoices for an event with a `sale_number` set. Open the created invoice. Confirm the name matches `{NNN}/{sale_number}` format.

**R5 — Lot breakdown table on PDF:** Print a generated invoice. Confirm the PDF shows the lot breakdown table with Lot No, Description, Hammer, and Buyer's Premium columns.

**R6 — Duplicate guard:** Click "Generate Buyer Invoices" on an event that already has invoices. Confirm a UserError is shown.

---

## 8. Interoperability

| Module | Interaction |
|--------|------------|
| `sor_buyer_invoice` | Parent — provides event-invoice link, PDF footer anchor; this bridge extends `_prepare_buyer_invoice_lines` |
| `sor_commercial_auction_house` | Parent — provides `hammer_price_vat_included`, `auction_vat_notice` on `res.company`; `sor.lot.buyers_premium_pct`; `sor.lot.hammer_price` |
| `sor_bidding` | Parent — provides `sor.bid.is_winning_bid`, `sor.bid.bidder_id` for identifying winning buyers |
| `sor_consignment_agreements_auction_house` | Sibling bridge — both auto-install when their respective parent sets are present; no direct dependency |
