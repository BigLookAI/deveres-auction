# deVeres Contact Reconciliation — Odoo Integration

Technical documentation for the completed pull + push integration
(6-Jul-2026 meeting scope). Verified live on the demo environment:
https://deveres.tail915505.ts.net (app) · https://deveres.tail915505.ts.net:8443 (Odoo UI).

---

## 1. Architecture

```
Blue Cubes export (.csv)                    Odoo 19 (system of record)
        │                                   res.partner + SOR auction modules
        │ upload                                    ▲          │
        ▼                                     push  │          │ pull (XML-RPC)
┌──────────────────────────────────────────────────┴──────────▼─────────┐
│ Contact Reconciliation (FastAPI, recon_app.py :8003)                   │
│                                                                        │
│  MasterRepository ◄── odoo_master.fetch_partners (batched search_read) │
│      │  in-memory blocking index (email / phone / name)                │
│      ▼                                                                 │
│  ReconciliationEngine → classify → ReconResult (session, persisted)    │
│      ▼ approve                                                         │
│  StagingRepository (SQLite output/staging.db — THE ONLY push payload)  │
│      ▼ push                                                            │
│  OdooImporter (plan → resolve → write → READ-BACK VERIFY → audit)      │
└────────────────────────────────────────────────────────────────────────┘
```

- **Environment**: Odoo runs in Docker (`deveres-odoo-test`, image `odoo:19`,
  PostgreSQL 15) with the SOR addons mounted at `/mnt/extra-addons`, configured
  from the Assembly profile `odoo-test/assemblies/deveres_demo.yaml`
  (9 explicit SOR modules + 12 auto-installed bridges — installed and verified
  by `scripts/install_assembly.py`, report in `output/module-install-report.md`).
- **Auth between the apps**: `ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD`
  env vars (on production: an Odoo **API key** in place of the password —
  generate via odoo shell `res.users.apikeys._generate`, scope `rpc`; the key
  lives only in the server-side `.env`, never in the repo).

## 2. When does the engine pull from Odoo? (investigation answer)

The 6-Jul meeting asked which of five behaviours exists. The answer:

| Option | Behaviour | Present? |
|---|---|---|
| A | once when the application starts | **≈ YES** — lazily, at the first request that needs the master, once per process |
| B | every browser refresh | no — the browser reuses the cached in-memory master |
| C | every login | no — HTTP Basic has no login event |
| D | every reconciliation session/upload | no — an upload re-uses the cached master |
| E | every API request | no — deliberately (a 13k-partner fetch per request would be seconds-slow) |

Precisely: `reconcile_routes._get_engine()` builds `MasterRepository.from_odoo()`
on first use and caches it in module state. It refreshed only on process
restart — **until the 6-Jul work added two explicit refresh paths**:

1. `POST /reconcile/master/reload` (existed since 3-Jul) — re-fetches the
   master, but does **not** touch an open session's already-reconciled rows.
2. `POST /reconcile/refresh` (**new, the UI's ⟳ Refresh contacts button**) —
   re-fetches the master **and re-reconciles the open session against it**,
   preserving reviewer decisions.

## 3. Refresh architecture (⟳ Refresh contacts)

```
UI ⟳ button ──► POST /reconcile/refresh
                    │ 1. MasterRepository.from_odoo()     (fresh partner list)
                    │ 2. rebuild ReconciliationEngine + blocking index
                    │ 3. re-run matching+classification for every session record
                    │    (rebuilt from each record's stored incoming snapshot)
                    │ 4. decision preservation:
                    │      record untouched  → adopt fresh classification/state
                    │      record acted upon → keep state, edits, approval
                    │        history, approved/staged values; only the master
                    │        snapshot + field diffs update
                    │ 5. persist session · update sync telemetry · audit
                    ▼
        {master_records, decisions_preserved, reclassified, refreshed_at}
```

Example (verified live, TC4): Karen Namesake's address is edited directly in
Odoo → ⟳ Refresh → her reconciliation record immediately shows the new
address on the master side; her pushed/staged status and history are intact.

Staged changes and pushed records are **never** silently altered by a refresh
(`decisions_preserved` counts them). Untouched records may legitimately
reclassify (e.g. an update suggestion disappears because Odoo now already
holds the incoming values).

## 4. Push pipeline (Stage → Push → Verify)

```
Approve (UI/API)                                  [nothing touches Odoo here]
   └─► StagingRepository row: original + incoming + approved values,
       changed/edited fields, approver, timestamps        status=ready
Push  (UI 🚀 button → POST /reconcile/odoo-import)
   1. plan_from_staging(ready rows)   — validation: bad rows become explicit
      skips (no name / no ref / no buyer number)
   2. dry_run=true (default)          — plan only, shown to the user first
   3. dry_run=false (confirmed)       — requires env RECON_ALLOW_ODOO_WRITE=1
        resolve partner: exact odoo_id → synthetic ODOO-<id> ref → ref → email
        create → res.partner.create   (idempotent: existing ref ⇒ write)
        write  → res.partner.write    (only approved changed fields)
        county/country names → state_id/country_id lookups at execute time
   4. VERIFY — the partner is READ BACK from Odoo; every written field is
      compared (many2one by id). op.verified = true/false + mismatch detail.
   5. bookkeeping — per record:
        staging row → status=pushed (+partner_id) · ReconResult → PUSHED_TO_ODOO
        audit "odoo_push_record": contact index+ref, Odoo id, timestamp, user,
        fields updated, OLD values, NEW values, API outcome, verified flag
      errored ops stay status=ready → the next push retries exactly those.
   6. sync telemetry — last_push_at/by/summary + failed count → status bar.
```

### Error handling & retries
- One failing record never aborts the batch (per-op isolation; op=`error`).
- Errored/VALIDATION rows remain in staging (`ready`) — re-pushing retries
  them; creates are idempotent by `ref` so a retry can't duplicate.
- Live writes are double-gated: `dry_run=false` in the request AND
  `RECON_ALLOW_ODOO_WRITE=1` on the server (403 otherwise).
- Master fetch failure: explicit `RECON_MASTER_SOURCE=odoo` fails fast (502);
  `auto` falls back to the CSV snapshot loudly (health flag + audit + UI toast).

## 5. API reference (all under HTTP Basic auth)

### Pull / session
| Endpoint | Purpose |
|---|---|
| `GET /reconcile/health` | status, master source/size/loaded-at, session, staging counts, last refresh/push |
| `GET /reconcile/sync-status` | status-bar payload: API config, master, last refresh, last push, pending/failed push |
| `POST /reconcile/refresh` | ⟳ Refresh contacts (master re-pull + session re-reconcile, decisions preserved) |
| `POST /reconcile/master/reload` | master re-pull only |
| `POST /reconcile/upload` | process a Blue Cubes CSV against the current master |
| `GET /reconcile/results` · `/results/{i}` · `/progress` | rows, detail, live counters |

### Review / staging
| Endpoint | Purpose |
|---|---|
| `POST /reconcile/records/{i}/edit` · `approve` · `reject` · `reopen` · `keep-existing` | record lifecycle (validated state machine) |
| `POST /reconcile/approve-bulk` · `/decide` | bulk decisions |
| `GET /reconcile/staging` · `/staging/export` | the pending-changes payload |

### Push
| Endpoint | Purpose |
|---|---|
| `POST /reconcile/odoo-import {dry_run:true}` | plan + resolve, NO writes (default) |
| `POST /reconcile/odoo-import {dry_run:false}` | live push + read-back verification (needs `RECON_ALLOW_ODOO_WRITE=1`) |

Response (live): `summary {create, write, skip, error, verified, verify_failed,
id_checks_required}` + per-operation `{op, ref, name, partner_id, values,
verified, verify_mismatch, reason}` + `correlation_id` (ties the request to
log lines and audit entries).

## 6. Field mapping

See `docs/FIELD-MAPPING.md` (Blue Cubes → canonical → res.partner, verified
per-field with live write round-trips on 2026-07-06).

## 7. Odoo environment set-up (Phase 1 artefacts)

| Step | Tool | Report |
|---|---|---|
| Install Assembly modules | `scripts/install_assembly.py odoo-test/assemblies/deveres_demo.yaml` | `output/module-install-report.md` |
| Contact Type = Contact migration + hierarchy validation | `scripts/migrate_contact_types.py` | `output/contact-migration-report.md` |
| Field editability checklist (UI/ORM/API, admin + demo user) | `scripts/verify_contact_fields.py --fix-perms` | `output/field-editability-report.md` |

Root causes fixed on 6-Jul: the demo Odoo had **no SOR modules** (Assembly
never applied) and the shared demo login had Odoo 19's read-only contact
access (`base.group_user`) — Contact Creation (`base.group_partner_manager`)
is now granted, and every listed field verified editable as that user.
