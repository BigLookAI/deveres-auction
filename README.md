# deVeres Auction — AI Operations (by Cimelium)

This repository contains **two completely independent products**
(2-Jul-2026 decision — separate frontends, separate landing pages, no shared
navigation, no coupled code):

| # | Product | App | Port | Status |
|---|---|---|---|---|
| 1 | **Contact Reconciliation** — the deliverable for the upcoming auction | `recon_app:app` | 8003 | **production-ready** |
| 2 | AI Bidder Evaluation — parked until after the auction | `api:app` | 8006 | frozen (do not modify) |

---

## Product 1 — Contact Reconciliation

Cleans incoming auction data before it touches the system of record:

```
Blue Cube Export → Reconciliation Engine → Review → Approval → Staging → Push to Odoo
```

* Matches every uploaded contact against the canonical client database
  (~13.7k records) with weighted, **explainable** fuzzy matching — the UI
  shows *why* each match scored what it scored (per-field similarity, weight
  and contribution).
* Formatting noise (case, spacing, dialing codes, address abbreviations,
  Eircode formats) is never treated as a change.
* Full review workflow with a **validated state machine**:
  `Update suggested → (Edit) → Update ready → Pushed to Odoo`, plus
  new-client, manual-review, reject and reopen paths. Every transition
  persists and is audited; an illegal move is an HTTP 409, never a silent
  no-op.
* **Manual edit before approval** (e.g. fixing `Wickie` → `Wicklow`) — edits
  live only in the approved/staging values; the uploaded file and the master
  are immutable.
* **Staging layer (SQLite)** = the pending-changes dataset. Approval writes
  here, never to Odoo. The staging file is the *only* Odoo push payload and
  distinguishes `UPDATE` vs `CREATE` unambiguously.
* Odoo push is **dry-run by default**; live writes are double-gated
  (`RECON_ALLOW_ODOO_WRITE=1` **and** explicit `dry_run:false`).
* Pure Python — **no LLM anywhere in the reconciliation path** (verified;
  see the developer guide). No GPU, no model, no paid APIs.

### Quick start

```bash
./setup.sh                     # one-time: venv + deps
./run.sh                       # http://localhost:8003 → open /reconcile
python3 -m pytest tests -q     # 258 tests
```

Login (HTTP Basic, override via `RECON_USER`/`RECON_PASS`):
`admin@deveres.ie` / `Admin2026!` · optional read-only account via
`RECON_VIEWER_USER`/`RECON_VIEWER_PASS`.

**Demo reset** (`↺ Reset demo data`, admin-only): reverts the demo dataset to
its original unreconciled state — seeded contacts restored, push-created
clients removed, lots back to pre-sale — and archives the working session to
`output/demo-archive-<ts>/`. Double-gated: the server must set
`RECON_ENABLE_DEMO_RESET=1` **and** `ODOO_DB` must be the demo database, so
the route cannot exist against client data.

Live demo: **https://deveres.tail915505.ts.net**

### Documentation

| doc | contents |
|---|---|
| [`docs/SYSTEM-DESIGN.md`](docs/SYSTEM-DESIGN.md) | architecture, data flow, state machine, matching & thresholds, staging schema, security |
| [`docs/DEVELOPER-GUIDE.md`](docs/DEVELOPER-GUIDE.md) | module-by-module walkthrough, env vars, testing, troubleshooting |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | install, DGX production setup, Odoo connection, backup/rollback |
| [`docs/RECONCILIATION.md`](docs/RECONCILIATION.md) | original engine notes (superseded where they conflict with the above) |

---

## Product 2 — AI Bidder Evaluation (parked)

Scores auction bidders against upcoming lots across 6 deterministic dimensions
and recommends who to invite (Approve ≥ 0.70 · Review 0.40–0.69 · Reject
< 0.40), with Markdown reports and drafted outreach emails. Deliberately
untouched while the reconciliation tool ships; it will become a fully separate
application afterwards.

```bash
./run-bidder.sh     # http://localhost:8006
```

To stop either product: `./stop.sh`. Docker: `docker compose up` (see
`docs/DEPLOYMENT.md`).

---

Cimelium (BigLook) · client: De Veres Art Auctions · The CSVs in this repo are
client personal data — handle per the GDPR notes in `docs/`.
