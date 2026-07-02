"""
deVeres Auction — PRODUCT 1: Contact Reconciliation (standalone app)
=====================================================================

Completely independent of the AI Bidder Evaluation product (2-Jul-2026
decision): its own FastAPI app, its own landing, its own deployment.

    Blue Cube Export → Reconciliation Engine → Review → Approval
                     → Temporary Staging → Push to Odoo

Run:    uvicorn recon_app:app --host 0.0.0.0 --port 8003
        (or ./run.sh)

The review UI lives at /reconcile (HTTP Basic protected — personal data).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from reconcile_routes import router as reconcile_router

app = FastAPI(
    title="deVeres Auction — Contact Reconciliation",
    description=("Reconciles Blue Cubes auction exports against the canonical "
                 "client database, with a review/edit/approve workflow, a staging "
                 "layer and a gated Odoo push. By Cimelium."),
    version="2.0.0",
)

app.include_router(reconcile_router)


@app.get("/health")
def health():
    """Unauthenticated liveness probe (no data exposed)."""
    return {"status": "ok", "product": "contact-reconciliation"}


@app.get("/", response_class=HTMLResponse)
def landing():
    """Product-1 landing: reconciliation only — no other product is linked
    here by design (separate tools, separate front doors)."""
    return HTMLResponse("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>deVeres — Contact Reconciliation</title>
<style>
  body{margin:0;background:#0e1116;color:#eef2f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh}
  .card{max-width:640px;padding:48px 44px;background:#161a22;border:1px solid #232833;border-radius:18px}
  h1{margin:0 0 6px;font-size:26px} .sub{color:#8b93a7;font-size:13px;margin-bottom:22px}
  p{color:#aab2c5;line-height:1.6;font-size:14.5px}
  .flow{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:#8b93a7;background:#0f131a;
        border:1px solid #232833;border-radius:10px;padding:14px 16px;margin:18px 0}
  a.btn{display:inline-block;background:#6366f1;color:#fff;text-decoration:none;font-weight:700;
        border-radius:10px;padding:12px 22px;margin-top:8px}
  .cred{font-size:12px;color:#8b93a7;margin-top:14px}
  code{background:#1b2130;border-radius:5px;padding:1px 6px}
</style></head><body>
<div class="card">
  <h1>Contact Reconciliation</h1>
  <div class="sub">deVeres Auction · Blue Cubes → System of Record · by Cimelium</div>
  <p>Cleans incoming auction data before it touches the system of record:
     every uploaded contact is matched against the canonical client database,
     classified, reviewed and approved into a staging dataset — which is the
     only payload ever pushed to Odoo.</p>
  <div class="flow">Blue&nbsp;Cube&nbsp;Export → Reconciliation&nbsp;Engine → Review → Approval → Staging → Push&nbsp;to&nbsp;Odoo</div>
  <a class="btn" href="/reconcile">Open the reconciliation workspace →</a>
  <div class="cred">Sign-in required — this workspace handles personal client data.
  Login: <code>admin@deveres.ie</code> / <code>Admin2026!</code></div>
</div>
</body></html>""")


@app.get("/overview")
def overview_redirect():
    """The old shared landing no longer exists — reconciliation is standalone."""
    return RedirectResponse("/", status_code=308)
