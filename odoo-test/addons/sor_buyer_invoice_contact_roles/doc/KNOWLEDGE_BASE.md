# SOR Buyer Invoice × Contact Roles Bridge: Knowledge Base

## 1. Overview

**What this module does:** Overrides Odoo 19's `base.res_partner_rule` record rule to allow
art-world contacts (`partner_share=True`, `company_id=False`) to remain visible to internal
users via related field traversal. This fixes a silent blank-field issue on buyer invoices
where `account.move.partner_ref` (a `related='partner_id.ref'` field) returned empty for
bidder contacts because the ORM filtered them out before traversing the relation.

**What this module does NOT do:** It does not add any new models, fields, or UI surfaces.
It is a pure security rule adjustment — a single `ir.rule` override.

**Why it is a bridge:** The issue only manifests when both `sor_buyer_invoice` and
`sor_contact_roles` are installed together. Art-world contacts created via `sor_contact_roles`
have `partner_share=True` and `company_id=False`; Odoo 19's core partner rule restricts their
visibility. Without this bridge, the `partner_ref` field on buyer invoices silently shows blank
for all bidder contacts, regardless of whether their `res.partner.ref` is set.

**Dependencies:** `sor_buyer_invoice`, `sor_contact_roles`  
**Auto-installs:** Yes — activates automatically when both parents are installed.

---

## 2. Key fields and models

No new models or fields are introduced. The bridge modifies one `ir.rule` record:

| Rule XML ID | Model | Purpose |
|-------------|-------|---------|
| `base.res_partner_rule` | `res.partner` | Partner record visibility rule; overridden to relax `partner_share` restriction |

**Installed domain (overridden):**

```python
['|', ('partner_share', '=', False),
 '|', ('company_id', '=', False),
      ('company_id', 'in', company_ids)]
```

This domain ensures:
- Internal users (`partner_share=False`) are always visible — no change from Odoo default.
- Contacts with no company (`company_id=False`) are visible — **this is the key relaxation**.
- Contacts assigned to one of the user's accessible companies are visible — no change from Odoo default.

Without this override, art-world contacts (who have `company_id=False` by default) are excluded
from the user's view whenever `partner_share=True` on the contact record, which is the default
for any contact without an Odoo user account.

---

## 3. Methods

No methods are added or overridden by this bridge. All behaviour is provided by the `ir.rule`
record installed in `security/sor_buyer_invoice_contact_roles_rules.xml`.

---

## 4. Configuration

No configuration is required. The rule is applied automatically when the module is installed.

To inspect the installed rule in developer mode:
- Navigate to **Settings → Technical → Rules** (developer mode required).
- Search for "partner" in the Name column.
- Open the `res.partner` rule to confirm the domain is the relaxed version above.

---

## 5. Developer menu

This module adds no developer menu items.

---

## 6. Building on this module

**If you add a new feature that reads `partner_id.ref` (or any `related` field traversal
through `res.partner`) on `account.move` or any other model linked to bidder/consignor
contacts:** this bridge already ensures those partners are visible, so no additional rule
override is needed.

**If a future module introduces a new population of art-world contacts** (consignors, lenders,
donors) that also have `partner_share=True` and `company_id=False`, and those contacts are
referenced via `related` field traversals from accounting or other models, this bridge already
covers them — no additional override per module type is required.

**If you need to remove the relaxation for a specific model** (e.g. restrict visibility per
model rather than globally), create a new `ir.rule` on that model rather than modifying this
override — the `res.partner` rule is a global rule; per-model restrictions belong on the
dependent models.

---

## 7. Regression checks

R1. **Customer Code populated on buyer invoice (standard path):** Navigate to an auction event
    with generated buyer invoices. Open a buyer invoice for a bidder contact whose
    `res.partner.ref` is set. Confirm the **Customer Code** field shows the reference value.
    Without this bridge, the field is blank even when `ref` is set on the partner.

R2. **No error for contacts without ref:** Open a buyer invoice for a bidder with no
    `res.partner.ref`. Confirm the Customer Code field is blank — no `AccessError` or
    validation error is raised.

R3. **Testlab standalone (Group 1 check):** On a blank `odoo_testlab` with only
    `sor_buyer_invoice` installed (no `sor_contact_roles`), confirm this bridge is absent.
    Customer Code behaviour is unchanged from before this sprint.

R4. **Testlab combined (Group 2 check):** On `odoo_testlab` with both parents installed,
    confirm this bridge auto-installs and the `base.res_partner_rule` domain is the relaxed
    version.

---

## 8. Interoperability

| Installed with | Interaction |
|----------------|-------------|
| `sor_buyer_invoice` only | Bridge not present — `base.res_partner_rule` unchanged |
| `sor_contact_roles` only | Bridge not present — `base.res_partner_rule` unchanged |
| Both parents | Bridge installs — `base.res_partner_rule` domain relaxed to include `company_id=False` clause |
| `sor_buyer_invoice_auction_house` | No additional interaction — this bridge fixes visibility at the `account.move` / `res.partner` layer, which all invoice modules depend on |
| `sor_auction_documents` | No additional interaction — document PDFs do not traverse `partner_id.ref` |
