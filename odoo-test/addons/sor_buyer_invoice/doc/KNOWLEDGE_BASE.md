# SOR Buyer Invoice — Knowledge Base

## 1. Overview

**What it does:** Provides the business-model-agnostic event-invoice link layer. It adds an `Event` field (`sor_event_id`) to `account.move`, a smart button on the auction event form showing linked invoice count, a `PSRA Licence Number` field on `res.company`, and a regulatory footer on the invoice PDF (bank details, PSRA, company reg, VAT number) that appears on all invoices linked to an event.

**What it does NOT do:** It does not generate invoices, add lot fields, calculate buyer's premium, or render a lot breakdown table. All auction-specific invoice content belongs in `sor_buyer_invoice_auction_house`.

**Dependencies:** `sor_accounting`, `sor_events`

---

## 2. Key fields and models

| Model | Field | Type | Purpose |
|-------|-------|------|---------|
| `account.move` | `sor_event_id` | Many2one → `sor.event` | Links an invoice to the auction event it was generated for |
| `account.move` | `partner_ref` | Char (related) | Customer code from `partner_id.ref` — shown in invoice list view |
| `sor.event` | `invoice_count` | Integer (computed) | Count of `account.move` records linked to this event |
| `res.company` | `auction_psra_number` | Char | PSRA Licence Number — rendered in the invoice PDF regulatory footer |

---

## 3. Methods

| Model | Method | Description |
|-------|--------|-------------|
| `sor.event` | `action_view_buyer_invoices()` | Returns a window action opening all invoices with `sor_event_id = self.id` |
| `sor.event` | `_compute_invoice_count()` | Counts `account.move` records linked to this event via `search_count` |

---

## 4. Configuration

**PSRA Licence Number:** Settings → General Settings → scroll to the SOR — Auction House section. Enter the company's PSRA licence number. This appears in the regulatory footer on all event-linked invoice PDFs.

---

## 5. Developer menu

No SOR developer menu entries in this module.

---

## 6. Building on this module

`sor_buyer_invoice` provides the invoice-event link and the PDF footer anchor (`sor_auction_footer`). Bridge modules that add auction-specific invoice content should:

1. Depend on `sor_buyer_invoice` (and other parent modules as appropriate)
2. Add lot fields to `account.move` and `account.move.line` in the bridge
3. Extend `sor_buyer_invoice.report_invoice_document_sor_buyer_invoice` via XPath at `//div[@name='sor_auction_footer']` position="before" to insert content above the regulatory footer

The `sor_auction_footer` anchor is deliberately placed at the bottom of the PDF content area so bridge content always appears above the regulatory footer without needing to know the footer's internal structure.

---

## 7. Regression checks

**R1 — Invoices smart button on event:** Navigate to an auction event form. Confirm the "Buyer Invoices" stat button is visible and shows the correct count.

**R2 — Invoice links back to event:** Open a buyer invoice. Confirm the Event field shows the linked auction event name.

**R3 — Regulatory footer on PDF:** Print a buyer invoice linked to an event. Confirm the PDF footer contains bank details (if configured) and PSRA, Company Reg, and VAT numbers.

**R4 — Regulatory footer absent on non-event invoice:** Print a standard Odoo invoice with no `sor_event_id`. Confirm the SOR regulatory footer does not appear.

**R5 — Document type selector suppressed:** Open any buyer invoice form. Confirm there is no radio button or dropdown widget near the invoice title allowing staff to switch document types (Journal Entry / Customer Invoice / Credit Note / Vendor Bill etc.). The form should show only the invoice number without a type switcher.

**R6 — Receipts filter absent from search panel:** Navigate to Invoicing → Customers → Invoices. Open the search filter dropdown. Confirm "Receipts" is not listed as a selectable filter option — only "Invoices", "Credit Notes", and state/date filters should be present.

---

## 8. Interoperability

| Module | Interaction |
|--------|------------|
| `sor_accounting` | Parent — ensures `account` module present and GL surface configured |
| `sor_events` | Parent — provides `sor.event` model that `sor_event_id` references |
| `sor_buyer_invoice_auction_house` | Bridge — depends on this module; adds lot fields, generate button, lot breakdown PDF on top of the link layer this module provides |
