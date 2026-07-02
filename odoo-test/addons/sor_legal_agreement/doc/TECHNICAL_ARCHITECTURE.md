# Technical Architecture: sor_legal_agreement

## Overview

`sor_legal_agreement` is a **horizontal base module** providing the legal agreement infrastructure for all SOR agreement workflows. It introduces the `sor.agreement` model — a company-scoped document that ties a counterparty, effective dates, a list of products, and terms and conditions together as the authoritative legal basis for physical movements of goods.

The module is **asset-agnostic**: it knows nothing about artworks, consignments, loans, or any specific domain. It depends only on `product` and `stock`, carries no dependency on any other SOR module, and is designed to be extended by bridge modules that add domain-specific fields, filtering, and movement logic.

```
      product        stock
          \            /
           \          /
       sor_legal_agreement      (auto_install=False, application=False)
                |
                |  ← bridge modules attach here
     sor_legal_agreement_artwork
     sor_legal_agreement_consignment
     sor_legal_agreement_docuseal
     ...
```

The module sits at the horizontal layer of the SOR composability grid — alongside `sor_asset_paradigm`, `sor_business_model`, and `sor_locations`. Bridges cross this horizontal layer with the vertical asset modules (`sor_artwork`, etc.) or with operational modules (`sor_consignments`, etc.).

---

## Module Pattern

**Manifest flags:**

```python
'category': 'Hidden/Technical',
'depends': ['product', 'stock'],
'auto_install': False,
'application': False,
'post_init_hook': 'post_init_hook',
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `False` | The module is an intentionally-installed building block, not a bridge. |
| `application` | `False` | Not a top-level app — it is infrastructure for bridge modules and domain sprints. |
| `category` | `'Hidden/Technical'` | Keeps the module out of business category listings in the Apps menu. |
| `depends` | `['product', 'stock']` | `product` is needed for `product.template` on agreement lines; `stock` is needed for the `stock.picking` relationship. `mail` is available transitively via `stock` and is not declared explicitly. |
| `post_init_hook` | `'post_init_hook'` | Creates per-company agreement sequences for all companies that exist at install time. The data XML creates only the main-company sequence; the hook covers all others. |

**Why no SOR module dependencies?**

`sor_legal_agreement` is a horizontal base module. Adding a dependency on `sor_artwork`, `sor_contact_roles`, or any other SOR vertical module would couple the legal layer to a specific asset domain and prevent installations that use legal agreements with non-artwork assets. All SOR-to-SOR coupling is handled through bridge modules. This is the enforceable composability constraint.

---

## Architecture Decisions

### 1. `product.template` on agreement lines (not `artwork_id`)

`sor.agreement.line.product_id` is `Many2one('product.template')` with no domain filter. The base module is asset-agnostic; using `artwork_id` or any asset-specific reference on the line would couple the legal layer to the artwork vertical. Bridge modules add domain-specific filtering and display via `selection_add` on `agreement_type` and view inheritance on the inline list.

### 2. No picking helper in the base

The module provides only the data relationship: `picking_ids = One2many('stock.picking', 'agreement_id')` on the agreement and the inverse `agreement_id = Many2one('sor.agreement')` on `stock.picking`. Movement creation is entirely the bridge's responsibility. A `create_picking()` helper in the base would bake asset-type or movement-type assumptions into a horizontal module.

### 3. State machine as explicit `UserError` guards (no FSM decorator)

State transitions are enforced via explicit guards in each action method (`if self.state != 'draft': raise UserError(...)`). Odoo 19 Community does not ship a built-in FSM decorator. Explicit guards are cleaner, more readable, and avoid a phantom dependency on Enterprise.

### 4. `_render_qweb_pdf` + `ir.attachment.create` (not `report_action`)

`action_send_for_signature` and `_generate_draft_pdf` both use `report._render_qweb_pdf(xml_id, res_ids=self.ids)` followed by an explicit `ir.attachment.create(...)` call. This is deliberate: `report_action` renders the PDF and returns an action dict for the client — it does not attach the PDF to the record. Using `_render_qweb_pdf` gives server-side control over the attachment lifecycle. The XML ID string is passed as the first argument (not `self.ids`) because Odoo 19 changed the `_render_qweb_pdf` signature: `(report_ref, res_ids=None, data=None)`.

### 5. Per-company sequences: three-layer pattern

The sequence `AGR/YYYY/NNNNN` is per-company. Three mechanisms maintain invariant coverage:
- **Data XML** — creates the sequence for `base.main_company` at install time.
- **`post_init_hook`** — creates sequences for all other companies that exist at install time, skipping any that already have one (idempotent).
- **`res.company.create` override** — creates a sequence for every newly-created company going forward.

The sequence is fetched via `env['ir.sequence'].with_company(company).next_by_code('sor.agreement')` to ensure the counter used belongs to the record's company, not the user's current session company.

### 6. `logo_pdf` computed field on `res.company`

wkhtmltopdf 0.12.6 does not support WebP images. Odoo 19 stores all images (including company logos) as WebP via `ir.attachment`. A `logo_pdf` computed field (`store=False`) on `res.company` converts `logo_web` from WebP to PNG using Pillow. The QWeb report template inherits `web.external_layout_standard` to substitute `logo_pdf` for the standard logo `<img>`. See Special Concerns for the PIL `_initialized` gate and `bin_size=False` details.

### 7. `ondelete='set null'` on `stock.picking.agreement_id`

The `agreement_id` field on `stock.picking` uses `ondelete='set null'`. Deleting an agreement does not cascade-delete the associated pickings — the agreement reference is cleared and the pickings remain. This is correct: physical movements have independent operational existence and must not be removed when a legal document is deleted.

### 8. Deletion protection: only Draft agreements may be deleted

Once an agreement has been sent for signature it has legal significance and must not be deleted. `sor.agreement.unlink()` raises `UserError` for any non-Draft state (including `revoked`). Non-draft agreements must be closed (`action_close`) or rescinded (`action_rescind`) rather than deleted. This was identified as a Category 2a finding at Show & Tell and retrofitted in Development.

### 9. Bridge extension points

The base module exposes three clean extension points for bridge modules:
- **`agreement_type` selection field**: bridges add domain-specific types via `selection_add`.
- **`report_sor_agreement` QWeb template**: bridges extend it via `t-inherit` to add domain-specific sections.
- **Form view (`view_sor_agreement_form`)**: bridges inherit it via `inherit_id` to add fields, pages, and buttons.

Bridge modules must not modify the base module's `sor.agreement` model directly — they use model inheritance (`_inherit = 'sor.agreement'`) to extend it.

### 10. `_check_company_auto = True` but no `check_company=True` on line's `product_id`

`sor.agreement` sets `_check_company_auto = True` to validate that all `check_company=True` Many2one fields reference records belonging to the same company. `primary_partner_id` carries `check_company=True` — `res.partner` has a `company_id`. However, `sor.agreement.line.product_id` does **not** carry `check_company=True`: `sor.agreement.line` has no `company_id` field of its own, and Odoo 19 emits a warning ("Couldn't generate a company-dependent domain for field sor.agreement.line.product_id") when `check_company=True` is declared on a field whose model has no `company_id`. Company isolation for product selection is inherited from the parent `sor.agreement` via `_check_company_auto`.

### 11. Draft PDF generated on every write — not on demand

`_generate_draft_pdf()` is called from both the `create` override and the `write` override for all records in `draft` state. This keeps the chatter preview current as the agreement content evolves, without requiring a manual "Preview" action. The design trade-off: every draft write triggers a wkhtmltopdf render. At the expected write frequency for legal agreements (low-volume, deliberate edits), this is acceptable. If write frequency increases (e.g. programmatic batch creation), consider introducing a `skip_draft_pdf` context key to suppress generation in batch paths.

The existing `(Draft).pdf` attachment is removed and replaced on each call — the chatter does not accumulate multiple draft versions. This is an explicit delete-then-create pattern rather than an in-place update, which avoids stale cached attachment data in the browser.

### 12. `write()` override fires `_generate_draft_pdf()` always for draft records

The `write` override calls `_generate_draft_pdf()` unconditionally for any record that is in `draft` state after the write. It does not attempt to determine which fields changed before deciding whether to regenerate. This is intentionally conservative: tracking field-level changes to suppress PDF generation would add complexity without meaningful benefit at current write frequency, and a stale draft PDF is worse than a slightly redundant render call.

### 13. `partner_ids` in `message_post` for staleness notifications

The staleness cron (`_action_notify_stale_agreements`) passes `partner_ids=follower_partner_ids` explicitly in its `message_post` call, even though it targets the `mail.mt_note` subtype (Internal Note). This is required because `mt_note` only notifies followers who have explicitly subscribed to "Internal Notes" — followers subscribed to "Discussions" or other subtypes do not receive `mt_note` posts. Passing `partner_ids` explicitly bypasses the subscription-type filter and delivers the notification to all current followers regardless of their subscription preferences. This ensures the alerting is operationally reliable in a context where follower subscription types may not be carefully maintained.

### 14. `_search_is_stale` operator normalisation (Odoo 19)

Before invoking a Boolean field's `search=` method, Odoo 19's domain optimiser normalises `'='` to `'in'` with an `OrderedSet` value, and `'!='` to `'not in'` with an `OrderedSet` value. A naive `_search_is_stale` that only checks `operator == '='` would never match — the operator has already been rewritten by the time the method is called.

The canonical unwrap pattern used in `_search_is_stale`:

```python
if operator == 'in':
    operator, value = '=', (True in value)
elif operator == 'not in':
    operator, value = '!=', (True in value)
```

This restores the semantic operator/value pair before evaluating the condition. The same pattern must be applied in any `_search` method on a computed Boolean field anywhere in SOR. See `odoo_conventions.md` for the full reference.

### 15. `copy=True` on `line_ids` and the rescind copy semantics

`fields.One2many` defaults to `copy=False` in Odoo. `line_ids` explicitly declares `copy=True` so that `self.copy(...)` inside `action_rescind()` carries the lines to the replacement draft. Without this, the replacement would always start with zero lines — requiring the user to manually re-enter all covered products.

Fields that must NOT be copied (audit metadata, stock movement links, sequence number, supersession reference, staleness tracking date) are left at the default `copy=False`:

| Field | Copy decision | Reason |
|-------|--------------|--------|
| `line_ids` | `copy=True` | Content lines must carry to the replacement |
| `picking_ids` | `copy=False` (default) | Physical movements must never be duplicated |
| `name` | `copy=False` | Replacement gets a fresh sequence number |
| `state` | `copy=False` | Reset to `draft` explicitly in `action_rescind` |
| `supersedes_id` | `copy=False` | Audit metadata belongs to the original only |
| `date_sent_for_signature` | `copy=False` | Audit metadata — replacement has not been sent |
| `last_stale_notified` | `copy=False` | Replacement starts fresh on notification tracking |

---

## Models

### `sor.agreement`

Primary model. Inherits `mail.thread` and `mail.activity.mixin` for chatter.

| Field | Type | Notes |
|-------|------|-------|
| `name` | `Char` | Auto-assigned from sequence on create (`AGR/YYYY/NNNNN`). `copy=False`. `default='New Agreement'`. |
| `company_id` | `Many2one('res.company')` | Required. `default=lambda self: self.env.company`. |
| `agreement_type` | `Selection` | Base selection: `[('base', 'Base Agreement')]`. Bridges extend via `selection_add`. |
| `primary_partner_id` | `Many2one('res.partner')` | The counterparty. `check_company=True`. |
| `date_start` | `Date` | Effective date. |
| `date_end` | `Date` | End date. Optional. Used in staleness computation. |
| `state` | `Selection` | `draft / pending_signature / active / closed / revoked`. `default='draft'`. `required=True`. `copy=False`. `tracking=True`. |
| `terms` | `Html` | Terms and conditions. Rendered as `<div t-field="..."/>` in QWeb to preserve block-level formatting. |
| `notes` | `Text` | Internal notes. Not included in the PDF. Always editable. |
| `line_ids` | `One2many('sor.agreement.line', 'agreement_id')` | Agreement lines (products involved). `copy=True` — carried to replacement on rescind. |
| `picking_ids` | `One2many('stock.picking', 'agreement_id')` | Stock movements linked by bridge modules. Read-only in the form. `copy=False`. |
| `supersedes_id` | `Many2one('sor.agreement')` | The original agreement this record replaces. Set by `action_rescind()` on the replacement. `copy=False`. `readonly=True`. |
| `superseded_by_id` | `Many2one('sor.agreement')` (computed, `store=False`) | Inverse lookup: the replacement that supersedes this record. Computed via `search([('supersedes_id', '=', rec.id)], limit=1)`. |
| `date_sent_for_signature` | `Date` | Set by `action_send_for_signature()`. Used to compute staleness. `copy=False`. `readonly=True`. |
| `is_stale` | `Boolean` (computed, `store=False`) | `True` when state is `pending_signature` and the agreement is overdue (sent >14 days ago, or `date_end` within 7 days). Has `search='_search_is_stale'`. |
| `last_stale_notified` | `Date` | Set by the staleness cron after notification. Prevents duplicate notifications. `copy=False`. `readonly=True`. |

**Model-level attributes:**

| Attribute | Value | Notes |
|-----------|-------|-------|
| `_name` | `'sor.agreement'` | |
| `_description` | `'SOR Agreement'` | |
| `_order` | `'name desc'` | Most recently created agreements appear first. |
| `_inherit` | `['mail.thread', 'mail.activity.mixin']` | Chatter and activity support. |
| `_check_company_auto` | `True` | ORM validates `check_company=True` fields on write. |

**Methods:**

| Method | Signature | Purpose |
|--------|-----------|---------|
| `create` | `@api.model_create_multi` | Assigns sequence number when `name == 'New Agreement'`. Uses `with_company(company)`. Calls `_generate_draft_pdf()` on new draft records. |
| `write` | `(self, vals)` | Standard write, then calls `_generate_draft_pdf()` on records still in `draft` state. |
| `_generate_draft_pdf` | `(self)` | Renders the agreement PDF, removes any existing `(Draft).pdf` attachment, creates a fresh one. Called on every draft write. |
| `_compute_superseded_by_id` | `(self)` | `search([('supersedes_id', '=', rec.id)], limit=1)` for each record. |
| `_compute_is_stale` | `(self)` | Computes staleness based on `state`, `date_sent_for_signature`, and `date_end`. |
| `_search_is_stale` | `(self, operator, value)` | Translates `is_stale` domain filter to concrete stored-field domain. Handles Odoo 19 `'in'`/`'not in'` operator normalisation. |
| `_check_can_trigger_movement` | `(self)` | Bridge contract: raises `UserError` if any record in `self` is not `active`. Bridges must call this before creating `stock.picking` records. |
| `unlink` | `(self)` | Raises `UserError` for any non-Draft record. Only Draft agreements may be deleted. |
| `action_send_for_signature` | `(self)` | `ensure_one()`. Validates `state == 'draft'`. Renders final PDF, removes draft preview attachment, attaches final PDF. Writes `state = 'pending_signature'` and sets `date_sent_for_signature`. Posts to chatter. |
| `action_confirm_signed` | `(self)` | `ensure_one()`. Validates `state == 'pending_signature'`. Writes `state = 'active'`, posts to chatter. |
| `action_close` | `(self)` | `ensure_one()`. Validates `state == 'active'`. Writes `state = 'closed'`, posts to chatter. Terminal. |
| `action_rescind` | `(self)` | `ensure_one()`. Validates `state in ('pending_signature', 'active')`. Writes `state = 'revoked'`, posts chatter note. Calls `self.copy(...)` to create a Draft replacement with `supersedes_id` set. Returns window action opening the replacement. |
| `_action_notify_stale_agreements` | `(self)` | Cron target. Finds stale agreements with `last_stale_notified = False`. Posts follower notifications with explicit `partner_ids`. Sets `last_stale_notified = today`. |

---

### `sor.agreement.line`

Inline line model. One row per product covered by the agreement.

| Field | Type | Notes |
|-------|------|-------|
| `agreement_id` | `Many2one('sor.agreement')` | Required. `ondelete='cascade'`. Deleting the agreement removes its lines. |
| `product_id` | `Many2one('product.template')` | Required. No domain filter — the base module is asset-agnostic. Bridges add domain filtering via view inheritance. No `check_company=True` (see Architecture Decision 10). |

**Model-level attributes:**

| Attribute | Value |
|-----------|-------|
| `_name` | `'sor.agreement.line'` |
| `_description` | `'SOR Agreement Line'` |
| `_order` | `'agreement_id, id'` |

---

### `res.company` (extended)

| Field | Type | Notes |
|-------|------|-------|
| `logo_pdf` | `Binary` (computed) | `store=False`. Converts `logo_web` (WebP) to PNG for wkhtmltopdf compatibility. See Special Concerns. |

**Methods added:**

| Method | Signature | Purpose |
|--------|-----------|---------|
| `_compute_logo_pdf` | `(self)` | Reads `logo_web` with `bin_size=False` context, decodes from base64, converts WebP → PNG via Pillow, returns base64-encoded PNG. |
| `create` | `@api.model_create_multi` | Extended to create an `ir.sequence` with code `sor.agreement` for every newly-created company. |

---

### `stock.picking` (extended)

| Field | Type | Notes |
|-------|------|-------|
| `agreement_id` | `Many2one('sor.agreement')` | Optional reference to the governing agreement. `ondelete='set null'` — deleting the agreement clears this field; it does not delete the picking. No `check_company=True` (bridge modules are responsible for domain-appropriate company scoping on their picking creation logic). |

---

## Views

### `view_sor_agreement_form` — Agreement form view

**Primary view** for `sor.agreement`. Not an inherited view — it is the root form view for the model.

**Header:**
- "Mark as Sent for Signature" button: `invisible="state != 'draft'"`. Calls `action_send_for_signature`. `class="btn-primary"`.
- "Confirm Signed" button: `invisible="state != 'pending_signature'"`. Calls `action_confirm_signed`. `class="btn-primary"`.
- "Close Agreement" button: `invisible="state != 'active'"`. Calls `action_close`.
- "Rescind" button: `invisible="state not in ('pending_signature', 'active')"`. Calls `action_rescind`. Renders a browser confirmation dialog (`confirm="..."` attribute) before executing.
- `state` statusbar widget: `statusbar_visible="draft,pending_signature,active,closed,revoked"`.

**Sheet:**
- Title group: `name` field, `readonly="1"` (reference is always sequence-generated).
- Left group: `agreement_type`, `primary_partner_id`, `company_id` (visible only when `groups="base.group_multi_company"`). All locked when `state != 'draft'`.
- Right group: `date_start`, `date_end`. Both locked when `state != 'draft'`.
- Supersession group: conditionally visible (`invisible="not supersedes_id and not superseded_by_id"`). Shows `supersedes_id` (the agreement this record replaced) and `superseded_by_id` (the replacement that superseded this record). Both read-only.
- Notebook with three pages:
  - **Lines**: inline editable list of `line_ids` showing `product_id`. Locked when `state != 'draft'`.
  - **Terms and Conditions**: full-width `terms` Html field. Locked when `state != 'draft'`.
  - **Internal**: `notes` text field (always editable); read-only list of `picking_ids` (name, state, scheduled_date).

**Chatter:** `<chatter/>` after the sheet.

---

### `view_sor_agreement_list` — Agreement list view

| Column | Widget / decoration |
|--------|---------------------|
| `is_stale` | `column_invisible="1"` — in arch for `decoration-warning` resolution; not visible as a column |
| `name` | — |
| `agreement_type` | — |
| `primary_partner_id` | — |
| `date_start` | — |
| `date_end` | — |
| `state` | `widget="badge"` with `decoration-success` (active), `decoration-warning` (pending\_signature), `decoration-info` (draft), `decoration-muted` (closed), `decoration-danger` (revoked) |

Row-level decoration:
- `decoration-muted="state in ('closed', 'revoked')"` — both terminal states render rows muted.
- `decoration-warning="is_stale"` — overdue Pending Signature rows render with an amber warning. `is_stale` must be declared in the arch (as `column_invisible="1"`) for the decoration expression to resolve.

---

### `view_sor_agreement_search` — Agreement search view

**Search fields:** `name` (labelled "Reference"), `primary_partner_id` (labelled "Counterparty").

**Filters:** Draft, Pending Signature, Active, Closed, Revoked — each a direct `state` equality domain. **Overdue** — `domain="[('is_stale', '=', True)]"` (resolved by `_search_is_stale`).

**Group by:** Counterparty, State, Agreement Type.

---

### `action_sor_agreement` — Window action

Opens `sor.agreement` in list/form mode. Default view pinned to `view_sor_agreement_list`. Search view: `view_sor_agreement_search`.

---

### `external_layout_logo_pdf` — QWeb template override

Inherits `web.external_layout_standard` with `priority="16"` (above Odoo's default priority). Replaces the standard company logo `<img class="o_company_logo_small">` with a version sourced from `company.logo_pdf`. This override is required because Odoo 19 stores images as WebP and wkhtmltopdf cannot render WebP.

```xml
<template id="external_layout_logo_pdf" inherit_id="web.external_layout_standard" priority="16">
    <xpath expr="//img[hasclass('o_company_logo_small')]" position="replace">
        <img t-if="company.logo_pdf" class="o_company_logo_small"
             t-att-src="image_data_uri(company.logo_pdf)" alt="Logo"/>
    </xpath>
</template>
```

---

### `action_report_sor_agreement` — Report action

Registered as `ir.actions.report`, bound to `sor.agreement`, report type `qweb-pdf`. Template: `sor_legal_agreement.report_sor_agreement`. Binding type `report` makes "Agreement" appear in the Action menu on the form and list views.

---

### `report_sor_agreement` — QWeb PDF template

The base agreement PDF template. Content sections:

1. Agreement reference (h2).
2. Agreement type, counterparty, effective date, end date (if set).
3. Items table: product names, `table-layout:fixed` with `word-wrap:break-word` on cells to prevent mid-word breaks.
4. Terms and conditions: `<div t-field="doc.terms"/>` (block element required for Html field formatting).
5. Signature block: two-column table — company signatory column and counterparty column, each with a ruled line and "Name / Title / Date" label.

**Extension point:** Bridge modules extend this template via:

```xml
<t t-inherit="sor_legal_agreement.report_sor_agreement" t-inherit-mode="extension">
    <xpath expr="..." position="after">
        <!-- domain-specific content -->
    </xpath>
</t>
```

---

### Menu structure

```
Legal (menu_sor_root, sequence=110, top-level)
└── Legal (menu_sor_agreements, action=action_sor_agreement)

Settings → Technical → SOR (sor_technical_menu.menu_sor_technical_root)
└── Agreements (menu_sor_technical_agreements, action=action_sor_agreement, groups=base.group_no_one)
```

The `menu_sor_root` top-level "Legal" menu is owned by this module. The Technical SOR root menu (`sor_technical_menu.menu_sor_technical_root`) is owned by the `sor_technical_menu` module. `sor_legal_agreement` registers its own child entry (`menu_sor_technical_agreements`) under that shared root at `sequence=30`. The developer menu entry is hidden from normal users (`groups="base.group_no_one"`) and is only visible in developer mode.

---

## Module File Structure

```
sor_legal_agreement/
├── __init__.py                          # Imports models and post_init_hook
├── __manifest__.py                      # Module manifest; registers post_init_hook
├── hooks.py                             # post_init_hook — creates sequences for existing companies
│
├── models/
│   ├── __init__.py                      # Imports all four model files
│   ├── sor_agreement.py                 # sor.agreement — primary model with state machine, rescind, staleness
│   ├── sor_agreement_line.py            # sor.agreement.line — inline product lines
│   ├── res_company.py                   # res.company extension — logo_pdf field + sequence creation
│   └── stock_picking.py                 # stock.picking extension — agreement_id field
│
├── data/
│   ├── sor_agreement_sequence.xml       # ir.sequence for base.main_company (noupdate="1")
│   └── ir_cron_data.xml                 # Daily staleness alerting cron (noupdate="1")
│
├── security/
│   ├── ir.model.access.csv              # CRUD access for sor.agreement and sor.agreement.line
│   └── sor_agreement_rules.xml          # Multi-company ir.rule (noupdate="1")
│
├── views/
│   ├── sor_agreement_views.xml          # Form, list, and search views for sor.agreement
│   └── sor_agreement_menus.xml          # Window action, top-level menu, Agreements sub-menu, Technical SOR entry
│
├── report/
│   ├── sor_agreement_report.xml         # ir.actions.report + web.external_layout_standard override
│   └── sor_agreement_template.xml       # QWeb PDF template: report_sor_agreement
│
├── tests/
│   ├── __init__.py                      # Test package
│   ├── test_placeholder.py              # Stub (superseded by test_sor_legal_agreement.py)
│   └── test_sor_legal_agreement.py      # Full test suite — all test classes
│
└── doc/
    ├── KNOWLEDGE_BASE.md                # User-facing documentation
    └── TECHNICAL_ARCHITECTURE.md       # This file
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `__manifest__.py` | Declares `depends`, `data` load order, and `post_init_hook`. Load order matters: sequence before security, security before views, views before menus. |
| `models/sor_agreement.py` | Core model. Contains state machine, bridge contract method (`_check_can_trigger_movement`), deletion protection (`unlink`), draft PDF generation (`_generate_draft_pdf`, `create`, `write`), rescind workflow (`action_rescind`), staleness computation (`_compute_is_stale`, `_search_is_stale`), and staleness cron (`_action_notify_stale_agreements`). |
| `models/res_company.py` | WebP→PNG conversion (`logo_pdf`) and per-company sequence creation on `res.company.create`. Contains the explicit `WebPImagePlugin` import that works around Pillow's `_initialized` gate. |
| `hooks.py` | `post_init_hook`: ensures every existing company has a sequence at install time. Must be idempotent — safe to call multiple times. |
| `data/sor_agreement_sequence.xml` | `noupdate="1"` sequence for `base.main_company`. Changes to sequence numbering in production survive module upgrades. |
| `data/ir_cron_data.xml` | `noupdate="1"` daily cron record. Calls `_action_notify_stale_agreements()` on `sor.agreement`. |
| `security/sor_agreement_rules.xml` | `noupdate="1"` multi-company `ir.rule`. Restricts `sor.agreement` record visibility to the user's accessible companies. |
| `report/sor_agreement_report.xml` | Registers `ir.actions.report` and overrides `web.external_layout_standard` for the PNG logo substitution. |
| `report/sor_agreement_template.xml` | Base QWeb template. The stable extension point for bridge modules adding domain-specific PDF content. |
| `tests/test_sor_legal_agreement.py` | Full test suite across multiple test classes: install verification, creation/sequence, state machine, deletion protection, bridge contract, multi-company, rescind, draft PDF, staleness. |

---

## Composability Boundary

The following table describes which features are present under different module installation combinations.

| Feature | `sor_legal_agreement` only | With `sor_artwork` bridge | With `sor_consignments` bridge |
|---------|---------------------------|--------------------------|-------------------------------|
| `sor.agreement` model | ✓ present | ✓ present | ✓ present |
| `sor.agreement.line` model | ✓ present | ✓ present | ✓ present |
| `stock.picking.agreement_id` field | ✓ present | ✓ present | ✓ present |
| `agreement_type` base value | ✓ `base` only | ✓ + artwork-specific types | ✓ + consignment types |
| Agreement line domain filtering | ✗ no filter (all products) | ✓ artwork domain added by bridge | ✓ domain per bridge |
| PDF template base sections | ✓ reference, type, party, dates, items, terms, signature | ✓ + bridge sections | ✓ + bridge sections |
| `_check_can_trigger_movement` contract | ✓ defined, callable | ✓ called by bridge before pickings | ✓ called by bridge before pickings |
| State machine (Draft→Pending→Active→Closed; Revoked) | ✓ present | ✓ present (bridges may add states) | ✓ present |
| Draft PDF on save | ✓ present | ✓ present | ✓ present |
| Rescind & Regenerate | ✓ present | ✓ present | ✓ present |
| Staleness alerting cron | ✓ present | ✓ present | ✓ present |

---

## Special Concerns

### PIL `_initialized` gate and explicit `WebPImagePlugin` import

Pillow uses a lazy plugin registry. `Image.open()` calls `Image.init()` the first time it runs, which loads all registered format plugins and sets `_initialized = 2`. On Odoo 19, this first call happens during server startup (triggered by a core Odoo image operation) before `sor_legal_agreement` is loaded. Once `_initialized == 2`, subsequent `Image.init()` calls are no-ops — they return early without re-scanning plugins. Because `WebPImagePlugin` was not registered during that initial startup call, `Image.open()` cannot decode WebP files and raises `PIL.UnidentifiedImageError`.

The fix: `res_company.py` explicitly imports `WebPImagePlugin` at module load time:

```python
from PIL import (  # noqa: F401 — WebPImagePlugin import registers WEBP in Image.OPEN
    Image,
    WebPImagePlugin,
)
```

Importing `WebPImagePlugin` directly calls `Image.register_open(...)` which inserts the WebP decoder into `Image.OPEN` regardless of `_initialized` state. This is idempotent and safe. The `# noqa: F401` comment suppresses ruff's "imported but unused" warning — the import is intentional side-effect registration.

### `bin_size=False` in `_compute_logo_pdf`

Odoo's HTTP layer sets `bin_size=True` in the rendering context for PDF requests. When `bin_size=True`, ORM `Binary` fields return a human-readable size string (e.g. `b'7.24 KB'`) instead of the actual base64-encoded image bytes. `base64.b64decode` on a size string produces garbage bytes; PIL raises `UnidentifiedImageError`.

The fix: `company.with_context(bin_size=False).logo_web` forces the field to return actual image bytes regardless of the surrounding HTTP context. This must be applied before decoding, not after.

### Multi-company sequence invariant

Three mechanisms maintain the invariant "every `res.company` has exactly one `ir.sequence` with `code='sor.agreement'`":

1. **Data XML** (`data/sor_agreement_sequence.xml`, `noupdate="1"`): creates the sequence for `base.main_company` at install time.
2. **`post_init_hook`** (`hooks.py`): runs once on module install. Iterates all `res.company` records; calls `_ensure_agreement_sequence` which creates the sequence if absent (idempotent skip if present). Covers companies that existed before the module was installed.
3. **`res.company.create` override** (`models/res_company.py`): creates the sequence for every newly-created company going forward.

The `noupdate="1"` flag on both the sequence data XML and the multi-company rule XML is important: it prevents module upgrades (`-u sor_legal_agreement`) from overwriting sequence counters or rule domains that have been customised in production.

### wkhtmltopdf installation and CSS access

wkhtmltopdf is not available in the Debian 13 (bookworm) package repositories. The Dockerfile installs it from the official wkhtmltopdf packaging releases on GitHub (arm64 `.deb`). Additionally, wkhtmltopdf fetches CSS from `web.base.url` at render time — this must be set to `http://localhost:8069` (the internal Odoo port) rather than the Docker host-mapped port (`http://localhost:8080`), which is unreachable from inside the container. This is configured in `docker/odoo.conf` via `report.url = http://localhost:8069`.

### `closed` is terminal

`action_close` transitions `state` to `'closed'`. No `action_reopen` or reverse transition is defined in the base module. Closed is permanently closed. Bridge modules that require a re-open workflow for their domain must define their own transition using `selection_add` to add an intermediate state, and must not add a re-open path to `closed` without explicit PO approval.

### `revoked` is terminal

`action_rescind` transitions `state` to `'revoked'`. No further state transition is possible from Revoked. The revoked agreement is retained in the system as the historical record of the voided document; all workflow continues on the replacement draft created at rescind time. Revoked records are protected from deletion by the `unlink` override — the same guard that protects all non-Draft records.

### chatter via `mail.thread` (implicit `mail` dependency)

`sor.agreement` inherits `mail.thread` and `mail.activity.mixin`. The `mail` module is an implicit dependency of `stock`, so it is always present when `sor_legal_agreement` is installed. `mail` is not declared in `depends` — declaring transitive dependencies explicitly would make the manifest misleading and fragile against future Odoo refactoring.

### Draft PDF write overhead at scale

`_generate_draft_pdf()` is called on every `write()` to a draft agreement. Each call invokes wkhtmltopdf via `_render_qweb_pdf` — a synchronous subprocess. At the write frequency expected for legal agreements (manual, deliberate edits), this is acceptable. For any future programmatic batch path (e.g. agreement import, batch field update), introduce a `skip_draft_pdf=True` context key in `write()` to suppress generation:

```python
def write(self, vals):
    result = super().write(vals)
    if not self.env.context.get('skip_draft_pdf'):
        self.filtered(lambda a: a.state == 'draft')._generate_draft_pdf()
    return result
```

This context key is not currently implemented — document it here as the intended escape hatch if it becomes necessary.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_legal_agreement
```

The test suite comprises multiple test classes:

| Class | What it covers |
|-------|----------------|
| `TestSorLegalAgreementInstall` | Model and field presence after install; new fields from D1 Completions present |
| `TestSorAgreementCreate` | Sequence auto-assignment, default state, company default, line creation, draft PDF attachment on create |
| `TestSorAgreementStateMachine` | All valid transitions and all invalid-state guards; PDF attachment on send; draft PDF removed on send |
| `TestSorAgreementRescind` | `action_rescind` from pending\_signature and active; replacement has correct `supersedes_id`; lines carried; original revoked; `superseded_by_id` inverse resolves correctly |
| `TestSorAgreementDeletion` | Draft deletable; all other states (including revoked) blocked |
| `TestSorAgreementMovementGate` | `_check_can_trigger_movement` passes for `active`, raises for all other states |
| `TestSorAgreementMultiCompany` | Per-company sequence exists; new company gets sequence; sequence used on create |
| `TestSorAgreementStaleness` | `is_stale` True/False for various date combinations; `_search_is_stale` operator normalisation; cron notification posted; `last_stale_notified` prevents duplicates |

PDF rendering in tests is patched via `unittest.mock.patch` on `ir.actions.report._render_qweb_pdf` so the tests do not require wkhtmltopdf to be installed in the test environment.

---

## Story Reference

| Story | Title | Sprint |
|-------|-------|--------|
| `.backlog/previous/Legal Agreements/stories/01_Agreement-Base-Model.md` | `sor.agreement` Base Model and Picking Relationship | Legal Agreements Base |
| `.backlog/previous/Legal Agreements/stories/02_State-Machine.md` | State Machine: Draft → Pending Signature → Active → Closed | Legal Agreements Base |
| `.backlog/previous/Legal Agreements/stories/03_PDF-Template.md` | Base QWeb PDF Report Template | Legal Agreements Base |
| `.backlog/current/Legal Agreements D1 Completions/stories/03_Rescind-Regenerate.md` | Rescind and Regenerate | Legal Agreements D1 Completions |
| `.backlog/current/Legal Agreements D1 Completions/stories/04_Staleness-Alerting.md` | Staleness Alerting | Legal Agreements D1 Completions |
| `.backlog/current/Legal Agreements D1 Completions/stories/05_Draft-PDF-on-Save.md` | Draft PDF on Save | Legal Agreements D1 Completions |
