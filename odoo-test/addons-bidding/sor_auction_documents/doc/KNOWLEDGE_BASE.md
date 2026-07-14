# sor_auction_documents — Knowledge Base

## Overview

`sor_auction_documents` delivers the full document production layer for auction houses. It is a non-auto-install feature module that sits above the commercial fee layer (`sor_commercial_auction_house`) and provides:

- **Pre-Sale Advice** — generated before the auction; one document per consignor per event; lists lots with estimate and reserve price; sent by email via an editable `mail.template`, individually or in bulk
- **Post-Sale Advice** — generated after the auction; lists sold and passed lots with hammer prices; margin scheme annotation (M-); sent by email via an editable `mail.template`, individually or in bulk
- **Vendor Settlement Statement (VSS)** — formal financial statement; per-lot commission and Fixed Charges deductions; grand totals; four-state lifecycle; sent by email via an editable `mail.template`, individually or in bulk
- **Consignor identity** on `sor.lot` — the `consignor_id` field that all three documents address
- **Company-level content configuration** — a Top/Bottom rich-text content block per document type (six fields total), plus Odoo's native per-page footer (`company.report_footer`) for shared sign-off/licence content

**What this module does NOT do:**

- Auto-populate `consignor_id` from consignment intake records — that is `sor_consignment_auction` (auto-installs when `sor_consignment_agreements` is also present)
- Enforce a required consignor — the field is optional; staff can leave it blank
- Create `account.move` records — VSS is a PDF statement only; self-billing invoice compliance is deferred (Gap 06)
- Calculate DdS (Droit-de-Suite) levy — deferred (Gap 02)

**Depends on:** `sor_commercial_auction_house` (lots, events, fee layer, margin scheme flag), `mail` (chatter on document models)

---

## Key Fields and Models

### sor.pre.sale.advice

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char (computed, stored) | Auto-computed reference: `PSA/{sale_number}/{consignor.ref or consignor.id}` |
| `event_id` | Many2one `sor.event` | The auction event this document belongs to |
| `consignor_id` | Many2one `res.partner` | The consignor this advice is addressed to |
| `company_id` | Many2one `res.company` | Required; defaults to current company |
| `state` | Selection | `draft` (default) → `sent`; updated by `action_send_by_email()` (individual) or `action_bulk_send()` (bulk) — only when the document is genuinely dispatched (never lies about state when the consignor has no email) |
| `lot_ids` | One2many `sor.lot` | Lots linked via `sor.lot.pre_sale_advice_id`; catalogued or live lots for this event+consignor |

### sor.post.sale.advice

| Field | Type | Description |
|-------|------|-------------|
| `name` | Char (computed, stored) | Auto-computed: `PSA-POST/{sale_number}/{consignor.ref or consignor.id}` |
| `event_id` | Many2one `sor.event` | The auction event |
| `consignor_id` | Many2one `res.partner` | The consignor |
| `company_id` | Many2one `res.company` | Required; defaults to current company |
| `state` | Selection | `draft` (default) → `sent`; updated by `action_send_by_email()` (individual) or `action_bulk_send()` (bulk) — only when the document is genuinely dispatched |
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
| `total_fixed_charges` | Monetary (computed) | Sum of `lot_ids.fixed_charge_ids.amount` (Fixed Charges are provisioned by `sor_commercial_auction_house` — see that module's docs) |
| `net_proceeds` | Monetary (computed) | `total_hammer − total_commission − total_fixed_charges` |

### Fields added to sor.event

| Field | Type | Description |
|-------|------|-------------|
| `psa_pending_count` | Integer (computed, store=False) | Number of lots in catalogued/live state that have a consignor but no `pre_sale_advice_id` — i.e. PSAs not yet generated |
| `posa_pending_count` | Integer (computed, store=False) | Number of lots in sold/passed state that have a consignor but no `post_sale_advice_id` |
| `vss_pending_count` | Integer (computed, store=False) | Number of lots in sold/passed state that have a consignor but no `vendor_settlement_id` |
| `psa_count` | Integer (computed, store=False) | Total Pre-Sale Advice records for this event (smart button) |
| `posa_count` | Integer (computed, store=False) | Total Post-Sale Advice records for this event (smart button) |
| `vss_count` | Integer (computed, store=False) | Total Vendor Settlement Statement records for this event (smart button) |

The pending count fields drive the badge-style generation buttons on the event form — showing how many documents remain to be generated. A count of 0 indicates all eligible lots are already covered.

### Fields added to sor.lot

| Field | Type | Description |
|-------|------|-------------|
| `consignor_id` | Many2one `res.partner` | Optional. `check_company=True`. Editable in Draft/Catalogued; read-only in Sold/Passed/Withdrawn. |
| `vat_margin_scheme` | Boolean | Margin scheme flag. Defaults from `company.vat_margin_scheme` (field defined in `sor_commercial_auction_house`). Controls M- annotation in PDFs. |
| `pre_sale_advice_id` | Many2one `sor.pre.sale.advice` | Back-reference set by batch generation. `copy=False`. |
| `post_sale_advice_id` | Many2one `sor.post.sale.advice` | Back-reference set by batch generation. `copy=False`. |
| `vendor_settlement_id` | Many2one `sor.vendor.settlement` | Back-reference set by batch generation. `copy=False`. |

### Fields added to res.company

| Field | Type | Description |
|-------|------|-------------|
| `psa_content_top` | Html | Rendered above the lot table on Pre-Sale Advice documents |
| `psa_content_bottom` | Html | Rendered below the lot table on Pre-Sale Advice documents (e.g. sale terms) |
| `posa_content_top` | Html | Rendered above the results table on Post-Sale Advice documents |
| `posa_content_bottom` | Html | Rendered below the results table on Post-Sale Advice documents (e.g. sale terms) |
| `vss_content_top` | Html | Rendered above the lot table on Vendor Settlement Statements |
| `vss_content_bottom` | Html | Rendered below the lot table on Vendor Settlement Statements (e.g. bank details, sale terms) |

**No dedicated shared-footer field.** A seventh field (`auction_document_footer`) was originally planned to hold shared sign-off/licence content rendered identically across all three documents, but was dropped during Show & Tell (Auction Refinements 01) in favour of Odoo's **native** `company.report_footer` field — already Html, already renders correctly in the real per-page footer across every Odoo layout variant, with zero custom code. `report_footer` is configured via Settings → Companies → Configure Document Layout (native Odoo UI, not a `sor_auction_documents` screen). Because `report_footer` is company-global, this content also now appears on Buyer Invoices and any other document type for the company — accepted as correct, since companies wanting document-specific content still have the six Top/Bottom fields above. There is no dedicated "Director Signature" field either — sign-off content goes in whichever of Top, Bottom, or the native footer an administrator chooses.

---

## Methods

### On sor.event

| Method | Description |
|--------|-------------|
| `action_generate_pre_sale_advices()` | Creates one `sor.pre.sale.advice` per consignor with lots in `catalogued` or `live` state. Re-run refreshes lot assignments for Draft records. Blocked on `closed`/`archived` events. Returns list action. |
| `action_generate_post_sale_advices()` | Creates one `sor.post.sale.advice` per consignor with lots in `sold` or `passed` state. Only available on `active`/`closed` events. |
| `action_generate_vendor_settlements()` | Creates one `sor.vendor.settlement` per consignor with sold/passed lots. Re-run updates Draft VSSes only; Payment Confirmed/Sent/Cancelled are left untouched. |
| `action_view_pre_sale_advices()` | Smart button action — returns filtered list for this event. |
| `action_view_post_sale_advices()` | Smart button action — returns filtered list for this event. |
| `action_view_vendor_settlements()` | Smart button action — returns filtered list for this event. |

### On sor.pre.sale.advice / sor.post.sale.advice

| Method | Description |
|--------|-------------|
| `action_send_by_email()` | Transitions `draft` → `sent` (no-op if already `sent`), then opens the `mail.compose.message` wizard with `default_template_id` set to the document's `mail.template` — subject, body, recipient, and PDF attachment are all populated from that template (the template's `report_template_ids` drives automatic PDF rendering/attachment; no manual `_render_qweb_pdf`/`ir.attachment.create()` code). Form button is a two-button colour-toggle: purple (`btn-primary`) while `draft`, grey (`btn-secondary`, still clickable, re-opens the wizard) once `sent`. |
| `action_bulk_send()` | List bulk action (Actions menu → "Send to Consignors"). Filters selected records to `draft` state with a consignor. For each: if the consignor has an email, sends via the shared `mail_bulk_send_utils.bulk_send_via_template()` helper (mass-mail mode) and transitions to `sent`; if not, the record stays `draft` and gets a chatter note explaining why it wasn't sent — the state never claims a send that didn't happen. Returns a transient `display_notification` summarising counts sent/skipped/**not eligible (wrong starting state)**, chained via `'next': {'type': 'ir.actions.act_window_close'}` so the calling list view refreshes and clears its selection. Records selected in a non-`draft` state (e.g. already `sent`) are reported as "not eligible" rather than silently vanishing from the summary (BUG-04). Renamed from `action_bulk_mark_sent()` this sprint (Auction Documents and Invoice Email Behaviour) — the old name read as a passive "already sent, just record it" attestation. |

### On sor.vendor.settlement

| Method | Description |
|--------|-------------|
| `action_confirm_payment()` | Transitions `draft` → `payment_confirmed`. |
| `action_send_by_email()` | Transitions `payment_confirmed` → `sent` (no-op if already `sent` or still `draft`); opens the `mail.compose.message` wizard with `default_template_id` set to the VSS `mail.template`. Same two-button colour-toggle pattern as PSA/POSA: no button in `draft` or `cancelled`, purple in `payment_confirmed`, grey (still clickable) once `sent`. |
| `action_cancel()` | Transitions `draft` → `cancelled`. Button labelled **Void** (not "Cancel" — that label is reserved for discarding form edits), with a `confirm=` guard since this is irreversible from the UI. Generates a new VSS if cancellation was in error. |
| `action_bulk_send()` | List bulk action (Actions menu → "Send to Consignors"). Filters selected records to `payment_confirmed`. Same email-presence-gated send/skip/chatter/summary behaviour as PSA/POSA's `action_bulk_send()`, via the same shared helper, including the not-eligible-count reporting (BUG-04). Renamed from `action_bulk_mark_sent()` this sprint — VSS's state correctness was already sound pre-sprint (it never wrote `sent` on a skip); this sprint closed the reporting gap (no summary, no chatter on skip) and brought the method name in line with PSA/POSA. |

### Shared bulk-send helper

`addons/sor_auction_documents/models/mail_bulk_send_utils.py` — plain functions (not a model), used by PSA, POSA, and VSS `action_bulk_send()`:

| Function | Purpose |
|----------|---------|
| `bulk_send_via_template(records, template, no_email_reason)` | Splits `records` into `sent` (consignor has email) and `skipped` (does not). Sends `sent` via a `mail.compose.message` in mass-mail mode using `template`. Posts a chatter note on each `skipped` record using `no_email_reason % consignor.name`. Returns `(sent, skipped)` — writes no state; the caller decides. |
| `bulk_send_notification(sent_count, skipped_count, plural_noun, not_eligible_count=0)` | Builds the transient `display_notification` action summarising the outcome, with `'next': {'type': 'ir.actions.act_window_close'}` so the calling list view reloads and deselects. `not_eligible_count` (BUG-04) reports records excluded by the caller's own starting-state filter *before* the sent/skipped split ran — distinct from `skipped_count` (reached the split but had no email). Each `action_bulk_send()` caller computes it as `len(self) - len(to_send)`. |

`sor_buyer_invoice_auction_house` does **not** import this helper — it duplicates the same small pattern in its own `account_move.py` rather than create a base-to-base module dependency (see `sor_composability.md`).

### Mail templates (Settings → Technical → Email → Templates)

Three `mail.template` records, one per document type, defined in `data/mail_template_data.xml` (`noupdate="1"` — admin wording edits survive upgrades):

| Template (XML ID) | Model | `report_template_ids` |
|---|---|---|
| `mail_template_sor_pre_sale_advice` | `sor.pre.sale.advice` | `action_report_sor_pre_sale_advice` |
| `mail_template_sor_post_sale_advice` | `sor.post.sale.advice` | `action_report_sor_post_sale_advice` |
| `mail_template_sor_vendor_settlement` | `sor.vendor.settlement` | `action_report_sor_vendor_settlement` |

Each is used by **both** that document type's individual send and bulk send — mirroring the native `account.email_template_edi_invoice` pattern (one template serves both "Send & Print" and any bulk send of the same move type).

**Critical field: `use_default_to` must be `False`.** Each template sets `partner_to` (e.g. `{{ object.consignor_id.id }}`) to resolve the recipient. `mail.template.use_default_to` **defaults to `True`** in core Odoo, and if left at that default, `partner_to` is silently ignored in mass-mail (bulk) mode — recipient resolution falls back to the generic `_message_get_default_recipients()`, which finds nothing for these models, producing a `mail.mail` with zero recipients that fails silently. Every template here explicitly sets `use_default_to eval="False"`. See `odoo_conventions/orm_and_field_patterns.md` for the full mechanism if this is ever touched again.

---

## Configuration

**Navigation:** Settings → General Settings, below the Buyer's Premium / Vendor Fee Schedule block (all four blocks below are visible only when company business model is `auction_house`), in this order:

**"Auction Documents: Margin Scheme" block:**

| Setting | Field | Notes |
|---------|-------|-------|
| VAT Margin Scheme | `vat_margin_scheme` (defined in `sor_commercial_auction_house`) | Boolean. Company-wide default for new lots. Individual lots can override. |
| Auction VAT Notice | `auction_vat_notice` (defined in `sor_commercial_auction_house`) | HTML rich text (converted from plain text at UAT — BUG-U02; existing content's line breaks were migrated to `<br/>` tags). Printed on buyer invoices when margin scheme applies. Leave blank to suppress. Full-width row, below the VAT Margin Scheme checkbox. |

**"Auction Documents: Pre-Sale Advice Content" block:** Top, Bottom (`psa_content_top`, `psa_content_bottom`) — HTML rich text.

**"Auction Documents: Post-Sale Advice Content" block:** Top, Bottom (`posa_content_top`, `posa_content_bottom`) — HTML rich text.

**"Auction Documents: Vendor Settlement Content" block:** Top, Bottom (`vss_content_top`, `vss_content_bottom`) — HTML rich text.

**Shared footer content (all three documents):** Settings → Companies → **Configure Document Layout** (native Odoo UI, not a `sor_auction_documents` screen) → set the Footer field. This maps to `company.report_footer` and prints in the real per-page footer on every document for the company, including Buyer Invoices.

**`report.url` system parameter:** Must be set to `http://localhost:8069` (internal container URL) for wkhtmltopdf to fetch CSS correctly. Set via Settings → Technical → Parameters → System Parameters → `report.url`.

**Editing email wording (no code change required):** Settings → Technical → Email → Templates → open "Pre-Sale Advice: Sending" / "Post-Sale Advice: Sending" / "Vendor Settlement Statement: Sending". Subject and body are editable there directly; changes take effect immediately for both individual and bulk send, since both paths reference the same template record.

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

**R3 — VAT Margin Scheme defaults from company setting:**
Settings → General Settings → Auction Documents → tick "VAT Margin Scheme" → Save. Create a new lot. Confirm the lot's VAT Margin Scheme checkbox is already ticked.

**R4 — Auction Documents settings hidden for non-auction-house companies:**
Switch to a non-auction-house company. Open Settings → General Settings. Confirm none of the four auction-document blocks (Auction Documents, Pre-Sale Advice Content, Post-Sale Advice Content, Vendor Settlement Content) are visible.

**R5 — Pre-Sale Advice batch generation one record per consignor:**
Open an active or published auction event with catalogued lots assigned to a consignor. Click "Generate Pre-Sale Advices". Confirm one record per consignor appears in the list.

**R6 — Pre-Sale Advice button invisible on closed events:**
Open a closed auction event. Confirm the "Generate Pre-Sale Advices" button is not visible in the form header.

**R7 — Post-Sale Advice button invisible on published events:**
Open a published event. Confirm "Generate Post-Sale Advices" is not visible. Open an active or closed event. Confirm it is visible.

**R8 — VSS lifecycle buttons correct per state:**
Draft VSS: "Confirm Payment" and "Void" visible; "Send to Consignor" hidden.
Payment Confirmed VSS: "Send to Consignor" visible (purple), "Confirm Payment" and "Void" hidden.
Sent VSS: "Send to Consignor" still visible, now grey — clicking it re-opens the compose wizard.
Cancelled VSS: no "Send to Consignor" button.

**R8b — Resend colour-toggle on PSA/POSA:**
Draft PSA/POSA: "Send by Email" is purple. After sending (individually or via bulk), the same document still shows "Send by Email", now grey, and clicking it re-opens the compose wizard pre-populated from the template — it does not disappear once sent, unlike pre-sprint behaviour.

**R8c — Bulk send actually delivers mail, not just a state change:**
Select several Draft PSAs/POSAs (or Payment Confirmed VSSes) with a mix of consignors with and without an email on file. Run the list's "Send to Consignors" Action. Confirm: (a) a transient notification reports counts sent/skipped; (b) the list refreshes automatically and clears the selection with no manual page refresh needed; (c) the record(s) whose consignor has an email now show `state = 'sent'` **and** a real email actually reaches an outgoing mail server (check Mailhog or equivalent) with the correct recipient and PDF attached; (d) the record(s) whose consignor has no email remain in their prior state with a chatter note explaining why. This is the regression surface for BUG-01/02/03 (`use_default_to`, missing `action =` assignment, missing notification `'next'` key) — see `odoo_conventions/orm_and_field_patterns.md`.

**R8d — Bulk send reports a mixed-state selection accurately (BUG-04):**
Select a batch that mixes an eligible record (Draft for PSA/POSA, Payment Confirmed for VSS) with one already in a non-eligible state (e.g. already Sent). Run "Send to Consignors". Confirm the notification reads e.g. "1 Pre-Sale Advice(s) sent, 1 not eligible (wrong state)." rather than silently reporting only the eligible record — and that the not-eligible record's state and content are untouched. Same check applies to Buyer Invoice bulk send ("Send to Buyers" on `account.move`) with a mixed `out_invoice`/`out_refund` selection.

**R9 — VSS totals correct:**
Open a VSS with multiple lots, some with Fixed Charges recorded. Verify `total_hammer = Σ hammer_price`, `total_commission = Σ (hammer × rate/100)`, `total_fixed_charges = Σ fixed_charge_ids.amount` across all lots, `net_proceeds = total_hammer − total_commission − total_fixed_charges`. The Totals tab displays all four fields, in that order.

**R10 — Re-run batch generation does not duplicate:**
Click "Generate Pre-Sale Advices" on an event. Click the button again. Confirm the same count of records exists (no duplicates).

**R11 — M- annotation on margin scheme lots:**
Set `vat_margin_scheme = True` on a sold lot. Generate a Post-Sale Advice. Print the PDF. Confirm the lot shows `M-` after the hammer price.

**R12 — Content blocks render at the correct position:**
Set distinct content in `psa_content_top`, `psa_content_bottom`, and the native `report_footer`. Print a Pre-Sale Advice. Confirm Top renders above the lot table, Bottom renders below it, and the footer content renders in the real per-page footer alongside the page number — not as extra content near the bottom of the page body. Repeat for Post-Sale Advice and Vendor Settlement Statement.

**R13 — Fixed Charges render as labelled lines on the VSS PDF:**
Add two Fixed Charges (different types) to a lot included in a VSS. Print the VSS. Confirm each charge appears as its own "Less: <Charge Type>" line beneath the lot's row (not folded into a single total), and the settlement-level "Total Fixed Charges" row in the footer matches the sum.

---

## Interoperability

| Module | Relationship | Effect |
|--------|-------------|--------|
| `sor_commercial_auction_house` | Parent dependency | Provides `is_commercial` flag on events; `vat_margin_scheme`, `auction_vat_notice`, `sellers_commission_pct` used by PDF templates; `fixed_charge_ids` on `sor.lot` (Fixed Charges — `sor.fixed.charge.type` registry and `sor.lot.fixed.charge` line model) read by the VSS deduction compute and report |
| `sor_bidding` | Optional — not a dependency | When installed, winning bid data drives buyer invoice generation via `sor_buyer_invoice_auction_house`; this module is unaffected either way |
| `sor_consignment_auction` | Auto-installs bridge | Overrides `consignor_id` view to read-only+button; wraps batch generation actions to auto-populate consignors from intake pickings |
| `sor_lotting` | Transitive dependency | Provides `sor.lot` base model; `lot_reference`, `lot_number`, `state`, `auction_id` fields read by document logic |
| `sor_events_auction` | Transitive dependency | Provides `is_commercial` on `sor.event` and the lot→event relationship |
| `sor_buyer_invoice`/`sor_buyer_invoice_auction_house` | No dependency either direction | Never reads any of this module's content-block fields and has no Top/Bottom fields of its own — but Buyer Invoice PDFs **do** pick up whatever is set in native `company.report_footer`, since that field is company-global, not scoped by module |
| Odoo core (`base`) | Native functionality reused | Shared footer content uses `res.company.report_footer` (native field) rather than a `sor_auction_documents`-owned field — configured via Settings → Companies → Configure Document Layout |
