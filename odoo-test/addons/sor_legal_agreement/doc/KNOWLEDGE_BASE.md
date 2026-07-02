# SOR Legal Agreements — Knowledge Base

## Overview

`sor_legal_agreement` is the legal agreement foundation module for the SOR platform. It records the signed contracts that govern the physical movement of goods — artworks, consignment items, or any other product — between the gallery and a counterparty. The module enforces the **agreement-first principle**: no stock movement may be triggered unless the agreement covering it is in the `active` (signed) state.

**What this module does:**

- Provides the `sor.agreement` model with a five-stage state machine (Draft → Pending Signature → Active → Closed; Revoked reachable from Pending Signature and Active)
- Auto-generates a company-scoped agreement reference number in the format `AGR/YYYY/NNNNN`
- Generates a draft PDF preview automatically on every save while an agreement is in Draft state, and attaches it to the chatter for review before sending
- Generates and attaches a final PDF when the agreement is sent for signature; removes the draft preview at that point
- Provides a Rescind & Regenerate workflow: rescinding a Pending Signature or Active agreement moves it to the terminal `revoked` state and immediately creates a new Draft replacement carrying the same lines, pre-linked to the original
- Runs a daily staleness alerting cron that identifies overdue Pending Signature agreements (sent more than 14 days ago, or expiring within 7 days) and notifies followers via a chatter note
- Links stock movements (`stock.picking`) to their governing agreement via `stock.picking.agreement_id`
- Exposes a `_check_can_trigger_movement()` contract method that bridge modules must call before creating pickings
- Provides a user-facing **Legal** menu with a list and form view for agreements
- Registers an **Agreements** developer menu entry under **Settings → Technical → SOR**
- Applies company data isolation via a multi-company record rule

**What this module does NOT do:**

- It does not trigger stock movements itself — that is the responsibility of bridge modules (e.g. a future `sor_consignments_agreement` bridge)
- It does not manage consignment terms, pricing, or commission schedules — those are domain concerns for separate bridge modules
- It does not provide an electronic signature integration — `pending_signature` is a manual workflow marker indicating the PDF has been sent; wet-ink or DocuSign integration is out of scope
- It does not provide a re-open path from `closed` — Closed is terminal in the base module. Revoked agreements can only be followed up via the replacement created at rescind time
- It does not restrict which users can manage agreements beyond Odoo's standard `base.group_user` access

**Dependencies:**

- `product` — required for `sor.agreement.line.product_id`
- `stock` — required for the `stock.picking.agreement_id` link field

This module installs standalone. It does not depend on any other SOR module. Bridge modules connect it to domain-specific workflows (`sor_artwork`, `sor_locations`, etc.).

---

## Key Fields and Models

### `sor.agreement` — the agreement record

The central model. Inherits `mail.thread` and `mail.activity.mixin` for chatter, logged note, and activity support. `_check_company_auto = True` enforces cross-company field validation automatically.

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `name` | Char | Auto-generated reference (e.g. `AGR/2026/00001`). Read-only on form; set on create via `ir.sequence`. | `'New Agreement'` (replaced on save) |
| `company_id` | Many2one → `res.company` | Owning company. Required. Shown on form only in multi-company deployments. | `env.company` |
| `agreement_type` | Selection | Agreement classification. Base module provides `'base'` ("Base Agreement"). Bridge modules extend via `selection_add`. | `False` (no default) |
| `primary_partner_id` | Many2one → `res.partner` | The counterparty to the agreement. `check_company=True`. | `False` |
| `date_start` | Date | Effective Date — when the agreement takes legal effect. | `False` |
| `date_end` | Date | End Date — optional expiry date. Used in staleness computation. | `False` |
| `state` | Selection | Lifecycle state. See state machine below. Tracked (chatter logs all changes). Not copied on duplicate. | `'draft'` |
| `terms` | Html | Terms and Conditions. Rendered in the agreement PDF. | `False` |
| `notes` | Text | Internal notes. Not included in the PDF. Always editable regardless of state. | `False` |
| `line_ids` | One2many → `sor.agreement.line` | The products covered by this agreement. `copy=True` — carried to the replacement when an agreement is rescinded. | `[]` |
| `picking_ids` | One2many → `stock.picking` | Stock movements linked to this agreement. Read-only display on the Internal tab. `copy=False`. | `[]` |
| `supersedes_id` | Many2one → `sor.agreement` | The original agreement this record replaces. Set automatically by `action_rescind()` on the replacement. Read-only. `copy=False`. | `False` |
| `superseded_by_id` | Many2one → `sor.agreement` (computed, `store=False`) | Inverse lookup — the replacement agreement that supersedes this record, if one exists. | `False` |
| `date_sent_for_signature` | Date | Set by `action_send_for_signature()` at the moment the agreement is sent. Used to compute staleness. Read-only. `copy=False`. | `False` |
| `is_stale` | Boolean (computed, `store=False`) | `True` when the agreement is in Pending Signature state and is either more than 14 days old (by `date_sent_for_signature`) or is expiring within 7 days (by `date_end`). Used by the Overdue list filter and the list view warning decoration. Has `search='_search_is_stale'` for domain-compatible filtering. | `False` |
| `last_stale_notified` | Date | Set by the staleness cron when a notification is dispatched. Prevents duplicate notifications. Read-only. `copy=False`. | `False` |

#### State machine

```
draft  →  pending_signature  →  active  →  closed
                  ↘                  ↘
                  revoked          revoked
```

| State | Label | Meaning |
|-------|-------|---------|
| `draft` | Draft | Agreement is being prepared. The only deletable state. Draft PDF previews are generated automatically on every save. |
| `pending_signature` | Pending Signature | PDF has been generated and sent to the counterparty. Awaiting their wet-ink or out-of-band signature. Can be rescinded. |
| `active` | Active | Agreement is signed and in force. Bridge modules may now trigger stock movements. Can be rescinded. |
| `closed` | Closed | Terminal state. No further transitions in the base module. |
| `revoked` | Revoked | Terminal state. Reached via `action_rescind()` from Pending Signature or Active. A new Draft replacement is created automatically at rescind time. |

Transitions are forward-only. There are no backwards transitions in the base module. Bridge modules must not add a re-open transition to `closed` without explicit PO approval.

---

### `sor.agreement.line` — the items covered

| Field | Type | Description |
|-------|------|-------------|
| `agreement_id` | Many2one → `sor.agreement` | Parent agreement. Required. Cascade-deletes when the parent is deleted. |
| `product_id` | Many2one → `product.template` | The product covered by this agreement. Required. |

Lines are edited inline on the **Lines** tab of the agreement form view. Because `line_ids` is declared `copy=True`, rescinding an agreement copies all lines to the replacement draft.

---

### `stock.picking` extension

`sor_legal_agreement` adds one field to `stock.picking`:

| Field | Type | Description |
|-------|------|-------------|
| `agreement_id` | Many2one → `sor.agreement` | The agreement governing this movement. `ondelete='set null'` — if the agreement is deleted, the picking retains its history but loses the link. |

Bridge modules populate this field when creating pickings. The base module provides the field but does not set it automatically.

---

### `res.company` extension

| Field | Type | Description |
|-------|------|-------------|
| `logo_pdf` | Binary (computed, `store=False`) | PNG version of the company logo, converted from WebP on demand for use in PDF reports. See Methods section for details. |

---

## Methods

### `sor.agreement.create(vals_list)`

**Override of `@api.model_create_multi`.**

Auto-assigns the agreement reference number from the company-scoped `ir.sequence` (code `sor.agreement`). The number is only assigned when `name` is still `'New Agreement'` — if a caller explicitly provides a name, it is preserved unchanged.

Uses `with_company(company)` to pull the sequence for the record's company rather than the user's active session company, which may differ in multi-company deployments.

After creating the records, calls `_generate_draft_pdf()` on all records in `draft` state, so a draft PDF preview is attached immediately on first save.

---

### `sor.agreement.write(vals)`

**Override of `write`.**

After performing the standard write, calls `_generate_draft_pdf()` on all records in `self` that are still in `draft` state. This keeps the draft PDF preview current as the agreement content evolves. Non-draft records are unaffected — their PDFs are frozen at the point of sending for signature.

---

### `sor.agreement._generate_draft_pdf()`

**Internal method — draft PDF preview generation.**

For each agreement in `self`:

1. Renders the agreement report (`action_report_sor_agreement`) via `_render_qweb_pdf`.
2. Removes any existing attachment named `{name} (Draft).pdf` on this record.
3. Creates a new `ir.attachment` named `{name} (Draft).pdf` with the rendered PDF binary.

The preview is always replaced (not appended) so the chatter does not accumulate multiple draft versions. The `(Draft)` suffix distinguishes the preview from the final signed PDF created by `action_send_for_signature()`.

---

### `sor.agreement._check_can_trigger_movement()`

**Bridge contract method.**

```python
agreement.ensure_one()
agreement._check_can_trigger_movement()
# Raises odoo.exceptions.UserError if state != 'active'
```

Bridge modules **must** call this method before creating any `stock.picking` for the agreement. It raises `UserError` with a descriptive message if the agreement is not in `active` state, enforcing the agreement-first principle.

This is the public interface between the base module and bridge modules. Do not bypass it with a direct state check — the implementation may be extended in future sprints.

**Raises:** `UserError` — "Movement cannot be triggered: the agreement '{name}' must be Active."

---

### `sor.agreement.unlink()`

**Override of `unlink`.**

Only `draft` agreements may be deleted. Attempting to delete an agreement in any other state raises `UserError` with the current state label included in the message.

Non-draft agreements should be closed (`action_close`) or, where appropriate, rescinded (`action_rescind`). Once an agreement has been sent for signature it has legal significance and cannot be deleted.

---

### `sor.agreement.action_send_for_signature()`

**Button method — Draft → Pending Signature.**

1. Validates the agreement is in `draft` state.
2. Renders the final PDF using the `action_report_sor_agreement` report action (qweb-pdf).
3. Removes the existing `{name} (Draft).pdf` attachment (the draft preview) from the chatter.
4. Creates a new `ir.attachment` named `{name}.pdf` (no Draft suffix) — the final, signed-version PDF.
5. Writes `state = 'pending_signature'` and sets `date_sent_for_signature` to today.
6. Posts a chatter message: "Sent for signature. PDF attached."

After this transition, all legally significant fields become read-only. The final PDF represents the agreement terms at the moment of sending and is not regenerated by subsequent edits.

---

### `sor.agreement.action_confirm_signed()`

**Button method — Pending Signature → Active.**

Validates the agreement is in `pending_signature` state, writes `state = 'active'`, and posts a chatter message noting that movements may now be triggered. Once active, bridge modules may call `_check_can_trigger_movement()` without error.

---

### `sor.agreement.action_close()`

**Button method — Active → Closed.**

Validates the agreement is in `active` state, writes `state = 'closed'`, and posts a chatter message. `closed` is a terminal state — no further transitions are possible from the base module.

---

### `sor.agreement.action_rescind()`

**Button method — Pending Signature or Active → Revoked + new Draft replacement.**

1. Validates the agreement is in `pending_signature` or `active` state; raises `UserError` otherwise.
2. Writes `state = 'revoked'` on the original agreement and posts a chatter note.
3. Calls `self.copy({'state': 'draft', 'supersedes_id': self.id, 'name': 'New Agreement'})` to create the replacement — this carries `line_ids` (because `copy=True` on that field) and resets `state`, `name`, `supersedes_id`, `date_sent_for_signature`, and `last_stale_notified` to their appropriate defaults.
4. Returns a window action that opens the replacement form view directly.

The replacement receives a new system-generated reference on its first save (the `create` override handles this via `'New Agreement'` detection). The `supersedes_id` field on the replacement points back to the original, and the original's `superseded_by_id` computed field shows the replacement.

Both agreements remain in the system. Revoked agreements are shown muted in the list view.

---

### `sor.agreement._compute_is_stale()` and `_search_is_stale()`

**Computed field and search method for `is_stale`.**

`_compute_is_stale()` runs for each record: if `state != 'pending_signature'`, `is_stale` is `False`. Otherwise, `is_stale` is `True` when either:
- `date_sent_for_signature` is set and is more than 14 days before today, **or**
- `date_end` is set and is on or before today + 7 days.

`_search_is_stale()` translates a domain filter on `is_stale` into a concrete domain query against stored fields. This enables the **Overdue** filter in the search view. It handles the Odoo 19 operator normalisation: before invoking a `_search` method, Odoo 19 normalises `'='` to `'in'` with an `OrderedSet` value (and `'!='` to `'not in'`). The method unwraps these before evaluating the condition.

---

### `sor.agreement._action_notify_stale_agreements()`

**Cron target — daily staleness notification.**

Called by the `ir.cron` record `ir_cron_notify_stale_agreements` (runs daily).

Searches for agreements where `state = 'pending_signature'` AND `last_stale_notified` is `False` AND the staleness conditions are met. For each match:

1. Collects all follower partner IDs from `message_follower_ids`.
2. Posts a chatter note using `message_post` with `subtype_xmlid='mail.mt_note'` and `partner_ids` explicitly set to the follower list. The explicit `partner_ids` is required because `mt_note` (Internal Note) only notifies followers explicitly subscribed to Internal Notes — passing `partner_ids` bypasses the subscription-type gate and ensures delivery.
3. Sets `last_stale_notified = today`.

The `last_stale_notified` field prevents the same agreement from generating a second notification on subsequent cron runs. If the agreement is later revised (e.g. rescinded and replaced), the replacement starts with `last_stale_notified = False` and will notify independently.

---

### `res.company._compute_logo_pdf()`

**Computed field method for `logo_pdf`.**

Converts `company.logo_web` (stored as WebP in Odoo 19) to PNG for use in PDF reports rendered by wkhtmltopdf 0.12.6, which does not support WebP.

**Why `bin_size=False` is required:** In HTTP contexts (including PDF render requests), Odoo's Binary fields default to returning a human-readable size string (e.g. `b'7.24 KB'`) rather than the actual image bytes when `bin_size=True`. Forcing `bin_size=False` on the `with_context` call ensures the method always receives the real base64-encoded image bytes from the database. Without this, `base64.b64decode` would silently produce garbage bytes and PIL would raise `UnidentifiedImageError`.

The `WebPImagePlugin` import is intentional: importing the plugin registers WebP support in Pillow's `Image.open` dispatch table. Without it, `Image.open` cannot decode WebP source data even if Pillow was compiled with WebP support.

---

## Configuration

There is no configuration UI for this module. It works out of the box after installation with the following defaults:

- Agreement reference sequence: `AGR/YYYY/NNNNN`, starting at `AGR/2026/00001` for each company
- All authenticated internal users (`base.group_user`) have full read/write/create/delete access to agreements and agreement lines
- Deletion is restricted by the unlink override (not by access rules) — all users can attempt delete, but only Draft records succeed
- The staleness alerting cron runs daily and will begin firing as soon as Pending Signature agreements meet the staleness threshold

### Customising the reference sequence

Each company has its own independent sequence. To inspect or modify it:

1. Activate developer mode (`?debug=1` in the URL, or **Settings → General Settings → Developer Tools → Activate the developer mode**).
2. Navigate to **Settings → Technical → Sequences & Identifiers → Sequences**.
3. Search for "SOR Agreement".
4. One row per company will be shown. Click the relevant row to change the prefix, padding, or next counter value.

---

## Developer Menu

`sor_legal_agreement` registers a developer-only **Agreements** entry under **Settings → Technical → SOR → Agreements**.

- **Navigation path:** Settings → Technical → SOR → Agreements (developer mode required; hidden from normal users via `groups="base.group_no_one"`)
- **Parent menu:** `sor_technical_menu.menu_sor_technical_root` — the canonical SOR Technical submenu owned by `sor_technical_menu`
- **What it shows:** The same `action_sor_agreement` window action that powers the user-facing Legal menu — all agreements, unfiltered
- **How to use it:** Primarily useful when troubleshooting supersession chains or staleness alerting in developer mode; the list view's Overdue filter and muted-row decorations are visible here

If future bridge modules need to expose developer-configurable rule records that govern agreement behaviour, those menus should be registered under the same `sor_technical_menu.menu_sor_technical_root` parent following the established SOR Technical menu pattern.

---

## Building on This Module

Bridge modules connect `sor_legal_agreement` to domain-specific workflows. Follow these steps to build a bridge.

### Step 1 — Declare the dependency

```python
# __manifest__.py
'depends': ['sor_legal_agreement', 'sor_other_module'],
'auto_install': True,
'application': False,
'category': 'Hidden/Technical',
```

`auto_install: True` means the bridge installs automatically when both parent modules are present. Do not set `auto_install: False` for bridges — it defeats composability.

### Step 2 — Extend the agreement type vocabulary (if needed)

The base module provides a single type value: `'base'` ("Base Agreement"). If your bridge introduces a distinct agreement type (e.g. `'consignment'` for consignment agreements, `'loan'` for loan agreements), extend the selection:

```python
class SorAgreement(models.Model):
    _inherit = 'sor.agreement'

    agreement_type = fields.Selection(
        selection_add=[('consignment', 'Consignment Agreement')],
        ondelete={'consignment': 'set default'},
    )
```

Use `ondelete='set default'` so that uninstalling the bridge reverts affected records to no type rather than deleting them.

### Step 3 — Add domain-specific fields

Extend `sor.agreement` with any fields your bridge needs (e.g. commission rate, return period, artist studio reference). Keep fields in the bridge — do not propose additions to the base model unless the field is truly universal across all agreement types.

### Step 4 — Extend the form view

Use `inherit_id` to add your fields to the agreement form. Add new fields in the `<group>` block or as a new notebook `<page>` — do not remove or reorder existing elements.

### Step 5 — Call `_check_can_trigger_movement()` before creating pickings

This is the most important bridge contract obligation. Before calling `stock.picking.create(...)` for an agreement, always call:

```python
agreement._check_can_trigger_movement()
```

This raises `UserError` immediately if the agreement is not `active`, preventing any movement from being created under a draft or unsigned agreement. Place the call before any ORM write or picking creation logic in your bridge.

```python
def action_trigger_movement(self):
    self.ensure_one()
    self.agreement_id._check_can_trigger_movement()  # raises if not active
    picking = self.env['stock.picking'].create({
        'agreement_id': self.agreement_id.id,
        # ... other picking vals
    })
```

### Step 6 — Set `agreement_id` on pickings

When your bridge creates `stock.picking` records, populate `agreement_id` with the governing agreement. This links the movement to the agreement for audit purposes and makes it visible in the **Linked Stock Movements** section on the agreement's Internal tab.

### Step 7 — Extend the PDF template (if needed)

The base template (`sor_legal_agreement.report_sor_agreement`) renders reference, type, counterparty, dates, items table, terms, and a signature block. To add domain-specific content (e.g. consignment-specific clauses), inherit the template:

```xml
<template id="report_sor_agreement_consignment"
          inherit_id="sor_legal_agreement.report_sor_agreement">
    <!-- XPath additions here -->
</template>
```

Use `priority` to control the rendering order if multiple bridges extend the same template.

---

## Regression Checks

Run these checks after any change to `sor_legal_agreement` or any bridge module that depends on it to confirm the core behaviour has not regressed.

### R1 — Agreement creation and reference numbering

1. Log in as any internal user.
2. Navigate to **Legal → Legal**.
3. Click **New**.
4. Confirm the reference field reads "New Agreement" in the form title.
5. Click **Save manually** (or navigate away to trigger save).
6. Confirm the reference has been replaced with a sequence number in the format `AGR/YYYY/NNNNN` (e.g. `AGR/2026/00001`).
7. Create a second agreement and confirm the counter increments (`AGR/2026/00002`).

**Expected:** Sequence assigned on first save; counter increments correctly.

---

### R2 — State machine: Draft → Pending Signature

1. Open a Draft agreement.
2. Confirm the header shows the **Mark as Sent for Signature** button (blue/primary) and the status bar reads **Draft**.
3. Confirm **Confirm Signed** and **Close Agreement** buttons are absent.
4. Click **Mark as Sent for Signature**.
5. Confirm the state transitions to **Pending Signature**.
6. Confirm a final PDF attachment (`AGR/...NNNNN.pdf`, no "(Draft)" suffix) appears in the chatter.
7. Confirm the earlier `(Draft).pdf` attachment is no longer present.
8. Confirm a chatter message "Sent for signature. PDF attached." is visible.
9. Confirm the **Mark as Sent for Signature** button has disappeared and **Confirm Signed** is now shown.
10. Confirm a **Rescind** button is now visible.

**Expected:** Transition succeeds; final PDF attached; draft PDF removed; chatter updated; buttons update correctly.

---

### R3 — State machine: Pending Signature → Active

1. Open an agreement in **Pending Signature** state.
2. Click **Confirm Signed**.
3. Confirm the state transitions to **Active**.
4. Confirm the chatter message "Agreement confirmed as signed. Movements may now be triggered." appears.
5. Confirm the **Confirm Signed** button has disappeared and **Close Agreement** is now shown.
6. Confirm the **Rescind** button is still visible.

**Expected:** Transition succeeds; chatter updated; buttons update correctly.

---

### R4 — State machine: Active → Closed

1. Open an agreement in **Active** state.
2. Click **Close Agreement**.
3. Confirm the state transitions to **Closed**.
4. Confirm the chatter message "Agreement closed." appears.
5. Confirm all header action buttons are absent (no further transitions available).
6. Confirm the row in the list view is greyed out (muted decoration applied to closed rows).

**Expected:** Terminal state reached; no further action buttons displayed; list row muted.

---

### R5 — Deletion protection

1. Open a **Draft** agreement and delete it via the **Action** menu → **Delete**.
2. Confirm the deletion succeeds.
3. Create a new agreement and advance it to **Pending Signature** using the button.
4. Attempt to delete the Pending Signature agreement via the **Action** menu → **Delete**.
5. Confirm an error message is shown: "Agreement [reference] cannot be deleted because it is Pending Signature. Only Draft agreements may be deleted."
6. Repeat for an **Active** agreement, a **Closed** agreement, and a **Revoked** agreement.

**Expected:** Draft deletion succeeds; all other states are protected with a descriptive error.

---

### R6 — Movement gate (`_check_can_trigger_movement`)

This check requires a bridge module that calls `_check_can_trigger_movement()`. If no such bridge is installed, test directly in a developer shell:

```python
agreement = env['sor.agreement'].browse(<id of draft agreement>)
agreement._check_can_trigger_movement()
# Expected: UserError raised
```

Then advance the agreement to Active and retry:

```python
agreement._check_can_trigger_movement()
# Expected: no error raised
```

**Expected:** UserError raised for Draft, Pending Signature, Closed, and Revoked states; no error raised for Active.

---

### R7 — PDF content

1. Open an agreement with a Counterparty, Effective Date, at least one Line item, and Terms text filled in.
2. Click **Mark as Sent for Signature**.
3. Open the final PDF attachment from the chatter.
4. Confirm the PDF shows: company logo (top), agreement reference, agreement type, counterparty name, effective date, items table (product names), terms and conditions text, and signature blocks for both parties.
5. Confirm Internal Notes are **not** present in the PDF.

**Expected:** All confirmed fields present; internal notes absent; company logo rendered (not broken).

---

### R8 — Company logo in PDF (WebP to PNG conversion)

1. Ensure the company has a logo set (Settings → General Settings → Company → Logo).
2. Generate a PDF via **Mark as Sent for Signature**.
3. Open the attachment and confirm the company logo renders as an image, not a broken image icon.

**Expected:** Logo renders correctly in the PDF even when stored as WebP.

---

### R9 — Multi-company isolation

This check requires two companies to be configured.

1. Log in as a user whose active company is Company A.
2. Create an agreement. Confirm it shows `company_id = Company A`.
3. Switch the active company to Company B.
4. Navigate to **Legal → Legal**.
5. Confirm Company A's agreement is not visible in the list.
6. Create a new agreement with Company B active.
7. Confirm it receives a reference from Company B's sequence independently (e.g. `AGR/2026/00001` for Company B, separate counter from Company A).
8. Switch back to Company A and confirm Company B's agreement is not visible.

**Expected:** Agreement records are isolated per company; each company has its own independent sequence counter.

---

### R10 — Stock movement link

1. Confirm a suitable agreement is in **Active** state.
2. In the Internal tab, confirm the **Linked Stock Movements** section shows the linked pickings (if any bridge has created them).
3. Open any linked picking and confirm the **Agreement** field is populated with the correct agreement reference.

**Expected:** `stock.picking.agreement_id` correctly references the parent agreement; inverse `picking_ids` shows all linked movements on the agreement form.

---

### R11 — Sequence customisation (developer mode)

1. Activate developer mode.
2. Navigate to **Settings → Technical → Sequences & Identifiers → Sequences**.
3. Search for "SOR Agreement".
4. Confirm one sequence row exists per company.
5. Click the main company row and change the next number to `100`.
6. Create a new agreement and confirm the reference is `AGR/YYYY/00100`.

**Expected:** Sequence is user-editable; changes take effect on the next agreement created.

---

### R12 — Legal menu accessibility

1. Log in as a standard internal user (not admin).
2. Confirm the **Legal** item appears in the top navigation bar.
3. Click **Legal → Legal** and confirm the agreements list opens.
4. Confirm agreements from other companies are not visible.

**Expected:** Menu visible to all internal users; list scoped to the user's active company.

---

### R13 — Readonly field protection after PDF generation

1. Create a new agreement in Draft state. Confirm all fields (counterparty, type, dates, lines, terms) are editable.
2. Click **Mark as Sent for Signature**. Confirm the agreement moves to Pending Signature.
3. Attempt to edit the Counterparty, Agreement Type, Start Date, End Date, Lines tab, or Terms and Conditions tab.
4. Confirm all fields are read-only and cannot be modified.
5. Confirm the **Internal** tab notes field remains editable.
6. Click **Confirm Signed** to advance to Active. Confirm fields remain read-only.
7. Click **Close Agreement**. Confirm fields remain read-only in Closed state.

**Expected:** Legally significant fields locked in all non-Draft states; internal notes always editable.

---

### R14 — Draft PDF on save

1. Create a new agreement (click **New**, fill in Counterparty and Terms, save).
2. Confirm a `(Draft).pdf` attachment is visible in the chatter immediately after the first save.
3. Edit the Terms field (change any text) and save again.
4. Confirm the old `(Draft).pdf` attachment has been replaced — only one `(Draft).pdf` attachment is present in the chatter, and it reflects the updated content.
5. Click **Mark as Sent for Signature**.
6. Confirm the `(Draft).pdf` attachment is gone and replaced with `AGR/...NNNNN.pdf` (the final PDF, no draft suffix).

**Expected:** Draft PDF generated and replaced on every save; removed and replaced with final PDF on send.

---

### R15 — Rescind creates replacement

1. Open an agreement in **Pending Signature** or **Active** state.
2. Confirm the **Rescind** button is visible in the header.
3. Click **Rescind**. Confirm the browser shows a confirmation dialog.
4. Confirm the dialog and wait for navigation.
5. Confirm the browser has opened a new Draft agreement with reference "New Agreement" (pre-save) or a fresh `AGR/...NNNNN` reference (post-save).
6. Confirm the new agreement has a **Supersedes** field pointing to the original agreement.
7. Confirm the new agreement's Lines tab contains the same lines as the original.
8. Navigate back to the original agreement. Confirm its state is **Revoked**.
9. Confirm the original shows a **Superseded By** field pointing to the new agreement.
10. Confirm the original is shown muted in the list view.

**Expected:** Original moves to Revoked; replacement Draft created with lines carried over and supersession link in place; list row muted.

---

### R16 — Overdue filter shows stale agreements

1. Create an agreement. Advance it to **Pending Signature**.
2. In the list view, apply the **Overdue** filter from the search bar.
3. Confirm the agreement does not appear (it was sent today, less than 14 days ago, and `date_end` is not within 7 days).
4. (To test staleness by date) Set `date_end` on the agreement to a date within 7 days from today.
5. Save and refresh. Apply the **Overdue** filter again.
6. Confirm the agreement now appears.
7. Confirm the list row shows an amber/warning decoration (the `decoration-warning="is_stale"` attribute on the list view).

**Expected:** Overdue filter correctly identifies stale agreements; warning decoration applied to stale rows.

---

### R17 — Staleness cron notification

1. Activate developer mode.
2. Navigate to **Settings → Technical → Scheduled Actions**.
3. Search for "SOR Legal: Notify stale agreements".
4. Confirm the cron is active (Active = True, daily interval).
5. Confirm a stale agreement exists (state = Pending Signature, `last_stale_notified` = False, and either sent more than 14 days ago or expiring within 7 days).
6. Click **Run Manually** on the cron record.
7. Open the stale agreement. Confirm a new chatter note has been posted: "This agreement is overdue for signature. Please follow up with the counterparty."
8. Confirm `last_stale_notified` is now set to today.
9. Run the cron again manually.
10. Confirm no second notification has been posted (because `last_stale_notified` is now set).

**Expected:** Cron notifies followers once per stale agreement; `last_stale_notified` prevents duplicate notifications on subsequent runs.

---

## Interoperability

| Module | Relationship | Effect when both installed |
|--------|-------------|---------------------------|
| `sor_artwork` | Vertical — no bridge yet | No automatic interaction. A future `sor_legal_agreement_artwork` bridge would link artwork products to agreement lines and expose agreements on the artwork form. |
| `sor_locations` | Horizontal — no bridge yet | No automatic interaction. A future bridge could link a Viewing Location to an agreement (e.g. loan-to-institution terms). |
| `sor_locations_artist_studios` | Horizontal bridge — no bridge yet | No automatic interaction. A future bridge could make an Artist Studio the counterparty party anchor for consignment agreements. |
| `sor_asset_paradigm` | Horizontal — independent | No interaction. Asset paradigm governs inventory UI suppression; legal agreements are a separate concern. Both modules install and operate independently. |
| `sor_business_model` | Horizontal — independent | No interaction. Business model governs commerce UI suppression; legal agreements operate regardless of the company's business model. |
| `sor_contact_roles` | Horizontal — no bridge yet | No automatic interaction. A future bridge could restrict `primary_partner_id` to partners with specific SOR contact roles (e.g. Artist, Collector). |
| `stock` (Odoo core) | Direct dependency | `sor_legal_agreement` adds `agreement_id` to `stock.picking`. All pickings gain this optional link field regardless of whether any SOR agreement is in use. |
| `product` (Odoo core) | Direct dependency | `sor.agreement.line.product_id` references `product.template`. No changes to the product model itself. |
