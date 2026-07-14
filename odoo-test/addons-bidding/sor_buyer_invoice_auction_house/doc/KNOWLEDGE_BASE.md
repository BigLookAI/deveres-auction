# SOR Buyer Invoice × Auction House — Knowledge Base

## 1. Overview

**What it does:** Activates all auction-house-specific invoice functionality. When both `sor_buyer_invoice` and `sor_commercial_auction_house` are installed, this bridge auto-installs and adds:
- An **Auction Sales journal** (code `AUC`) provisioned per company
- **Four Incoming Payment methods** (Debit Card, Bank Transfer, Cheque, Bank Draft) provisioned on the company's **Bank** journal — not AUC (see Configuration section below)
- A **per-company buyer invoice sequence** (code `sor.buyer.invoice`)
- A **Generate Buyer Invoices** button on the auction event form
- Lot fields on `account.move` (`sor_lot_ids`) and `account.move.line` (`sor_lot_id`, `sor_line_type`, `sor_buyers_premium_pct`)
- Invoice number format: `{sequential}/{sale_number}` (e.g. `100109/A132`)
- **Buyer's premium lines** computed from `sor.lot.buyers_premium_pct`
- **Lot breakdown table** in the invoice PDF with Hammer, Buyer's Premium columns
- **VAT treatment columns** (VAT indicator M-, VAT on Hammer) when `company.vat_margin_scheme` is True
- **Statutory VAT notice** text from `company.auction_vat_notice`
- **Incremental invoice generation** (BUG-05): "already invoiced" is tracked at (event, buyer, **lot**) granularity via `account.move.sor_lot_ids`, not (event, buyer). A buyer with an existing invoice still gets a new invoice generated for any subsequently-sold lot(s) not yet covered by that invoice. The action only raises a UserError when there is genuinely nothing left to invoice (every winning-bid/sold lot for the event already has a covering invoice)
- **Bulk send from the invoice list** ("Send to Buyers" Action menu item): sends every selected Buyer Invoice with a valid email an editable-template email with the correct bespoke invoice PDF attached; skips (with a chatter note) invoices whose buyer has no email on file; reports a transient sent/skipped summary

**What it does NOT do:** It does not modify the base `sor_buyer_invoice` module. Gallery invoice formatting is a separate future bridge. Lot-to-agreement linking is D2 scope.

**Dependencies:** `sor_buyer_invoice`, `sor_commercial_auction_house`
**Auto-installs:** Yes — when both parents are installed.

**`sor_bidding` is optional.** When `sor_bidding` is installed, invoices are generated from winning bids (`sor.bid.is_winning_bid = True`, `sor.bid.bidder_id`). When `sor_bidding` is absent, invoices are generated from sold lots with `buyer_id` set directly on `sor.lot`. The presence of `sor_bidding` is detected via `'sor.bid' in self.env.registry` at runtime.

---

## 2. Key fields and models

| Model | Field | Type | Purpose |
|-------|-------|------|---------|
| `account.move` | `sor_lot_ids` | Many2many → `sor.lot` | Links an invoice to the lots it covers |
| `account.move.line` | `sor_lot_id` | Many2one → `sor.lot` | The specific lot this line represents |
| `account.move.line` | `sor_line_type` | Selection (`hammer` / `buyers_premium`) | Identifies whether the line is a hammer price or a buyer's premium |
| `account.move.line` | `sor_buyers_premium_pct` | Float | The rate applied when this premium line was generated |
| `account.journal` | AUC journal | Provisioned record | `type=sale`, `code=AUC`, one per company — used for all buyer invoices |
| `account.payment.method.line` | Debit Card / Bank Transfer / Cheque / Bank Draft | Provisioned records | Four Incoming Payment methods on the company's `type=bank` journal, each `payment_account_id` set to that journal's own account (`reconcile=False`) so registered payments — including partials — reach Paid immediately |
| `ir.sequence` | `sor.buyer.invoice` | Provisioned record | Per-company sequential counter for invoice numbers |
| `sor.event` | `invoice_pending_count` | Integer (computed, store=False) | Number of distinct buyers with at least one winning-bid/sold lot for this event **not yet covered by an existing invoice** — granularity is (event, buyer, lot), not (event, buyer) (BUG-05). A buyer who already has an invoice for this event still counts if they have a further sold lot not on that invoice. Drives the badge-style Generate Buyer Invoices button on the event form. |
| `mail.template` | `mail_template_sor_buyer_invoice_bulk` | Provisioned record (`noupdate=1`) | Dedicated bulk-send template on `account.move`; `report_template_ids` references `account.account_invoices` (the same native report action individual "Send & Print" resolves to, so the bespoke SOR/auction-house layout is picked up automatically). `use_default_to eval="False"` — required, or `partner_to` is silently ignored in mass-mail mode (see `odoo_conventions/orm_and_field_patterns.md`). |

---

## 3. Methods

| Model | Method | Description |
|-------|--------|-------------|
| `sor.event` | `action_generate_buyer_invoices()` | Finds winning bids (or sold lots, fallback path), excludes any lot already covered by an existing invoice (`already_invoiced_lot_ids`, keyed on `account.move.sor_lot_ids` — BUG-05), groups the remainder by buyer, calls `_prepare_buyer_invoice_lines`, creates one `account.move` per buyer covering only their not-yet-invoiced lots, assigns invoice number. Raises a UserError only when there are no lots left to invoice at all — a buyer with an existing invoice still gets a new one for a further unbilled lot. |
| `sor.event` | `_prepare_buyer_invoice_lines(lots, buyer)` | Returns `(0, 0, {...})` command tuples for hammer lines and buyer's premium lines; designed as an extension point for bridge overrides |
| `account.move` | `action_bulk_send_sor_invoice()` | List bulk action (Actions menu → "Send to Buyers"). Filters selection to `move_type == 'out_invoice'` with a partner — records excluded by this filter (wrong `move_type` or no partner) are reported as a "not eligible (wrong state)" count rather than silently vanishing (BUG-04). Of the eligible records, splits into `sent` (partner has email) and `skipped` (does not); sends `sent` via `mail.compose.message` in mass-mail mode using `mail_template_sor_buyer_invoice_bulk`; posts a chatter note on each `skipped` invoice; returns a transient `display_notification` summarising sent/skipped/not-eligible counts, chained via `'next': {'type': 'ir.actions.act_window_close'}` so the list view refreshes and clears its selection. Individual "Send & Print" is untouched — it still resolves the native `account.email_template_edi_invoice` via its own `account.move.send` wizard. |

---

## 4. Configuration

**Auction Sales journal:** The AUC journal is provisioned automatically on install with `default_account_id` set to the company's primary income account (the first `account_type = 'income'` account associated with the company). No manual journal configuration is required after a standard install with a chart of accounts applied.

**Payment methods (registering buyer payments):** Four Incoming Payment methods — Debit Card, Bank Transfer, Cheque, Bank Draft — are provisioned automatically on the company's **Bank** journal (`type=bank`), not on AUC. AUC is a pure invoicing journal (`type=sale`) and cannot be offered by Odoo's payment registration wizard, which only lists `bank`/`cash`/`credit` journals. Each method's account is set explicitly to the Bank journal's own account (`reconcile=False`), so a registered payment — including a partial payment — reaches Paid immediately, with no manual bank reconciliation step. This applies **going forward only**: a company with pre-existing manually-created lines under these same names is left untouched; provisioning does not modify or overwrite them, regardless of which account they point to.

**Hammer Price VAT Scheme:** Settings → General Settings → **Auction Documents** block → enable `VAT Margin Scheme`. When enabled, the invoice PDF shows the VAT indicator (M-), VAT on Hammer column (displays €0.00), and the VAT notice text.

**VAT Notice Text:** Settings → General Settings → **Auction Documents** block → `Auction VAT Notice`. Enter the statutory notice text verbatim. Rendered on the PDF when `VAT Margin Scheme` is enabled and the notice field is non-empty.

**Editing the bulk-send email wording:** Settings → Technical → Email → Templates → "Buyer Invoice: Bulk Sending". Editable directly, no code change required. This template is used **only** by the bulk-send path — individual "Send & Print" continues to use the native `account.email_template_edi_invoice`, unaffected by edits here.

---

## 5. Generating buyer invoices

1. Navigate to an auction event with winning bids recorded.
2. Click **Generate Buyer Invoices**.
3. One invoice per buyer is created, covering all of that buyer's lots not already covered by an existing invoice for this event (lot-level granularity — BUG-05).
4. Invoice numbers are assigned immediately in format `{sequential}/{sale_number}`.
5. The action redirects to the invoice list filtered to this event.

Running the action again after some, but not all, lots have been invoiced creates a **new** invoice per buyer for just their remaining unbilled lot(s) — it does not touch or duplicate existing invoices. A `UserError` is raised only when every winning-bid/sold lot for the event already has a covering invoice: "All buyer invoices have already been generated for this auction."

---

## 6. Building on this module

The `_prepare_buyer_invoice_lines(lots, buyer)` method on `sor.event` is the designated extension point. A future gallery invoice bridge can override this method via `_inherit` to change line structure without modifying `action_generate_buyer_invoices`.

The PDF template `report_invoice_document_sor_auction_house_bridge` inherits `sor_buyer_invoice.report_invoice_document_sor_buyer_invoice` (a fully standalone template, no longer inherit-and-patch of native Odoo — see `sor_buyer_invoice`'s Technical Architecture doc, Auction MVP Refinements Story 03). This bridge replaces the base's generic fallback table wholesale (`position="replace"` on `//div[@name='sor_invoice_line_table']`) with the lot breakdown table, VAT columns, and statutory notice. Further PDF extensions (e.g. `sor_buyer_invoice_artwork`) should inherit from this bridge template — not from the base — if they need to add content within the lot breakdown context; the artwork bridge specifically XPaths `//td[t[@t-if='lot.product_id']]` inside the lot breakdown `<tbody>` to substitute a compound description. The base template's payment-status block (`sor_invoice_payment_status`) is a sibling of `sor_invoice_line_table`, so it renders unchanged regardless of this bridge's replacement.

**Bulk-send pattern is duplicated from `sor_auction_documents`, not imported.** `sor_auction_documents` has a shared `mail_bulk_send_utils.py` helper used by its own three document models (PSA/POSA/VSS). This module does **not** depend on `sor_auction_documents` to reuse it — `account_move.py::action_bulk_send_sor_invoice()` re-implements the same small (~5-line) mass-mail-composer-creation pattern inline. Adding a dependency purely to share this logic would create a base-to-base module dependency, prohibited by `sor_composability.md`. If this pattern needs to change, both modules' implementations must be updated in step.

---

## 7. Regression checks

**R1 — AUC journal exists after install:** Settings → Invoicing → Journals. Confirm "Auction Sales" journal with code AUC is present.

**R2 — Generate button appears on event with winning bids:** Navigate to an auction event with at least one `is_winning_bid=True` bid. Confirm "Generate Buyer Invoices" button is visible.

**R3 — Generate button absent with no winning bids:** Navigate to an auction event with no winning bids. Confirm the button is absent.

**R4 — Invoice number format:** Generate invoices for an event with a `sale_number` set. Open the created invoice. Confirm the name matches `{NNN}/{sale_number}` format.

**R5 — Lot breakdown table on PDF:** Print a generated invoice. Confirm the PDF shows the lot breakdown table with Lot No, Description, Hammer, and Buyer's Premium columns.

**R6 — Duplicate guard (all lots invoiced):** Click "Generate Buyer Invoices" on an event where every winning-bid/sold lot already has a covering invoice. Confirm a UserError is shown ("All buyer invoices have already been generated for this auction.").

**R6b — Incremental invoicing (BUG-05):** On an event where a buyer already has an invoice covering some of their lots, sell a further lot to the same buyer. Confirm `invoice_pending_count` is non-zero (button visible) and that clicking "Generate Buyer Invoices" creates a **new** invoice containing only the newly-sold lot — the existing invoice is untouched and no lot appears on two invoices.

**R7 — Payment methods present on Bank journal:** Accounting → Configuration → Journals → Bank → Incoming Payments tab. Confirm Debit Card, Bank Transfer, Cheque, and Bank Draft are all present.

**R8 — Bulk send reports a not-eligible selection (BUG-04):** Select a mix of an eligible Buyer Invoice (`out_invoice` with a partner) and an ineligible record (e.g. a credit note or a move with no partner). Run "Send to Buyers". Confirm the notification reports a "not eligible (wrong state)" count alongside sent/skipped, rather than silently omitting the ineligible record.

**R8 — Single payment reaches Paid immediately:** Register a payment via any of the four methods that fully settles a buyer invoice. Confirm the payment's own status shows Paid immediately, with no manual reconciliation step.

**R9 — Partial payments each reach Paid individually:** Register two or more partial payments against a buyer invoice (any combination of the four methods, at different times). Confirm each individual payment shows Paid as soon as it is registered — not just the last one — while the invoice's own status progresses Not Paid → Partially Paid → Paid as expected.

**R10 — Lot breakdown table replaces the fallback, payment status still present:** Print a generated invoice. Confirm the lot breakdown table (Lot No, Description, Hammer, Buyer's Premium) is the only line-items table shown — no duplicate generic fallback table — and that the payment-status block (Paid on / Amount Due) still renders correctly alongside it once the invoice is paid.

**R11 — VAT notice appears only when a lot on the invoice is margin-scheme:** Print an invoice covering a mix of margin-scheme and non-margin-scheme lots. Confirm the VAT indicator/column and statutory notice appear. Print an invoice with no margin-scheme lots. Confirm the notice is absent even when `company.auction_vat_notice` is configured.

**R12 — Bulk send actually delivers mail with the correct bespoke PDF:** Select several Buyer Invoices with a mix of buyers with and without an email on file, and run "Send to Buyers" from the Actions menu. Confirm: (a) a transient summary reports counts sent/skipped; (b) the list refreshes automatically with no manual page refresh needed; (c) a real email reaches an outgoing mail server (e.g. Mailhog) for each buyer with an email, with the correct bespoke SOR/auction-house invoice PDF attached (same layout individual "Send & Print" would produce); (d) each skipped invoice (no email on file) gets a chatter note explaining why.

---

## 8. Interoperability

| Module | Interaction |
|--------|------------|
| `sor_buyer_invoice` | Parent — provides event-invoice link, PDF footer anchor; this bridge extends `_prepare_buyer_invoice_lines` |
| `sor_commercial_auction_house` | Parent — provides `vat_margin_scheme`, `auction_vat_notice` on `res.company`; `sor.lot.buyers_premium_pct`; `sor.lot.hammer_price` |
| `sor_bidding` | Optional — when installed, invoices generated from winning bids (`sor.bid.is_winning_bid`, `sor.bid.bidder_id`); when absent, invoices generated from sold lots with `buyer_id`; detected via `'sor.bid' in self.env.registry` |
| `sor_consignment_agreements_auction_house` | Sibling bridge — both auto-install when their respective parent sets are present; no direct dependency |
