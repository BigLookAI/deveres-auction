# Contact Reconciliation — Developer Guide

_Everything an engineer needs to maintain this product without reverse
engineering it. Companion to `docs/SYSTEM-DESIGN.md` (the why) — this is the
how. Updated 2 July 2026._

## 1. Quick start

```bash
./setup.sh                                  # venv + deps (fastapi, uvicorn, openpyxl, fpdf2)
./run.sh                                    # Product 1 on :8003 (reconciliation)
./run-bidder.sh                             # Product 2 on :8006 (bidder eval — separate)
python3 -m pytest tests -q                  # 131 tests
```

Open http://localhost:8003 → landing → `/reconcile` (HTTP Basic:
`RECON_USER`/`RECON_PASS`, default `admin@deveres.ie` / `Admin2026!`).

## 2. Environment variables

| var | default | purpose |
|---|---|---|
| `RECON_USER` / `RECON_PASS` | `admin@deveres.ie` / `Admin2026!` | admin (read-write) login |
| `RECON_VIEWER_USER` / `RECON_VIEWER_PASS` | unset | optional read-only login |
| `RECON_MASTER_CSV` | `All Clients.csv` | canonical master path |
| `RECON_LOTS_CSV` | `Lot List Export …csv` | lot list for `/reconcile/lots` |
| `RECON_STAGING_DB` | `output/staging.db` | staging SQLite path |
| `ODOO_URL` / `ODOO_DB` / `ODOO_USERNAME` / `ODOO_PASSWORD` | unset | Odoo XML-RPC target |
| `RECON_ALLOW_ODOO_WRITE` | unset | **must be `1` for any live Odoo write** |

## 3. Module walkthrough

### `reconciliation/fieldmap.py`
Column-name maps from each source format to the canonical contact schema
(`client_ref, first_name, …, postcode`). A new Blue Cubes version = a new map
here, nothing else changes. `DIFF_FIELDS` controls the diff viewer's rows.

### `reconciliation/repository.py`
All file I/O. `MasterRepository.from_csv` loads the master once (read-only) and
builds the blocking index. `load_incoming` collapses the per-lot buyer export
to one record per buyer. `detect_format`/`load_upload` sniff the header row —
buyers (`Buyer Number`+`Winning Bid`) vs sellers (`Seller Ref`+…). `load_lots`
forces Hammer=0 (1-Jul meeting rule).

### `reconciliation/normalize.py` — how formatting noise is removed
Pure, total, deterministic functions (never raise):
* `normalize_name` — lowercase, accent-fold (é→e), strip punctuation and
  titles (Mr/Dr/…); `name_key` also sorts tokens ("Smith John"=="John Smith").
* `normalize_email` — lowercase + whitespace strip. Gmail dots/plus-tags are
  deliberately **not** collapsed (could merge distinct people).
* `normalize_phone` — to E.164-ish: `087 123…` ≡ `+353 87 123…` ≡ `00353…`.
  `phone_key` = last 7 digits of the national number; returns `''` for
  truncated exports (`'35387'`) so garbage can't match or diff.
* `normalize_address` — accent/punctuation/case folding + synonym table
  (Street=St, Road=Rd, Apartment=Apt=Flat, …).
* `normalize_postcode` — uppercase, strip non-alphanumerics ("D18 XY53"≡"d18xy53").
  `is_eircode` detects Eircodes misfiled in the master's *town* column.
* `normalize_country` — free text → ISO-3166 alpha-2 (Ireland/Éire/ROI → IE).

There is no LLM anywhere in this pipeline — every equivalence above is an
explicit, testable rule. That is a feature: deterministic, auditable,
installable anywhere with plain Python.

### `reconciliation/matching.py` — how weighted matching works
1. **Blocking**: `MasterIndex` holds three dicts — normalised email, phone key,
   sorted-name key → master row ids. A lookup returns a handful of candidates
   instead of scanning 13k rows (O(1) per key; ~16k contacts reconcile in
   seconds; benchmarked to 50k masters).
2. **Scoring**: `score_pair` computes per-field similarities (`difflib.
   SequenceMatcher`; token-set ratio for names/addresses), multiplies by the
   `WEIGHTS` table, and renormalises over the fields present on both sides.
3. **Strong ID**: exact email/phone ⇒ `matched_by` entry and a 0.90 confidence
   floor.
`Candidate.field_sims` carries the raw per-field numbers into
`ReconResult.match_evidence` (the UI's "Matched because" panel).

### `reconciliation/classify.py` — decision rules
Thresholds: `MATCH_THRESHOLD=0.72`, `REVIEW_FLOOR=0.55`. `diff_fields` builds
the field-level report with statuses `UNCHANGED / EQUIVALENT / CHANGED /
NEW_INFO / MISSING`; only significant CHANGED/NEW_INFO drive an UPDATE.
Manual-review rules **R1/R2/R3** are documented at the top of the file and in
SYSTEM-DESIGN §6; each has a dedicated test with example records
(`tests/test_classify_rules.py::TestManualReviewRules`).
Data-quality specials: postcode misfiled in town; Eircode-in-town treated as
"no town value"; phone truncation never a change.

### `reconciliation/states.py` — the state machine
`RecordState` enum + `ALLOWED_TRANSITIONS` dict + `validate_transition` (raises
`TransitionError`). `initial_state(classification)` maps NEW→NEW_RECORD,
UPDATE→UPDATE_SUGGESTED, RETAIN→EXISTING_OK, POSSIBLE_DUPLICATE→NEEDS_REVIEW.
If you add a state: add it to the enum, the transition map, `STATE_LABELS`,
and a test in `tests/test_states_staging.py`.

### `reconciliation/staging.py` — the pending-changes store
`StagingRepository` (SQLite, WAL). `stage()` upserts on `(session,
record_index)` — re-approval overwrites, never duplicates. `withdraw()` /
`mark_pushed()` move status; `export_csv()/export_json()` produce the
reviewable file; `log_transition()/history()` are the approval history.

### `reconciliation/odoo_import.py` — push preparation
`plan_from_staging(entries)` → `ImportOp[]`:
* `create` ops carry the full approved record, `ref=BC-<buyer_number>`;
* `write` ops carry **only** changed+edited fields mapped via
  `PARTNER_FIELD_MAP` (email/phone/mobile/street/street2/city/zip);
* county/country changes have no direct text field in `res.partner` — they are
  surfaced in the op reason (never silently dropped) until the
  state_id/country_id mapping is confirmed.
`OdooImporter.execute(ops, dry_run)` resolves partners by `ref` then email
(idempotent: a re-run of `create` becomes `write`), and refuses live writes
without `RECON_ALLOW_ODOO_WRITE=1`. Buyers with >€10,000 winning bids get an
ID-verification note.

### `reconcile_routes.py` — HTTP API
All routes require auth; write routes require the admin role. The
session (results + states + edits + history) persists to
`output/reconcile_session.json` on every mutation and restores on restart.
Endpoint map is in the module docstring. Key invariants:
* every mutation goes through `_transition()` (validate → apply → persist →
  audit) and `_save_session()`;
* `_approved_values()` merges incoming ⊕ edits — the only place approved
  values are computed;
* `/reconcile/odoo-import` reads **staging only**.

### `static/reconcile.html` — the UI
No build step: vanilla JS + fetch. State badges, filter chips (classification
+ workflow state), match-evidence panel, 4-column diff (master / incoming /
final approved), edit form with dirty-field highlighting, approval history
timeline, pending-changes header bar, bulk actions, Odoo dry-run button.

## 4. Testing

```bash
python3 -m pytest tests -q                    # all 131
python3 -m pytest tests/test_workflow_api.py  # HTTP workflow only
```
* `tests/fixtures/` — synthetic master + Blue Cubes export (fake data only)
  covering every classification pathway and every meeting edge case.
* `test_states_staging.py` — state machine legality + staging repo.
* `test_classify_rules.py` — R1/R2/R3 with example records, evidence maths,
  formatting-noise equivalences, invalid inputs.
* `test_workflow_api.py` — end-to-end HTTP: edit→approve→staging→plan,
  reject/reopen rollback, RBAC, persistence across restart, audit log.
* `test_reconciliation.py` — original engine suite (normalisation, matching,
  export, importer plan/execute with stubbed client).

## 5. Troubleshooting

| symptom | cause / fix |
|---|---|
| 401 on every request | missing/wrong Basic auth — check `RECON_USER/PASS` env on the server |
| 403 on approve/edit | you're on the viewer account — use the admin login |
| 409 on approve | illegal state transition — the record is already staged/pushed; the body says what's allowed |
| "Staging is empty" on import | nothing approved yet — approve records first (staging is the only payload) |
| Excel/PDF export 501 | `pip install openpyxl fpdf2` in the venv |
| Session gone after restart | check `output/reconcile_session.json` exists and is writable |
| Live push refused | set `RECON_ALLOW_ODOO_WRITE=1` *and* pass `dry_run:false` — both are required |
