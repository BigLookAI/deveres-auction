# Phase 4 · Priority 1 — "Missing contacts" root cause

**Verdict: no contact was ever deleted, archived, reassigned or lost by sync.
The records were present and correct throughout; three independent
*visibility* mechanisms made them look missing. Two were real product defects
(both now fixed); one was Odoo view state cleared during the meeting itself.**

## Evidence base

- App audit log (`output/reconcile_audit.log`, append-only — survives resets)
- Odoo chatter (`mail_message`) + database state (`res_partner`, `ir_filters`)
- Odoo server logs (`docker logs deveres-odoo-test`)
- SOR view definitions (`ir_act_window` domains)

## Database state (checked 7-Jul, after the morning session)

| Check | Result |
|---|---|
| Active partners | **217** (216 seeded + BC-9001 re-created 10:03 UTC, verified ✓) |
| Inactive partners | 3 — Odoo's own system template users (never user-visible; not archived by anyone) |
| Person partners missing the SOR Contact Type | **0** |
| Saved/default user filters (`ir_filters`) | none |
| `unlink` calls in server logs during the meeting window | none |

## The three mechanisms

### 1. The SOR Contacts views filter on *Contact Types*, not on partner existence
`action-211` ("Contacts", from `sor_contact_roles`) has domain
`[('contact_types.code','=','contact')]` — likewise Bidders / Consignors /
Donors / Creators. A partner without that tag exists but is invisible in
every SOR contact view. The demo partners were seeded **before** the SOR
modules were installed, so all 216 lacked the tag until the 6-Jul migration
fix (0 → 216 tagged).

### 2. Push-created contacts lacked the tag until 7-Jul
A client created by the reconciliation push (e.g. `BC-9001 Testfirst
Newclient`) got no Contact Type either — visible in the plain Contacts app,
invisible in the SOR views: exactly "the engine says it exists but I can't
see it". **Fixed 7-Jul**: the importer now tags every created partner with
the SOR Contact Type "Contact" (best-effort, skipped on non-SOR databases).
Proof: partner 231, created 10:03 UTC via push, carries the tag; the
"missing tag" query returns zero rows.

### 3. The in-meeting empty list was leftover view state
During the meeting the Contacts list appeared empty, and restoring it was
witnessed live: *"just clear the filters … we now see 216 contacts again …
it looked like it was empty and then when you reset filter, it appeared."*
Odoo preserves search facets in the session/breadcrumb when navigating; a
stale facet (search term or type filter) hid everything. The database shows
no deletion, no archival, no saved default filter — presentation state only.

### Why the reconciliation engine "still believed they exist"
The engine reads partners over the API (`search_read` on all active
partners) — it never applies UI view domains. It was **correct** the whole
time; the inconsistency was between two *views* of the same data, not
between the data and the engine.

## Fixes shipped (underlying, no data insertion)

1. Importer auto-tags created partners with the SOR Contact Type (7-Jul).
2. Migration script tags/repairs existing partners, idempotently (6-Jul).
3. This document + the activity timeline (Phase 4) make create/push/verify
   events visible in-app, so a future "where did it go?" is answerable from
   the UI in seconds.

## Upstream recommendation (out of this repo's scope)
The SOR views could add a "no contact type" fallback filter or an
`auto-tag on create` default in `sor_contact_roles` itself, so records
created by *any* integration are never invisible. Raise with the SOR team.

## Related observation from the same investigation
Odoo 19 logs every app call with: *"/xmlrpc … deprecated in Odoo 19 and
scheduled for removal in Odoo 22"*. Migration to the JSON-2 API is queued in
the Phase 4 TODO (agreed in the meeting: not worth a refactor mid-delivery).
