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
