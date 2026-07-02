# Contact Reconciliation — System Design

_deVeres Auction · Product 1 · by Cimelium · updated 2 July 2026_

## 1. Purpose

Auction houses run two disconnected systems: **Blue Cubes** (the auction/bidding
platform, whose exports are messy and per-lot) and the **canonical client
database** (the system of record, headed for **Odoo**). After every auction,
buyer data must be merged back into the canonical database without duplicating
clients or bulldozing good data with formatting noise. Doing this by hand is the
single largest time cost of auction data operations.

This product automates that merge with a human in control:

```
Blue Cube Export ─▶ Reconciliation Engine ─▶ Review ─▶ Approval ─▶ Staging ─▶ Push to Odoo
     (CSV)          normalise·match·classify   (UI)    (per record)  (SQLite)   (gated, dry-run first)
```

**Two hard guarantees:**
1. The canonical master and the uploaded file are never modified. All changes
   live in the **staging repository** until an explicit, environment-gated push.
2. Nothing reaches Odoo that a human has not approved. The staging dataset is
   the *only* push payload.

## 2. Architecture

```
recon_app.py                     FastAPI app (Product 1 — port 8003)
└── reconcile_routes.py          HTTP API + auth/RBAC + audit + session persistence
    ├── reconciliation/
    │   ├── fieldmap.py          column maps: Blue Cubes / master / sellers / lots → canonical schema
    │   ├── repository.py        CSV I/O; per-buyer aggregation; format auto-detection
    │   ├── normalize.py         pure normalisation (names/emails/phones/addresses/postcodes/countries)
    │   ├── matching.py          blocking index + weighted fuzzy scoring (stdlib difflib)
    │   ├── classify.py          NEW / RETAIN / UPDATE / POSSIBLE_DUPLICATE + field diffs + R1–R3 rules
    │   ├── engine.py            orchestration; builds ReconResult with match evidence
    │   ├── models.py            typed dataclasses; lifecycle state; serialisation
    │   ├── states.py            record lifecycle state machine (validated transitions)
    │   ├── staging.py           SQLite staging repository (pending changes) + transition log
    │   ├── export.py            CSV/JSON/XLSX/PDF exports + Odoo intermediate model
    │   └── odoo_import.py       plan_from_staging() + OdooImporter (XML-RPC, dry-run, env-gated)
    └── static/reconcile.html    review UI (vanilla JS SPA — no build step)

api.py                           PRODUCT 2 (AI Bidder Evaluation) — fully separate app, port 8006
```

The two products share **no** routes, landing pages or navigation
(2-Jul decision). The only shared code is the `pipeline/odoo_client.py`
connection helper, reused read-only by the importer.

## 3. Data flow

1. **Upload** — a Blue Cubes CSV is posted to `/reconcile/upload`. The header
   row auto-detects buyers vs sellers exports. Buyer exports are per-lot, so
   rows are aggregated to one record per buyer (first non-empty value per field,
   lots collected for context).
2. **Match** — for each incoming contact, blocking indexes (normalised email /
   phone key / name key) fetch a small candidate set from the ~13k masters;
   each candidate is scored with weighted per-field similarity.
3. **Classify** — score + field-diff report decide: NEW · RETAIN · UPDATE ·
   POSSIBLE_DUPLICATE. Formatting-only differences are `EQUIVALENT` and never
   count as changes.
4. **Review** — the UI shows every record with a live lifecycle state, the
   *why* (per-field match evidence), and the field-level diff (master vs
   incoming vs final approved).
5. **Edit (optional)** — the reviewer corrects fields (e.g. `Wickie` →
   `Wicklow`). Edits are stored on the session record and only ever applied to
   the *approved values* — the incoming snapshot is immutable.
6. **Approve** — validates the state transition, computes approved values
   (incoming ⊕ edits), and upserts the staging row. The record becomes
   `update_ready` / `import_ready`.
7. **Push** — `/reconcile/odoo-import` builds operations **from staging only**:
   `change_type='update'` → `res.partner.write` (changed fields only);
   `change_type='create'` → `res.partner.create`. Dry-run by default; live
   writes additionally require `RECON_ALLOW_ODOO_WRITE=1`.

## 4. The lifecycle state machine

```
                        ┌────────────── classification ──────────────┐
                        │                                            │
  new ─────────▶ NEW_RECORD ──────approve──────▶ IMPORT_READY ──push──▶ PUSHED_TO_ODOO
  update ──────▶ UPDATE_SUGGESTED ─approve─────▶ UPDATE_READY ──push──▶ PUSHED_TO_ODOO
  retain ──────▶ EXISTING_OK                         ▲    │un-approve
  possible_dup ▶ NEEDS_REVIEW ──approve as update/new┘    ▼
                        │                        UPDATE_SUGGESTED / NEW_RECORD
   any of the above ──edit──▶ MANUAL_EDIT ──approve──▶ *_READY
   any pre-push ──reject──▶ REJECTED ──reopen──▶ (initial state)
```

* Transitions are validated (`states.validate_transition`); an illegal move is
  an HTTP 409, never a silent no-op.
* Every transition is persisted twice: on the session record (JSON) and in the
  staging DB `transitions` table (append-only), and mirrored to the audit log.
* `PUSHED_TO_ODOO` is terminal.

## 5. Matching & confidence (explainable)

Weights (renormalised over the fields present on both records — missing data
neither helps nor hurts):

| field | weight | note |
|---|---|---|
| email | 0.34 | exact normalised match is decisive |
| phone | 0.24 | last-7-digit national key; truncated exports excluded |
| name | 0.20 | token-set ratio (order/duplication insensitive) |
| address | 0.12 | concatenated + abbreviation-normalised |
| postcode | 0.05 | Eircode formatting collapsed |
| country | 0.03 | ISO-mapped |
| company | 0.02 | often absent in buyer exports |

An exact **email or phone** match floors confidence at **0.90** ("strong ID").
The UI's *Matched because* panel shows every compared field's similarity,
weight and contribution, so a reviewer can see exactly why 98% is 98%.

## 6. Classification thresholds & manual-review rules

* `score ≥ 0.72` → same client (RETAIN if only formatting, UPDATE if
  substantive changes)
* `0.55 ≤ score < 0.72` **without** strong ID → **R1 UNCERTAIN_SCORE** → review
* `score ≥ 0.72` without strong ID **and** a conflicting significant field →
  **R2 CONFLICT_NO_ID** → review (same name, different details — may be a
  different person)
* `score ≥ 0.72`, matched on name alone, wanting to add significant new info →
  **R3 NAME_ONLY_ADDS** → review (don't attach contact details to a namesake)
* `score < 0.55` or no candidate → NEW

R2/R3 were added on 2 Jul after analysis showed a namesake with a different
address could previously reach UPDATE (and overwrite the wrong person).

Significant fields: email, phone, address1/2, town, **county, country**
(meeting: the Wickie→Wicklow case), postcode, company. Blank incoming values
are `MISSING` and never overwrite the master.

## 7. Staging repository (SQLite)

`output/staging.db` (override: `RECON_STAGING_DB`). One row per approved
record per session:

| column | meaning |
|---|---|
| session, record_index | identity (unique together) |
| change_type | `update` \| `create` — **no ambiguity at push time** |
| status | `ready` → `pushed` \| `withdrawn` |
| original_json | master snapshot (source of truth at approval time) |
| incoming_json | Blue Cubes snapshot (never edited) |
| approved_json | final values = incoming ⊕ reviewer edits |
| edited_fields / changed_fields | what the reviewer changed / what differs |
| confidence, matched_by | match metadata |
| approved_by, approved_at | who and when |
| pushed_at, odoo_partner_id | set on live push |

`transitions` table: append-only state-change log (approval history).
Exports: `/reconcile/staging/export?fmt=csv|json` — the reviewable
*pending changes* file.

## 8. Security

* **HTTP Basic** over the whole router; personal data is never public.
* **RBAC**: `RECON_USER/RECON_PASS` = admin (read-write);
  `RECON_VIEWER_USER/RECON_VIEWER_PASS` = optional read-only reviewer.
* **Audit log** (`output/reconcile_audit.log`): every upload, edit, decision,
  state change and import attempt, with actor and timestamp.
* **No destructive operations**: master CSV read-only; staging rows are
  withdrawn, not deleted; rejected records can be reopened; pushed is terminal.
* **Gated writes**: Odoo writes need `dry_run=false` *and*
  `RECON_ALLOW_ODOO_WRITE=1`; only staged (approved) rows are ever sent.

## 9. No LLM — verified

The reconciliation path is **pure Python stdlib**: `csv`, `re`, `unicodedata`,
`difflib`, `dataclasses`, `sqlite3`. No Gemma/Ollama/Anthropic/OpenAI import
exists anywhere under `reconciliation/` (grep-verified, and covered by the
developer guide). `openpyxl`/`fpdf2` are optional lazy imports for Excel/PDF
export only. Installing this product elsewhere requires Python 3.11+ and
FastAPI/uvicorn — no GPU, no model, no network beyond Odoo's XML-RPC.

## 10. Deployment topology

| product | app | port | public URL |
|---|---|---|---|
| 1 Contact Reconciliation | `recon_app:app` | 8003 | https://deveres.tail915505.ts.net |
| 2 AI Bidder Evaluation | `api:app` | 8006 | (tailnet-private until needed) |

See `docs/DEPLOYMENT.md` for the DGX specifics (Tailscale Funnel, boot
persistence, watchdog).

## 11. Future improvements

* county/country → `res.partner.state_id`/`country_id` lookup mapping (needs
  Fintan's confirmation of the Odoo field conventions)
* supervised master de-duplication pass (2,813 duplicate groups detected)
* per-session staging retention policy + scheduled purge (GDPR minimisation)
* optional embedding-based name matching for diaspora spelling variants —
  explicitly *not* an LLM dependency, and only if real data shows the need
