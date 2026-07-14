# SOR Events — Technical Architecture

## Overview

`sor_events` is a horizontal SOR base module that provides the `sor.event` model — the central event record for all gallery and auction house operations. It sits at the root of the Auction Foundations track (Track D), providing the parent context that auction lot catalogues, buyer registrations, and sale results will hang from in subsequent D2 bridge modules.

The module is type-agnostic at the base level: it knows nothing about artworks, lots, consignments, or any domain-specific content. All domain additions come from context bridge modules (`sor_events_auction`, future `sor_events_exhibition`) that extend `sor.event` via `_inherit` and add type-specific tabs, fields, and navigation.

**Dependency:** `base`, `mail`

---

## Module Pattern

```python
{
    'depends': ['base', 'mail'],
    'auto_install': False,
    'application': False,
    'category': 'Hidden/Technical',
}
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `auto_install` | `False` | Installed explicitly — it is a standalone base module, not a bridge |
| `application` | `False` | Not a top-level app; navigation is provided by context bridges |
| `category` | `Hidden/Technical` | Infrastructure; not surfaced in the App Store |
| `depends: mail` | Required | Chatter (`mail.thread`) and activity tracking (`mail.activity.mixin`) are applied at the base level — a deliberate design choice because event coordination is inherently collaborative and needs log notes |

---

## Architecture Decisions

**Type-agnostic base, content added by bridges**
`event_type` (`exhibition` / `auction`) is declared as a Selection field. Domain content (lot catalogue, artwork lines) is added via bridge modules that use `_inherit = 'sor.event'`. The base module does not filter, branch, or condition on `event_type` — it treats all event types uniformly.

**No user-facing production menu in the base module**
There is no user role whose natural context is a mixed-type event list. Auction staff expect Auctions navigation; exhibition staff expect Exhibitions navigation. A type-agnostic "Events" list has no user who would navigate to it in production. The base module therefore creates only a developer utility menu under Settings → Technical → SOR → Events (`groups="base.group_no_one"`), mirroring the pattern used by `sor_asset_paradigm` and `sor_events` itself. Context bridges create the relevant production menus.

**`archived` status does not use Odoo's `active` field**
The `archived` lifecycle status is implemented as a manual state transition (`action_archive_event()`) that sets `status = 'archived'` — it does NOT set `active = False`. Conflating event lifecycle status with Odoo's archive mechanism would hide archived events from default searches and prevent operators from reviewing closed-cycle event history. Events in `archived` remain visible in the list.

**`date_end` is optional**
End date is not required at creation. Events may be entered before dates are finalised, or for online-only events that have no defined end time. This was confirmed during Show & Tell (Story 02 Finding #2).

**`venue_id` uses `res.partner` with a soft domain**
Venues are physical spaces. `res.partner` with `is_company=True` is used as the reference model to link venues to real address records for reporting. The domain `[('is_company', '=', True)]` is a client-side filter — it does not prevent saving an individual contact as a venue. No `required=True` — online events have no physical venue.

**`company_id` is read-only on the form**
No use case exists for cross-company event creation. Staff create events in the context of their active company. Setting `readonly="1"` on the form field prevents accidental company misassignment (confirmed SOR pattern — same as `sor.agreement`, `sor.lot`).

---

## Models

### sor.event

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `name` | Char | Yes | — | Event name; tracking=True |
| `event_type` | Selection | Yes | — | `exhibition` or `auction`; tracking=True |
| `status` | Selection | Yes | `draft` | Five-stage lifecycle; tracking=True |
| `date_start` | Datetime | Yes | — | tracking=True |
| `date_end` | Datetime | No | — | Optional; tracking=True |
| `venue_id` | Many2one → `res.partner` | No | — | Domain `is_company=True` (soft); `ondelete='restrict'` |
| `company_id` | Many2one → `res.company` | Yes | `env.company` | Read-only on form; no `_check_company_auto` needed (no cross-company Many2one refs) |
| `notes` | Text | No | — | Internal notes |

**Model attributes:**
- `_check_company_auto = True`
- `_order = 'date_start desc'`
- Inherits: `mail.thread`, `mail.activity.mixin`

**Methods:**

| Method | Transition | Guard condition |
|--------|------------|-----------------|
| `action_publish()` | draft → published | `status != 'draft'` → UserError |
| `action_activate()` | published → active | `status != 'published'` → UserError |
| `action_close()` | active → closed | `status != 'active'` → UserError |
| `action_archive_event()` | closed → archived | `status != 'closed'` → UserError |

Each method also calls `message_post()` to log a note to the chatter.

---

## Views

### sor_event_view_form (primary)

Form view with:
- `<header>`: Four action buttons (`Publish`, `Activate`, `Close`, `Archive`), each conditional on the current `status` value. Status bar showing all five statuses.
- `<sheet>`: Two groups — Identification (name, event_type, company_id with multi-company guard) and Schedule (date_start, date_end, venue_id). Notes field below.
- `<chatter/>`: Single self-closing tag (Odoo 19 pattern — `<div class="oe_chatter">` renders as raw list tables in Odoo 19).

### sor_event_view_list (primary)

List view with columns: name, event_type, status, date_start, date_end, venue_id.

### sor_event_view_search (primary)

Search view with:
- Field search: `name`
- Status filters: Draft, Published, Active, Closed, Archived
- Type filters: Exhibition, Auction
- Group by: Type

### Window action (sor_event_action)

Mode: `list,form`. Domain: `[('company_id', '=', allowed_company_ids[0])]`.

---

## Module File Structure

```
sor_events/
├── __init__.py
├── __manifest__.py
├── data/                          (empty — no data records at base level)
├── doc/
│   ├── KNOWLEDGE_BASE.md
│   └── TECHNICAL_ARCHITECTURE.md
├── i18n/
│   └── sor_events.pot
├── models/
│   ├── __init__.py
│   └── sor_event.py               sor.event model, state machine, company isolation
├── security/
│   ├── ir.model.access.csv        read/write/create/delete for base.group_user
│   └── sor_events_rules.xml       multi-company ir.rule (noupdate="1")
├── tests/
│   ├── __init__.py
│   ├── test_placeholder.py
│   └── test_sor_events.py
└── views/
    └── sor_event_views.xml        form, list, search views; window action; developer menu
```

---

## Critical Files

| File | Purpose |
|------|---------|
| `models/sor_event.py` | Core model, state machine methods, company default |
| `views/sor_event_views.xml` | All views and the developer utility menu |
| `security/sor_events_rules.xml` | Multi-company record rule — without this, `company_id` is just a label |
| `security/ir.model.access.csv` | Without this, no user can read or write event records |

---

## Composability Boundary

| Modules installed | Behaviour |
|-------------------|-----------|
| `sor_events` only | `sor.event` model with full lifecycle. Developer utility menu only. No domain-specific content. |
| `sor_events` + `sor_lotting` | No change to either module. Independent horizontals — no bridge yet. |
| `sor_events` + `sor_events_auction` (D2) | Bridge auto-installs. Auction events gain `auction_lot_ids`. User-facing Auctions menu appears. |
| `sor_events` + `sor_events_exhibition` (future) | Bridge auto-installs. Exhibition events gain artwork lines. User-facing Exhibitions menu appears. |

---

## Special Concerns

**Chatter syntax in Odoo 19**
Use `<chatter/>` (single self-closing tag). The legacy `<div class="oe_chatter">` block renders as three raw list tables in Odoo 19 — Related Documents, Activity, and Messages rendered as plain HTML table rows rather than the Discuss component. This was confirmed in Story 02 Finding #1 and is a category 2a finding (known-in-advance from Sprint 06 Legal Agreements documentation).

**Multi-company record rule**
The rule in `security/sor_events_rules.xml` uses `noupdate="1"`. Domain: `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`. The `company_id = False` clause is a safety guard for records where `company_id` was not set — in practice, `required=True` prevents this.

**`_check_company_auto`**
Set to `True` on `sor.event`. `venue_id` → `res.partner` does not carry `check_company=True` because venue partners are typically global records shared across companies (a fairground used by both SO Fine Art and SETU). This matches the documented exception in `sor_multi_company.md`.

---

## Running the Tests

```bash
docker exec odoo-app python3 odoo-bin \
  --addons-path=/mnt/extra-addons,/app/odoo/addons \
  --db_host=postgres --db_port=5432 \
  --db_user=odoo --db_password=admin \
  -d odoo --test-enable --stop-after-init -u sor_events
```

---

## Story Reference

- Story 02: `.backlog/current/Auction Foundations/stories/02_Events-Base-Module.md`
