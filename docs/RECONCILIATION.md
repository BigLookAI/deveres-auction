# Contact Reconciliation Engine

The preprocessing layer that reconciles an uploaded **Blue Cubes buyer export**
against the **immutable canonical client database** before auction data enters
the System of Record / Odoo. This is ~60% of the auction-import workflow.

```
System of Record (Odoo)            ← future import target
        ▲
        │ approved changes (ADD / UPDATE / IGNORE)
Reconciliation Engine  ── Review UI ── Reviewer decisions
        ▲
        │ compares against
Master Client DB (All Clients.csv, 13,682) ── baked in, source of truth, never
        ▲                                        overwritten by trivial changes
        │ user uploads
Blue Cubes export (Design-April 2026.csv) ── the ONLY file the user uploads
```

## Folder structure

```
reconciliation/            # engine package (framework-agnostic, no I/O in logic)
  normalize.py             # name/email/phone/address/postcode/country normalisers
  fieldmap.py              # column → canonical-field maps (master, incoming, lots)
  models.py                # dataclasses: Classification, FieldDiff, ReconResult, Summary
  matching.py              # blocking index + weighted fuzzy scoring (stdlib only)
  classify.py              # NEW/RETAIN/UPDATE/POSSIBLE_DUPLICATE + field-level diffs
  repository.py            # CSV loaders (master / incoming / lots), master index
  engine.py                # ReconciliationEngine — orchestration + summary
  export.py                # CSV / JSON / Odoo-ready intermediate model
reconcile_routes.py        # FastAPI APIRouter (upload, results, decide, export, lots)
static/reconcile.html      # polished dark review UI (upload→dashboard→table→diff drawer)
tests/test_reconciliation.py
```

## Normalization rules (what counts as "the same")

| Field | Normalisation |
|---|---|
| **Name** | lowercase · strip accents (é→e) · drop punctuation · drop titles/suffixes (Mr, Mrs, Dr, Jr) · collapse whitespace; `name_key` = sorted tokens (order-independent) |
| **Email** | lowercase · trim (exact-normalised equality only — dots/plus-tags preserved) |
| **Phone** | strip spaces/brackets/dashes · `00353`→`+353` · `087…`→`+35387…`; compare on the **national significant number** (country code stripped, last 7 digits). Numbers with <7 national digits (the export's **truncated** phones, e.g. `35387`) are treated as unusable — never match, never flag a change |
| **Address** | lowercase · strip accents/punctuation · collapse whitespace · map street words to one token (Street=St, Road=Rd, Apartment=Apt, Avenue=Ave, …) |
| **Postcode** | uppercase · remove spaces/punctuation (`D18 XY53` = `d18xy53`) |
| **Country** | ISO-3166 map (Ireland→IE, UK→GB, …) |

**Data-quality awareness:** the De Veres master frequently stores an **Eircode in
the `townCity` field** with `postalCode` blank. The engine detects this — the
misfiled postcode counts as *equivalent* (already present), and the real town is
surfaced as *new information* rather than a spurious "changed" value.

## Matching algorithm

1. **Blocking** — the master is indexed once by normalised email, phone-key, and
   name-key. For each incoming buyer we gather only the candidates sharing one of
   those keys (O(1) lookups) instead of scanning all 13k+ rows. Scales to 50k+.
2. **Weighted, field-aware scoring** over candidates. Only fields present on
   *both* records contribute; weights are renormalised over present fields so
   missing data neither helps nor hurts:

   | Field | Weight | Rationale |
   |---|---|---|
   | Email | 0.34 | highest confidence identifier |
   | Phone | 0.24 | high |
   | Name | 0.20 | medium |
   | Address | 0.12 | medium |
   | Postcode | 0.05 | low |
   | Country | 0.03 | low |
   | Company | 0.02 | lowest (often absent in buyer export) |

   Text similarity uses stdlib `difflib` plus an order-insensitive **token-set
   ratio** for names/addresses (no external dependencies). An **exact email or
   phone** match floors the score at 0.90 (decisive identifier).

## Confidence scoring & classification

`confidence` = weighted similarity of the best candidate (0–1). Then:

| Confidence / signal | Class | Recommendation | Status |
|---|---|---|---|
| no candidate or < 0.55 | **NEW** | ADD | 🟢 New client |
| ≥ 0.72 (or exact email/phone), only cosmetic diffs | **RETAIN** | KEEP EXISTING | 🔵 Existing — no action |
| ≥ 0.72 (or exact email/phone), ≥1 substantive change | **UPDATE** | UPDATE RECORD | 🟠 Update suggested |
| 0.55–0.72 and no strong identifier | **POSSIBLE DUPLICATE** | MANUAL REVIEW | 🟣 Manual review |

A change is **substantive** only if a significant field (email, phone, address,
town, postcode, company) is genuinely different (`CHANGED`) or newly provided
(`NEW_INFO`). Formatting-only differences are `EQUIVALENT` and never update the
canonical record. Blank incoming values are `MISSING` and never overwrite.

## Difference detection (field-by-field)

Each field yields one of: `UNCHANGED` · `EQUIVALENT` (formatting only) ·
`CHANGED` (both present, meaningfully different) · `NEW_INFO` (master blank) ·
`MISSING` (incoming blank). The UI renders green = new, red = changed, grey =
unchanged/equivalent.

## API

`GET /reconcile` UI · `GET /reconcile/health` · `POST /reconcile/upload` ·
`GET /reconcile/results?status&q&sort&order&page&page_size` ·
`GET /reconcile/results/{index}` · `POST /reconcile/decide {action,indices}` ·
`GET /reconcile/export?fmt=csv|json` · `GET /reconcile/odoo-preview` ·
`GET /reconcile/lots` (Hammer forced 0).

## Lots import

`load_lots()` parses a Lot List export and **forces `hammer = 0`** on every lot
(the original value is retained as `hammer_export` for audit), per the meeting rule.

## Odoo integration (future)

`export.odoo_intermediate()` emits a clean per-contact model —
`{action, canonical_record, canonical_ref, incoming_record, difference_report, lots}` —
so a future Odoo importer needs no reconciliation logic: it applies `ADD`,
`UPDATE` (only the significant fields), or `IGNORE`, and imports lots with
hammer = 0. Contacts map to `res.partner`; buyers/vendors via existing SOR roles.

## Performance

Blocking + in-memory indexes reconcile 83 buyers against 13,682 masters in ~14 ms;
the design scales to 50k+ masters (index build is linear, per-contact lookup is
O(1) on candidate blocks). The UI paginates server-side. For very large *result*
sets, table virtualisation and chunked/streamed upload are the next step (see
"Remaining work").

## Developer setup

```bash
cd deveres-auction
pip install -r requirements.txt          # + python-multipart (file upload)
pytest tests/test_reconciliation.py -q    # 17 tests
# run the app (serves /reconcile):
bash start.sh                             # uvicorn api:app on :8003
# CLI sanity check:
python -c "from reconciliation import *; m=MasterRepository.from_csv('All Clients.csv'); \
print(ReconciliationEngine(m).run(load_incoming('Design-April 2026.csv'))[1].to_dict())"
```

## Assumptions

- `All Clients.csv` is canonical and immutable within the app; only the Blue
  Cubes export is uploaded.
- Incoming rows are per-lot; buyers are deduped by **Buyer Number** (first
  non-empty value per field wins; lots aggregated).
- Blue Cubes phone numbers are frequently truncated → treated as unusable.
- Default country for bare national phone numbers is Ireland (+353).
- Payments context (debit card / bank transfer / cheque / bank draft; ID
  required over €10,000) is recorded for the future Odoo import step, not the
  reconciliation logic.

## Pre-Odoo checklist — status

- ✅ Odoo importer (`reconciliation/odoo_import.py` + `POST /reconcile/odoo-import`):
  maps the intermediate model to `res.partner`; UPDATE writes only significant
  fields; idempotent (resolves by `ref`, falls back to email); dry-run default;
  live writes require `RECON_ALLOW_ODOO_WRITE=1`; flags buyers over €10,000 for
  ID verification (payments: debit card / bank transfer / cheque / bank draft).
- ✅ Auth (HTTP Basic on every /reconcile route; env `RECON_USER`/`RECON_PASS`)
  + append-only audit log (`output/reconcile_audit.log`).
- ✅ Durable + named sessions (one per upload; list/activate endpoints + UI picker).
- ✅ Excel + PDF exports.
- ✅ Master data-quality report (`GET /reconcile/master-quality`): intra-master
  duplicate groups + misfiled-Eircode count.
- ✅ 50k-scale guarded by a benchmark test (index build <8s, 500-contact run <4s;
  the UI only ever renders one server-side page, so no client-side lag).
- ✅ Manual-review tooling: per-row decision buttons in the diff drawer.

Still open (post-Odoo niceties): field-level merge editor; learned confidence
thresholds; background worker for multi-hundred-MB uploads.
```
