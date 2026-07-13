# Environment Readiness — Lot Reconciliation (7-Jul-2026)

The 1.44pm meeting concluded the Odoo setup "is not going to support Mark
Sold and assigning the Buyer" and that admin access needed fixing. This
report documents what the environment actually supports, verified live.

## Verified capability matrix (demo Odoo, 7-Jul)

| Capability | Via API | Via the Odoo UI | Evidence |
|---|---|---|---|
| Read lots | ✅ | ✅ | `sor.lot` ACL grants full CRUD to every internal user |
| Create lots | ✅ (seed script) | ✅ (user did it in the meeting) | ACL + meeting |
| Write Hammer Price | ✅ | ✅ | seeded + imported live |
| Write Buyer | ✅ **works** (probed + reverted) | ❌ no Buyer field on the current lot form view | live probe 7-Jul |
| Set state → Sold | ✅ **works** (probed + reverted) | ❌ the form's workflow buttons expect a Bid; most fields go readonly per-state | live probe 7-Jul |
| Estimates/reserve after cataloguing | n/a (never written by design) | readonly per-state in the form | meeting observation |

**Conclusion: the blocker is FORM-VIEW configuration, not permissions.**
- `ir.model.access` for `sor.lot`: read/write/create/unlink = 1 for `base.group_user` (every internal user — even the shared demo login can write lots).
- The admin account (uid 2) holds Role/Administrator; nothing is missing for API-driven imports.
- The UI gaps are in `sor_lotting`'s form view: no `buyer_id` widget, state-dependent readonly fields, and a Sold transition wired to the bidding workflow (`sor_bid` records) rather than a direct state write.

## What this means for the pipeline

- **Hammer Price import: enabled now** (implemented, live).
- **Buyer assignment + Sold status: fully designed and implemented behind
  feature flags**, OFF by default per the meeting decision:
  - `RECON_LOTS_ENABLE_BUYER=1` — writes `buyer_id` for confident matches
    (contact-engine match ≥ 90% AND a known Odoo partner; uncertain buyers
    are never assigned)
  - `RECON_LOTS_ENABLE_SOLD=1` — writes `state='sold'` + `auction_result='sold'`
  - Enabling is a one-line `.env` change + restart; the plan/preview already
    shows exactly what each flag would write ("deferred" column).

## Recommended follow-ups (for the SOR/Odoo side)

1. Decide whether direct `state='sold'` writes (bypassing the bid workflow)
   are acceptable for imported historical results — if yes, flip the flag;
   if no, expose a server action / method that creates the winning `sor.bid`
   and let the importer call it.
2. Add `buyer_id` to the lot form view so imported buyers are visible in Odoo.
3. Meeting follow-up on modules: an attempt was made to uninstall
   `sor_artwork` during the 1.04pm call. **Not actioned** — it is a
   dependency of several installed bridges (uninstall cascades). Clarify the
   intended module set before removing anything.
4. The demo login currently has write access to lots (module ACL design).
   Fine for a synthetic demo; production should restrict lot writes to an
   auction-manager group.

## Admin access

No missing administrator permission was found on the demo instance. If the
client applies additional admin access (as offered in the meeting), nothing
in this pipeline needs to change — the flags simply become safe to enable.
