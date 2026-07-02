# sor_auction_documents — Knowledge Base

## Overview

`sor_auction_documents` delivers the full document production layer for auction houses. It is a non-auto-install feature module that sits above the commercial fee layer (`sor_commercial_auction_house`) and provides:

- **Pre-Sale Advice** — generated before the auction; one document per consignor per event; lists lots with estimate and reserve price; sent by email
- **Post-Sale Advice** — generated after the auction; lists sold and passed lots with hammer prices; margin scheme annotation (M-); sent by email
- **Vendor Settlement Statement (VSS)** — formal financial statement; per-lot commission deductions; grand totals; four-state lifecycle; bulk-send list action
- **Consignor identity** on `sor.lot` — the `consignor_id` field that all three documents address
- **Company-level settings** — auction sale terms, bank details, licence reference, director signature

**What this module does NOT do:**

- Auto-populate `consignor_id` from consignment intake records — that is `sor_consignment_auction` (auto-installs when `sor_consignment_agreements` is also present)
- Enforce a required consignor — the field is optional; staff can leave it blank
- Create `account.move` records — VSS is a PDF statement only; self-billing invoice compliance is deferred (Gap 06)
- Calculate DdS (Droit-de-Suite) levy — deferred (Gap 02)

**Depends on:** `sor_commercial_auction_house` (lots, events, fee layer, margin scheme flag), `sor_bidding` (bid model)

---

## Key Fields and Models

### sor.pre.sale.advice

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char (computed, stored) | Auto-computed reference: `PSA/{sale_number}/{consignor.ref or consignor.id}` |
| `event_id` | Many2one `sor.event` | The auction event this document belongs to |
| `consignor_id` | Many2one `res.partner` | The consignor this advice is addressed to |
| `company_id` | Many2one `res.company` | Required; defaults to current company |
| `lot_ids` | One2many `sor.lot` | Lots linked via `sor.lot.pre_sale_advice_id`; catalogued or live lots for this event+consignor |

### sor.post.sale.advice

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char (computed, stored) | Auto-computed: `PSA-POST/{sale_number}/{consignor.ref or consignor.id}` |
| `event_id` | Many2one `sor.event` | The auction event |
| `consignor_id` | Many2one `res.partner` | The consignor |
| `company_id` | Many2one `res.company` | Required; defaults to current company |
| `lot_ids` | One2many `sor.lot` | Sold and passed lots for this event+consignor (via `post_sale_advice_id`) |

### sor.vendor.settlement

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char | Combined reference `{seq}/{sale_number}` (e.g. `100001/A133`) built at creation from the per-company sequence and `event_id.sale_number`; falls back to raw sequence number if sale_number is absent |
| `state` | Selection | `draft` → `payment_confirmed` → `sent`; or `draft` → `cancelled` |
| `event_id` | Many2one `sor.event` | The auction event |
| `consignor_id` | Many2one `res.partner` | The consignor |
| `company_id` | Many2one `res.company` | Required; defaults to current company |
| `currency_id` | Related to `company_id.currency_id` | Used by Monetary widgets |
| `lot_ids` | One2many `sor.lot` | Sold and passed lots (via `vendor_settlement_id`) |
| `total_hammer` | Monetary (computed) | Sum of `lot_ids.hammer_price` |
| `total_commission` | Monetary (computed) | Sum of `lot.hammer_price × lot.sellers_commission_pct / 100` |
| `net_proceeds` | Monetary (computed) | `total_hammer − total_commission` |

### Fields added to sor.lot

| Field | Type | Description |
|-------|------|-------------|
| `consignor_id` | Many2one `res.partner` | Optional. `check_company=True`. Editable in Draft/Catalogued; read-only in Sold/Passed/Withdrawn. |
| `hammer_price_vat_included` | Boolean | Margin scheme flag. Defaults from `company.hammer_price_vat_included`. Controls M- annotation in PDFs. |
| `pre_sale_advice_id` | Many2one `sor.pre.sale.advice` | Back-reference set by batch generation. `copy=False`. |
| `post_sale_advice_id` | Many2one `sor.post.sale.advice` | Back-reference set by batch generation. `copy=False`. |
| `vendor_settlement_id` | Many2one `sor.vendor.settlement` | Back-reference set by batch generation. `copy=False`. |

### Fields added to res.company

| Field | Type | Description |
|-------|------|-------------|
| `auction_sale_terms` | Html | Rich-text terms printed on Pre-Sale Advice, Post-Sale Advice, and VSS PDFs |
| `auction_bank_details` | Text | Bank account details printed on Vendor Settlement Statements |
| `auction_licence_ref` | Char | e.g. `PSRA Licence No. 002261` — printed in PDF footers |
| `auction_director_signature` | Text | e.g. `Rory Guthrie, Director` — printed as sign-off block in PDFs |

---

## Methods

### On sor.event

| Method | Description |
|--------|-------------|
| `action_generate_pre_sale_advices()` | Creates one `sor.pre.sale.advice` per consignor with lots in `catalogued` or `live` state. Re-run refreshes lot assignments for Draft records. Blocked on `closed`/`archived` events. Returns list action. |
| `action_send_all_pre_sale_advices()` | Renders PDF for each Pre-Sale Advice linked to this event; posts via `message_post()` to consignors with email addresses. |
| `action_generate_post_sale_advices()` | Creates one `sor.post.sale.advice` per consignor with lots in `sold` or `passed` state. Only available on `active`/`closed` events. |
| `action_send_all_post_sale_advices()` | Batch email for Post-Sale Advices. Same pattern as Pre-Sale batch send. |
| `action_generate_vendor_settlements()` | Creates one `sor.vendor.settlement` per consignor with sold/passed lots. Re-run updates Draft VSSes only; Payment Confirmed/Sent/Cancelled are left untouched. |
| `action_view_pre_sale_advices()` | Smart button action — returns filtered list for this event. |
| `action_view_post_sale_advices()` | Smart button action — returns filtered list for this event. |
| `action_view_vendor_settlements()` | Smart button action — returns filtered list for this event. |

### On sor.pre.sale.advice / sor.post.sale.advice

| Method | Description |
|--------|-------------|
| `action_send_by_email()` | Renders PDF, creates attachment, opens `mail.compose.message` wizard pre-populated with consignor email and PDF attachment. |

### On sor.vendor.settlement

| Method | Description |
|--------|-------------|
| `action_confirm_payment()` | Transitions `draft` → `payment_confirmed`. |
| `action_send_by_email()` | Transitions `payment_confirmed` → `sent`; renders PDF, opens email compose wizard. |
| `action_cancel()` | Transitions `draft` → `cancelled`. Irreversible from the UI — generates a new VSS if cancellation was in error. |
| `action_bulk_mark_sent()` | List action. Filters selected records to `payment_confirmed`; renders PDF for each; posts via `message_post()`; transitions to `sent`. |

---

## Configuration

**Navigation:** Settings → General Settings → scroll to the **Auction Documents** section (visible only when company business model is `auction_house`; located below the Buyer's Premium / Vendor Fee Schedule block)

| Setting | Field | Notes |
|---------|-------|-------|
| Auction Sale Terms | `auction_sale_terms` | HTML rich text. Printed on all three consignor-facing PDFs. |
| Bank Account Details | `auction_bank_details` | Plain text. Enter with actual newlines (not `\n`). Printed on VSS. |
| Hammer Price VAT Included | `hammer_price_vat_included` | Boolean. Company-wide default for new lots. Individual lots can override. |
| Auction VAT Notice | `auction_vat_notice` | Plain text. Printed on buyer invoices when margin scheme applies. Leave blank to suppress. |
| Auction Licence Reference | `auction_licence_ref` | Plain text. e.g. `PSRA Licence No. 002261`. Printed in PDF footers. |
| Director Signature | `auction_director_signature` | Plain text. e.g. `Rory Guthrie, Director`. Printed as sign-off block. |

**`report.url` system parameter:** Must be set to `http://localhost:8069` (internal container URL) for wkhtmltopdf to fetch CSS correctly. Set via Settings → Technical → Parameters → System Parameters → `report.url`.

---

## Developer Menu

This module adds no developer menu items. All configuration is in General Settings.

---

## Building on this Module

### Bridge modules that need to override document generation

`sor_consignment_auction` (delivered) wraps all three `action_generate_*` methods to auto-populate `consignor_id` before document records are created. New bridges that need to extend document generation must call `super()` so the chain is preserved.

### Adding new document types

Follow the `sor.pre.sale.advice` pattern:
1. Define a model with `_inherit = ['mail.thread', 'mail.activity.mixin']`; `_check_company_auto = True`; `company_id`; `event_id`; `consignor_id`; `lot_ids` (One2many via a back-reference on `sor.lot`)
2. Add an `action_generate_*` stub method on `sor.event` here; implement it in the child module
3. PDF rendering: `report._render_qweb_pdf(report.id, [record.id])` — use the report record's integer ID as the first argument (not the record itself; not the XML ID)
4. Batch send: `message_post()` with the PDF as an `ir.attachment`
5. Smart button on the event form via view inheritance

### _render_qweb_pdf call pattern (Odoo 19)

```python
report = self.env.ref('sor_auction_documents.action_report_sor_pre_sale_advice')
pdf_content, _content_type = report._render_qweb_pdf(report.id, [record.id])
```

The integer ID path in `_get_report` bypasses the `isinstance(models.Model)` check which is not reliable in all environments. Do not pass the record object or the XML ID string directly as the first positional argument.

---

## Regression Checks

**R1 — Consignor field editable in Draft:**
Navigate to Lots. Open a lot in Draft state. Confirm the **Consignor** field is visible and editable in the Identification group (after Company field).

**R2 — Consignor field read-only after state transition:**
Open a lot in Sold or Passed state. Confirm the Consignor field is read-only.

**R3 — Hammer Price VAT Included defaults from company setting:**
Settings → General Settings → Auction Documents → tick "Hammer Price VAT Included" → Save. Create a new lot. Confirm the lot's Hammer Price VAT Included checkbox is already ticked.

**R4 — Auction Documents settings hidden for non-auction-house companies:**
Switch to a non-auction-house company. Open Settings → General Settings. Confirm the Auction Documents block is not visible.

**R5 — Pre-Sale Advice batch generation one record per consignor:**
Open an active or published auction event with catalogued lots assigned to a consignor. Click "Pre-Sale Advice". Confirm one record per consignor appears in the list.

**R6 — Pre-Sale Advice button invisible on closed events:**
Open a closed auction event. Confirm the "Pre-Sale Advice" button is not visible in the form header.

**R7 — Post-Sale Advice button invisible on published events:**
Open a published event. Confirm "Post-Sale Advice" is not visible. Open an active or closed event. Confirm it is visible.

**R8 — VSS lifecycle buttons correct per state:**
Draft VSS: "Confirm Payment" and "Void" visible; "Send to Consignor" hidden.
Payment Confirmed VSS: "Send to Consignor" visible; "Confirm Payment" and "Void" hidden.

**R9 — VSS totals correct:**
Open a VSS with multiple lots. Verify `total_hammer = Σ hammer_price`, `total_commission = Σ (hammer × rate/100)`, `net_proceeds = total_hammer − total_commission`.

**R10 — Re-run batch generation does not duplicate:**
Generate Pre-Sale Advices on an event. Click the button again. Confirm the same count of records exists (no duplicates).

**R11 — M- annotation on margin scheme lots:**
Set `hammer_price_vat_included = True` on a sold lot. Generate a Post-Sale Advice. Print the PDF. Confirm the lot shows `M-` after the hammer price.

---

## Interoperability

| Module | Relationship | Effect |
|--------|-------------|--------|
| `sor_commercial_auction_house` | Parent dependency | Provides `is_commercial` flag on events; provides `hammer_price_vat_included`, `auction_vat_notice`, `sellers_commission_pct` used by PDF templates |
| `sor_bidding` | Parent dependency | In dependency chain to ensure lot/bid layer is complete |
| `sor_consignment_auction` | Auto-installs bridge | Overrides `consignor_id` view to read-only+button; wraps batch generation actions to auto-populate consignors from intake pickings |
| `sor_lotting` | Transitive dependency | Provides `sor.lot` base model; `lot_reference`, `lot_number`, `state`, `auction_id` fields read by document logic |
| `sor_events_auction` | Transitive dependency | Provides `is_commercial` on `sor.event` and the lot→event relationship |
