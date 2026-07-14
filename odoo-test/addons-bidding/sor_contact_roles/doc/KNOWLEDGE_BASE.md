# Knowledge Base: SOR Contact Roles

## What is SOR Contact Roles?

`sor_contact_roles` extends Odoo's contact model (`res.partner`) with an art-market contact type system. It defines a two-level hierarchy of contact roles — **parent types** (Creator, Contact) and **sub-types** (Artist under Creator; Bidder, Buyer, Consignor, Donor, Lender under Contact) — and adds type-specific fields and computed flags to each contact.

**What it provides:**
- A seeded set of art-market contact types and sub-types
- A two-level type hierarchy visible on each contact form
- Computed boolean flags (`is_creator`, `is_artist`, `is_contact`, `is_bidder`, etc.) for use in domain filters across all SOR modules
- Type-specific fields: biography, birth date, nationality, social media (Creator); collection focus, preferred artists (Contact)
- Activity-earned sub-type assignment: Contact sub-types (Bidder, Buyer, Consignor, Donor, Lender) are assigned automatically when a contact participates in a relevant transaction — not manually by staff
- Multi-company support: contacts created from the UI are automatically scoped to the active company

**What it does NOT do:**
- Enforce hard uniqueness on type assignments (multiple types are allowed per contact)
- Replace Odoo's own contact model — it extends it
- Manage artwork relationships directly (that is handled by `sor_artwork` and the future `sor_artwork_contact_roles` bridge)
- Provide a Settings → Technical menu for managing contact types (deferred — Sprint Findings F-09)

---

## Prerequisites

- Odoo 19 Community `contacts` module installed.
- No other SOR modules required — `sor_contact_roles` depends only on `contacts`.

---

## Contact Type Hierarchy

```
Creator (code='creator', type_category='creator')
└── Artist (code='artist')           ← staff-selectable

Contact (code='contact', type_category='contact')
├── Bidder    (code='bidder')         ← activity-earned, auto-assigned
├── Buyer     (code='buyer')          ← activity-earned, auto-assigned
├── Consignor (code='consignor')      ← activity-earned, auto-assigned
├── Donor     (code='donor')          ← activity-earned, auto-assigned
└── Lender    (code='lender')         ← activity-earned, auto-assigned
```

**Parent types** are assigned by staff directly in the contact form.

**Contact sub-types** (Bidder, Buyer, Consignor, Donor, Lender) are **activity-earned** — they are assigned automatically when a contact participates in a relevant transaction (e.g. Bidder when they place a bid). Staff cannot manually assign them through the contact form widget (Story 03 controls widget visibility).

**Artist** is the only sub-type that remains staff-selectable. When a staff member assigns the Creator parent type, Artist is pre-selected automatically and can be confirmed or changed.

---

## Guide 1 — Assign a Creator Type

**When to use:** When registering a new artist or creative professional.

### Steps

1. Go to **Contacts** and open an existing contact, or click **New** to create one.
2. In the contact form, find the **Contact Types** field (below the name).
3. Click in the field and select **Creator**.
4. The **Sub-Types** field appears. **Artist** is pre-selected automatically. Confirm or change if needed.
5. Click **Save**.

### Expected outcome

- The contact's type shows **Creator** in the Contact Types field.
- The **Biography**, **Birth Date**, **Nationality**, **Website**, and **Social Media** fields become visible.
- The `is_creator` and `is_artist` computed flags are `True`.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R1 | Contact Types field visible on contact form | Yes |
| R2 | Sub-Types field appears after selecting Creator | Yes |
| R3 | Artist pre-selected in Sub-Types after choosing Creator | Yes |
| R4 | Creator-specific fields (Biography, Birth Date, Social Media) visible after assigning Creator | Yes |

---

## Guide 2 — Assign a Contact Type

**When to use:** When registering a new gallery contact (collector, advisor, etc.) who has an established relationship with the gallery but whose specific transaction role is not yet known.

### Steps

1. Go to **Contacts** and open or create a contact.
2. In the **Contact Types** field, select **Contact**.
3. Click **Save**.

### Expected outcome

- The contact shows **Contact** as their type.
- The **Collection Focus** and **Preferred Artists** fields become visible.
- The `is_contact` and `has_contact_type` flags are `True`.
- No Contact sub-type (Bidder, Buyer, etc.) is assigned at this point — those are assigned automatically when the contact participates in a transaction.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R5 | Selecting Contact type shows Contact-specific fields (Collection Focus, Preferred Artists) | Yes |
| R6 | No Contact sub-types are pre-assigned when Contact parent type is manually selected | Yes |
| R7 | Assigning Bidder sub-type (e.g. via auction system) automatically assigns Contact parent type | Yes |

---

## Guide 3 — Find Contacts by Type

**When to use:** When you want to search or filter contacts by their art-market role.

### Steps

1. Go to **Contacts**.
2. Use the search bar. Type the role name (e.g. "Creator") and select the corresponding filter — or apply a custom filter using the field `Is Creator` equals `True`.
3. The list updates to show only contacts with that flag set.

### Expected outcome

- The filtered list contains only contacts with the selected type.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R8 | Filtering by `is_creator = True` returns only Creator contacts | Yes |
| R9 | Filtering by `is_contact = True` returns only Contact contacts (formerly `is_customer`) | Yes |
| R10 | A contact with both Creator and Contact types appears in both filters | Yes |

---

## Guide 4 — Contact Types Available

The following contact types are seeded by default. All records use `noupdate="1"` — administrator changes made at runtime are not overwritten on module upgrade.

**Parent types:**

| Code | Name | Has sub-types |
|------|------|---------------|
| `creator` | Creator | Yes (Artist) |
| `contact` | Contact | Yes (Bidder, Buyer, Consignor, Donor, Lender) |

**Sub-types (Creator):**

| Code | Name | Assignment |
|------|------|-----------|
| `artist` | Artist | Staff-selectable; auto-selected when Creator is chosen |

**Sub-types (Contact):**

| Code | Name | Assignment |
|------|------|-----------|
| `bidder` | Bidder | Activity-earned — auto-assigned by `sor_bidding` |
| `buyer` | Buyer | Activity-earned — auto-assigned by relevant transaction modules |
| `consignor` | Consignor | Activity-earned — auto-assigned by consignment modules |
| `donor` | Donor | Activity-earned — auto-assigned by donation modules |
| `lender` | Lender | Activity-earned — auto-assigned by loan modules |

**Removed types (no longer in the system):**

The following types existed in earlier versions and have been removed:
- Private Collector, Corporate Collector, Institutions Collection, Dealer, Advisor
- Bidder and Consignor were formerly standalone parent types — they are now Contact sub-types

---

## Guide 5 — Contacts and Multi-Company

**When to use:** In a multi-company SOR deployment (e.g. running a gallery and an auction house as separate Odoo companies).

### Current behaviour (known limitation — see F-12)

When a new contact is created via the Contacts UI, the contact's `Company` field is automatically set to the currently active company. Because all SOR art-world contacts have `partner_share=True` (they are external contacts without Odoo user accounts), Odoo's core `ir.rule` on `res.partner` makes them visible only to users whose active company matches the contact's `company_id`.

> **This is a known limitation tracked as Sprint Findings F-12.** The design intent for SOR is that contacts and creators should be **shared across all companies** (visible from any company context), with `company_id` retained as a provenance field to record which location created the contact. A future sprint will override Odoo's core `res.partner` rule in `sor_contact_roles` to implement this intended behaviour.

> **Note:** Contacts created by Odoo internally — for example, the partner record that backs a `res.company` record — are not scoped to a company. This is intentional: company partner records are globally shared across all companies.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R11 | New contact created via Contacts UI → `company_id` is set to the active company | Yes |
| R12 | Contacts list grouped by Company shows new contacts under the correct company group | Yes |
| R13 | Creating a new Odoo company (`res.company`) does not fail due to a company inconsistency error | Yes |

---

## Computed Flags Reference

| Flag | True when | Used by |
|------|-----------|---------|
| `is_creator` | Creator parent type or any Creator sub-type assigned | `sor_artwork`, `sor_locations_artist_studios` |
| `is_artist` | Artist sub-type assigned | `sor_locations_artist_studios` |
| `is_contact` | Contact parent type assigned | `sor_locations_external` |
| `has_contact_type` | Contact parent type or any Contact sub-type assigned | Form view visibility |
| `has_creator_type` | Creator parent type or any Creator sub-type assigned | Form view visibility |
| `is_bidder` | Bidder sub-type assigned | `sor_bidding` domain filter |
| `is_consignor` | Consignor sub-type assigned | Available for consignment modules |
| `is_donor` | Donor sub-type assigned | Available for donation modules |

## Filtered Sub-Type Fields Reference

Two computed Many2many fields filter `contact_subtypes` by parent type context. These are used in list views to prevent sub-type cross-contamination (e.g. a Bidder tag appearing in the Creator list beside an artist who is also a Bidder).

| Field | Returns | Used in |
|-------|---------|---------|
| `creator_subtypes` | Sub-types from `contact_subtypes` where `parent_type_id.code == 'creator'` | Creator list view (`view_partner_tree_artists`) |
| `contact_role_subtypes` | Sub-types from `contact_subtypes` where `parent_type_id.code == 'contact'` | Contact list view (`view_partner_tree_contacts`), Collector list view (`view_partner_tree_collectors`) |

Both fields are `store=False` computed Many2many. They do not have their own database relation table — they are filters over the existing `contact_subtypes` recordset.

---

## Guide 6 — Contact Types in Developer Mode

**When to use:** When a developer or technical administrator needs to inspect, archive, or modify contact type records directly.

### Steps

1. Enable developer mode: **Settings → Activate Developer Mode**.
2. Navigate to **Settings → Technical → SOR → Contact Types**.
3. The list shows all contact types, including archived ones (rendered in muted text).
4. Click any row to open its form view.

### Expected outcome

- All contact types are visible, including archived types.
- Each row is clickable.

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R14 | Settings → Technical → SOR → Contact Types menu is visible in developer mode | Yes |
| R15 | List includes archived contact types (rendered muted) | Yes |
| R16 | Clicking a row opens the contact type form | Yes |

---

## Guide 7 — Individual/Company Toggle on SOR Contacts

SOR-managed contacts (those with `is_contact=True`) have the Individual/Company toggle hidden in the form view. The contact type (individual or company) was established at creation and should not be changed via the UI.

### Behaviour

- On a contact with `is_contact=True`: the **Individual / Company** toggle is not visible.
- On standard Odoo customers/vendors (`is_contact=False`): the toggle remains fully visible and functional.
- If an attempt is made via the ORM to set `is_company=True` on a partner whose `is_contact=True`, a `ValidationError` is raised with the message: *"SOR-managed contacts cannot be set to Company type. To make this record a company, first remove its SOR contact type assignments."*

### Regression check

| # | Check | Expected |
|---|-------|----------|
| R17 | Open a contact with Contact or Creator type assigned — toggle not visible | Hidden |
| R18 | Open a standard Odoo customer with no SOR types — toggle visible | Visible |
| R19 | ORM write of `is_company=True` on an `is_contact=True` partner raises ValidationError | Error raised |

---

## Interoperability

| Module | Relationship |
|--------|-------------|
| `sor_artwork` | Uses `is_creator` domain on the `creator_id` field; shows `artwork_ids` on creator contacts. Currently a direct dependency (known violation — tracked as spike `sor_artwork_contact_roles`) |
| `sor_locations_external` | Uses `is_contact` (renamed from `is_customer`) to control the External Locations smart button and `contact_id` domain on contact forms |
| `sor_locations_artist_studios` | Uses `is_artist` to link contacts to artist studio locations |
| `sor_bidding` | Uses `is_bidder` domain filter on `bidder_id`; auto-assigns Bidder sub-type when a bid is placed |
| `sor_consignment_agreements` | Auto-assigns Consignor sub-type to the counterparty when a Consignment In agreement is created; sets `is_consignor=True` |
| All future SOR modules | Use `is_*` boolean flags for domain restrictions and UI visibility |
