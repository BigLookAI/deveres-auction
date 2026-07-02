# SOR Events — Knowledge Base

## Overview

`sor_events` is a horizontal SOR module that provides the `sor.event` model — a central event record for gallery and auction house operations. Events carry a type (Exhibition or Auction), a scheduled date range, an optional venue, and a five-stage lifecycle (Draft → Published → Active → Closed → Archived).

**What this module does:**
- Provides the `sor.event` model with type, schedule, status lifecycle, and multi-company isolation.
- Attaches chatter (message thread and activity tracking) to every event record.
- Creates a developer utility menu at Settings → Technical → SOR → Events for direct record inspection.

**What this module does NOT do:**
- Manage domain-specific content: lot catalogues (auction events) and artwork lines (exhibition events) are added by bridge modules in later sprints.
- Provide a user-facing production menu — the type-agnostic events list has no natural user role. Context bridges (`sor_events_auction`, future `sor_events_exhibition`) create the relevant navigation for each event type.

**Depends on:** `base`, `mail`

---

## Key Fields and Models

### sor.event

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | Char | Yes | Event name |
| `event_type` | Selection | Yes | `exhibition` or `auction` |
| `status` | Selection | Yes | Lifecycle status; see Status Lifecycle below |
| `date_start` | Datetime | Yes | Event start date and time |
| `date_end` | Datetime | No | Event end date and time; optional at creation |
| `venue_id` | Many2one → `res.partner` | No | Physical venue; domain: `is_company=True` (soft filter) |
| `company_id` | Many2one → `res.company` | Yes | Owning company; defaults to `env.company`; read-only on the form |
| `notes` | Text | No | Internal notes |

`sor.event` inherits `mail.thread` and `mail.activity.mixin` — every event record has a chatter for log notes and activity scheduling.

---

## Status Lifecycle

Five statuses connected by four action methods. Forward transitions only — there is no reverse transition.

```
Draft → Published → Active → Closed → Archived
```

| Status | Value | Entry point |
|--------|-------|-------------|
| Draft | `draft` | Record creation (default) |
| Published | `published` | `action_publish()` |
| Active | `active` | `action_activate()` |
| Closed | `closed` | `action_close()` |
| Archived | `archived` | `action_archive_event()` |

**Note on `archived`:** The `archived` status is a manual lifecycle state — it does **not** set Odoo's `active` field to `False`. Events in the `archived` status remain visible in the event list and are not excluded from default searches.

---

## Methods

### action_publish()

Transitions the event from `draft` to `published`. Raises `UserError` if the current status is not `draft`. Posts a log note to the chatter.

### action_activate()

Transitions the event from `published` to `active`. Raises `UserError` if the current status is not `published`. Posts a log note.

### action_close()

Transitions the event from `active` to `closed`. Raises `UserError` if the current status is not `active`. Posts a log note.

### action_archive_event()

Transitions the event from `closed` to `archived`. Raises `UserError` if the current status is not `closed`. Posts a log note.

---

## Configuration

No configuration is required or available for this module. `sor_events` installs cleanly with no post-install steps.

Venue partners are selected from `res.partner` with `is_company=True` as a soft client-side filter. Individual contacts can still be assigned as venues if needed — the domain is not enforced at ORM level.

---

## Developer Menu

**Location:** Settings → Technical → SOR → Events (developer mode required)

Restricted to `base.group_no_one` — visible only when developer mode is active. Shows all `sor.event` records across all event types. Use this to inspect raw event data, check status values, or debug bridge behaviour before the contextual bridge menus are installed.

---

## Building on This Module

`sor_events` is designed to be extended by **context bridge modules** that add domain content to specific event types.

### Steps to create an event type bridge

1. **Create the bridge module** with `depends=['sor_events', '<domain_module>']` and `auto_install=True`. The bridge activates automatically when both parents are installed.

2. **Restrict the bridge's views to the correct event type.** Use a domain on any window action: `[('event_type', '=', 'auction')]`. Do not add domain restrictions to the base `sor_event_action` window action — create a new one in the bridge.

3. **Extend `sor.event`** via `_inherit = 'sor.event'` to add type-specific fields (e.g. `auction_id`, `artwork_line_ids`).

4. **Inherit the form view** via `inherit_id` to add a type-specific tab or section. Use an `invisible` expression on the inherited element if the addition should only appear when `event_type == 'auction'`.

5. **Create a user-facing menu** in the bridge pointing to a new window action filtered by event type. Do not modify the base developer utility menu — create a new menu item in the bridge's own namespace.

6. **Tests** should assert that the domain-specific field is present when the bridge is installed and absent (or ignored) when it is not.

---

## Regression Checks

Run these checks after any change to `sor_events` or any module that inherits from it.

**R1 — Events list renders without error**
Navigate to Settings → Technical → SOR → Events (developer mode). Confirm the list loads, columns are visible (Name, Type, Status, Start Date, End Date, Venue), and no JS console errors appear.

**R2 — Create a new event**
Click New. Enter a name, select Type = Exhibition, enter a Start Date. Leave End Date blank. Save. Confirm the record saves with status = Draft.

**R3 — Status transitions work**
Open the saved record. Click Publish → status bar shows "Published". Click Activate → "Active". Click Close → "Closed". Click Archive → "Archived".

**R4 — Invalid transition raises an error**
Create a new Draft event. Attempt to click Close (the button is invisible in the UI, but if triggered programmatically). Confirm the system raises an error. In the UI, confirm that only the correct action button is visible for the current status.

**R5 — Venue field optional**
Create an event without selecting a venue. Confirm no validation error occurs.

**R6 — Multi-company isolation**
With two companies active, switch to Company B and navigate to Settings → Technical → SOR → Events. Confirm only Company B's events appear.

**R7 — Chatter is visible**
Open any event form. Confirm the chatter section (message log) is visible at the bottom of the form with no raw list tables showing.

---

## Interoperability

| Module combination | Effect |
|-------------------|--------|
| `sor_events` alone | Base event record with type, schedule, lifecycle, chatter. Developer menu only. |
| `sor_events` + `sor_lotting` | No change to either module — they are independent horizontals with no bridge yet. |
| `sor_events` + `sor_events_auction` (D2) | Bridge auto-installs. Auction events gain a lot catalogue link. A user-facing Auctions menu appears. |
| `sor_events` + `sor_events_exhibition` (future) | Bridge auto-installs. Exhibition events gain artwork lines. A user-facing Exhibitions menu appears. |
