# Contact Reconciliation — Deployment Guide

_Updated 2 July 2026. Current production host: the on-prem DGX Spark._

## 1. What gets deployed

Two **independent** products from this repo (2-Jul separation decision):

| product | app module | port | exposure |
|---|---|---|---|
| Contact Reconciliation | `recon_app:app` | 8003 | public via Tailscale Funnel — https://deveres.tail915505.ts.net |
| AI Bidder Evaluation | `api:app` | 8006 | tailnet-only (own funnel node later if required) |

They share no pages and no navigation. Taking one down does not affect the other.

## 2. Requirements

* Python 3.11+ (no GPU, no LLM, no model downloads — the engine is pure Python)
* `pip install fastapi uvicorn python-multipart openpyxl fpdf2`
  (`openpyxl`/`fpdf2` optional — only Excel/PDF exports need them)
* The canonical `All Clients.csv` beside the app (or `RECON_MASTER_CSV=path`)
* Writable `output/` directory (session JSON, staging.db, audit log)

## 3. Fresh install (any Linux/macOS box)

```bash
git clone git@github-biglook:BigLookAI/deveres-auction.git
cd deveres-auction
./setup.sh                      # creates .venv and installs deps
cp .env.example .env 2>/dev/null || true
# set at least RECON_USER/RECON_PASS in .env for a non-default login
./run.sh                        # reconciliation on :8003
./run-bidder.sh                 # (optional) bidder eval on :8006
```

Health checks: `GET :8003/health` (no auth) → `{"status":"ok","product":"contact-reconciliation"}`;
`GET :8003/reconcile/health` (auth) → master size + session + staging counts.

## 4. DGX production specifics

* Code lives at `~/Gemma4/deveres-auction`, venv `.venv`, started by
  `~/scripts/boot-all-demos.sh` (@reboot cron) and supervised by
  `~/scripts/watch-demos.sh` (per-minute cron; restarts dead apps).
  **Update both scripts' start command** to `uvicorn recon_app:app --port 8003`
  and add the bidder app on 8006.
* Public URL via per-app Tailscale Funnel node (`tailscaled` userspace,
  `--statedir`, hostname `deveres`): funnel target must be `localhost:8003`
  (not `127.0.0.1`). Reset with `tailscale funnel reset` on that node.
* tmux default shell is dash — scripts must use POSIX `.` not `source`.
* Deploy update: `git pull` (or rsync), then
  `pkill -f 'uvicorn (api|recon_app):app' && . ~/scripts/boot-all-demos.sh`
  (the watchdog also brings them back inside a minute).
* Run the tests on the box after every deploy:
  `.venv/bin/python -m pytest tests -q` → must be 131 passed.

## 5. Odoo connection (when ready to push)

1. Set on the server (never commit):
   `ODOO_URL=…  ODOO_DB=…  ODOO_USERNAME=…  ODOO_PASSWORD=…`
2. Verify the plan: UI → *Odoo dry-run* (or
   `POST /reconcile/odoo-import {"dry_run": true}`) — counts of create/write/
   skip and any >€10k ID-check flags. **No writes happen.**
3. Live push (deliberate, two keys):
   `RECON_ALLOW_ODOO_WRITE=1` in the environment **and**
   `POST /reconcile/odoo-import {"dry_run": false}`.
4. After a live push: staged rows become `pushed` (with `odoo_partner_id`),
   records move to `PUSHED_TO_ODOO` (terminal), and the audit log records the
   summary. Re-pushing is idempotent (partners resolve by `ref`, then email).

## 6. Backup & rollback

* **State to back up**: `output/staging.db`, `output/reconcile_session.json`,
  `output/sessions/`, `output/reconcile_audit.log`. All are small files —
  nightly copy is enough.
* **Rollback of a mistaken approval**: UI *Un-approve* (staging row withdrawn,
  state returns) — no data loss, the history keeps both moves.
* **Rollback of a bad deploy**: `git checkout <previous tag/commit>` and
  restart; the session/staging files are forward/backward compatible (missing
  lifecycle fields default from the classification).
* **After a live Odoo push**: reversal is an Odoo-side operation (the audit
  log + staging rows record exactly what was written, per partner id).

## 7. Clean Odoo environment rebuild (production launch, 13-Jul-2026)

The Assembly YAML is the source of truth for the Odoo side. Never install
modules by hand — rebuild:

```bash
# 1. addons mount = EXACTLY the assembly module set, from the latest
#    BL-Odoo-System-of-Record checkout (auto_install containment: sor_bidding
#    would reinstall itself on any registry update if its code were present)
./odoo-test/sync_addons.sh odoo-test/assemblies/deveres_april.yaml \
    ~/Documents/Cimelium/BL-Odoo-System-of-Record

# 2. fresh containers + restore the real backup
cd odoo-test && docker compose down -v && \
    ./restore.sh ~/Downloads/odoo_deveres_april_test_<stamp>.zip && cd ..

# 3. upgrade to the latest module code, run the assembly, drop Inventory,
#    verify (38 checks), then the full real-data workflow — one command:
./scripts/launch_simulation.sh ~/Downloads/odoo_deveres_april_test_<stamp>.zip
```

`scripts/launch_simulation.sh` is the Phase-22 launch rehearsal: clean
rebuild → 38 environment checks → contacts upload→approve→push→refresh
(must converge in ONE pass) → lots hammer+buyer+sold push (verified,
idempotent). It exits non-zero on any failure.

Stack parity (deveres.yaml v1.1, Sprint 24): **no** sor_bidding, artwork,
locations, tracking, legal-agreement, and **no Inventory (stock)** — the
13-Jul meeting walkthrough uninstalled exactly these. `buyer_id` lives
directly on `sor.lot` (visible below Hammer Price once the lot is Sold);
`lot_suffix` no longer exists upstream (suffix lots are combined in
`lot_number`, e.g. "25A", matching Blue Cubes).

## 8. Demo reset (self-serve, 13-Jul-2026)

`POST /reconcile/demo/reset` (admin) — reverts the demo dataset to its
original unreconciled state so the full pipeline can be re-tested from
scratch: seeded contacts restored (push-created `BC-…` clients removed),
every lot back to pre-sale (hammer 0, no buyer, not Sold — stray ad-hoc lots
included), the working session/staging ARCHIVED to `output/demo-archive-<ts>/`,
and the master re-pulled from Odoo. Exposed in the UI as the red
**↺ Reset demo data** button on the sync bar.

Enable on the demo server only:

```bash
# .env — demo box (the route 404s without this, and refuses any ODOO_DB
# that is not the demo database)
RECON_ENABLE_DEMO_RESET=1
```

The Blue Cubes exports are static inputs and are never touched.
