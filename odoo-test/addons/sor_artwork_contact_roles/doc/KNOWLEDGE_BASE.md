# Knowledge Base: SOR Artwork – Contact Roles Bridge

## Overview

`sor_artwork_contact_roles` is a **bridge module** that links `sor_artwork` and `sor_contact_roles`. It activates automatically when both parent modules are installed and delivers two things: it restricts the `creator_id` field on artworks to contacts who hold the Creator contact role, and it adds an Artworks relationship to Creator contacts — a smart button, a count, and an Artworks tab showing all works attributed to that contact.

**What it provides:**
- A domain restriction on `creator_id` (artwork) that limits the picker to contacts with `is_creator = True`
- `artwork_ids` — a One2many field on `res.partner` listing all artworks attributed to a creator
- `artwork_count` — a computed integer on `res.partner` showing the count of attributed artworks
- An Artworks smart button on Creator contact forms, visible only when the contact has artworks attributed
- An Artworks tab on Creator contact forms listing all attributed works with key metadata
- A deletion guard: prevents a Creator contact from being deleted while artworks are attributed to them
- Company-scoped artwork visibility: the smart button action filters artworks to the active company (plus shared artworks with no company)

**What it does NOT do:**
- Manage artwork records — that is handled by `sor_artwork`
- Manage contact roles or type assignments — that is handled by `sor_contact_roles`
- Provide a Settings toggle or developer menu — the bridge activates automatically and requires no configuration
- Restrict artwork access by company at the field level — company isolation is the responsibility of `sor_artwork`'s own access rules

**Auto-install:** This module installs automatically when both `sor_artwork` and `sor_contact_roles` are present. No manual installation is required.

---

## Prerequisites

- `sor_artwork` installed
- `sor_contact_roles` installed
- When both are present, this bridge auto-installs — no further action needed

---

## Key Fields and Models

### `product.template` (extended)

| Field | Type | Purpose |
|-------|------|---------|
| `creator_id` | Many2one (patched domain) | Domain `[('is_creator', '=', True)]` added by this bridge — restricts the artwork creator picker to contacts with the Creator role. Without this bridge, `creator_id` accepts any partner. |

### `res.partner` (extended)

| Field | Type | Purpose |
|-------|------|---------|
| `artwork_ids` | One2many → `product.template` | All artworks whose `creator_id` points to this partner. Domain filter: `[('product_type', '=', 'artwork')]`. Read-only in the Artworks tab; new artworks can be created from this context. |
| `artwork_count` | Integer (computed, `store=False`) | Count of artworks in `artwork_ids`. Displayed in the smart button. |

---

## Methods

### `res.partner`

| Method | Signature | Purpose |
|--------|-----------|---------|
| `_compute_artwork_count` | `() → None` | Computes `artwork_count` by calling `len(partner.artwork_ids)` for each partner. |
| `action_view_artworks` | `() → dict` | Returns an `ir.actions.act_window` dict for `product.template`. Domain: `[('product_type', '=', 'artwork'), ('creator_id', '=', self.id), '|', ('company_id', '=', env.company.id), ('company_id', '=', False)]`. This company filter ensures the smart button only shows artworks that belong to the user's active company (plus shared artworks with no company). |
| `unlink` | `() → bool` | Override that guards against deletion. Raises `ValidationError` if the partner has `is_creator = True` and has linked `artwork_ids`. Staff must reassign or remove artworks before deleting a creator contact. |

### `product.template`

| Method | Signature | Purpose |
|--------|-----------|---------|
| `_check_creator_is_valid` | `@api.constrains('creator_id')` | Validates that the selected creator has the Creator or Artist contact type (`is_creator` or `is_artist`). Only runs for artwork products. Raises `ValidationError` if neither flag is `True`. **Known limitation:** see Special Concerns in the Technical Architecture. |

---

## Configuration

This bridge has no configuration. The `creator_id` domain restriction, Artworks tab, smart button, and deletion guard are all active as soon as the bridge is installed.

---

## Developer Menu

This bridge adds no developer menu. Contact type management is in `Settings → Technical → SOR → Contact Types` (provided by `sor_contact_roles`). Artwork product management is available through `sor_artwork`'s own navigation.

---

## Building on This Module

Other modules that need to link artwork records to creator contacts already have that relationship available via `product.template.creator_id`. No bridge module needs to depend on `sor_artwork_contact_roles` directly — it adds tooling to existing relationships, not a new relationship.

If a future module needs to traverse from a creator contact to their artworks, use `partner.artwork_ids` (filtered to `product_type = 'artwork'`). The `artwork_count` field is available for smart button counts.

For a bridge that further extends the creator–artwork intersection (e.g. adding exhibition history to the Artworks tab), inherit this bridge's views directly:
- Artwork form domain patch: `ref="sor_artwork_contact_roles.view_product_template_form_creator_domain"`
- Partner Artworks tab: `ref="sor_artwork_contact_roles.view_partner_form_artworks"`

---

## Regression Checks

| # | Check | Expected |
|---|-------|----------|
| R1 | Install both `sor_artwork` and `sor_contact_roles` — confirm bridge auto-installs in Settings → Apps | Bridge appears as installed; no manual install step needed |
| R2 | Open any artwork form. Click the `creator_id` field and use Search More | Only contacts with Creator type (or Creator sub-types) are shown in the search results — contacts with no type, or Contact-only types, are absent |
| R3 | Open a Creator contact with at least one artwork attributed | Artworks smart button is visible in the header and shows the correct count |
| R4 | Click the Artworks smart button on a Creator contact | Action opens filtered list of artworks attributed to this creator; only artworks from the active company (or with no company) are shown |
| R5 | Open a Creator contact with no artworks attributed | Smart button is not visible in the header |
| R6 | Open a non-Creator contact (Contact type only, no Creator) | No Artworks smart button; no Artworks tab |
| R7 | Open a Creator contact — Artworks tab should be first tab in the notebook | Artworks tab appears before the Contacts tab |
| R8 | Open a Creator contact with no artworks — navigate to Artworks tab | Artworks tab is visible (tab exists for creators even when the list is empty); smart button is hidden |
| R9 | Try to delete a Creator contact who has artworks attributed | Error message: "Cannot delete creator '...' because they have N artwork(s)." |
| R10 | Remove all artworks from a Creator contact (or reassign them) then delete the contact | Deletion succeeds |
| R11 | In a multi-company setup: create an artwork in Company A, switch to Company B, open the creator's contact form | Smart button either shows 0 (if count includes Company B artworks only) or is hidden. Company A artworks are not shown in the action result |
| R12 | Uninstall `sor_contact_roles` — confirm bridge also uninstalls (Odoo auto-uninstalls dependent modules) | Both bridge and `sor_contact_roles` are removed; `creator_id` reverts to accepting any partner |

---

## Interoperability

| Module | Relationship |
|--------|-------------|
| `sor_artwork` | Parent module — provides `product.template` with `creator_id` field and artwork product type |
| `sor_contact_roles` | Parent module — provides `res.partner` with `is_creator`, `is_artist` flags; provides Creator/Artist type hierarchy |
| `sor_locations_artwork` | Sibling bridge — adds `current_location_id` to artworks; no dependency or conflict with this bridge |
| `sor_bidding` | Sibling bridge — adds Bidder sub-type assignment; no dependency or conflict with this bridge |
| All future SOR modules | May use `artwork_ids` and `artwork_count` fields on `res.partner` when both parent modules are installed |
