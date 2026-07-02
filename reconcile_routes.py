"""
Deviours Auction — Contact Reconciliation · API routes
=======================================================

A self-contained FastAPI APIRouter that exposes the reconciliation engine and
serves the review UI. Wired into the main app via `app.include_router(router)`.

  GET  /reconcile                     → review UI (SPA)
  GET  /reconcile/health              → status + master size
  POST /reconcile/upload              → process an uploaded Blue Cubes CSV
  GET  /reconcile/results             → paginated / filtered / sorted rows
  GET  /reconcile/results/{index}     → full field-diff detail for one contact
  POST /reconcile/decide              → set reviewer action on selected rows
  GET  /reconcile/export?fmt=csv|json → download reconciled output
  GET  /reconcile/odoo-preview        → Odoo-ready intermediate model
  GET  /reconcile/lots                → Lot List import preview (Hammer forced 0)

The canonical master (All Clients.csv) is baked in and loaded once at startup;
the user only ever uploads the Blue Cubes export.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

from reconciliation import (
    Action, MasterRepository, ReconciliationEngine, load_incoming, load_lots,
)
from reconciliation.export import to_csv, to_json, odoo_intermediate

BASE_DIR    = Path(__file__).resolve().parent
MASTER_PATH = os.environ.get("RECON_MASTER_CSV", str(BASE_DIR / "All Clients.csv"))
LOTS_PATH   = os.environ.get("RECON_LOTS_CSV",   str(BASE_DIR / "Lot List Export 30 June 2026.csv"))
UI_PATH     = BASE_DIR / "static" / "reconcile.html"

router = APIRouter(prefix="/reconcile", tags=["reconciliation"])

# ── Lazy singletons ──────────────────────────────────────────────────────────
_master: MasterRepository | None = None
_engine: ReconciliationEngine | None = None
_state: dict = {"results": [], "summary": None, "filename": None}


def _get_engine() -> ReconciliationEngine:
    global _master, _engine
    if _engine is None:
        _master = MasterRepository.from_csv(MASTER_PATH)
        _engine = ReconciliationEngine(_master)
    return _engine


# ── UI ────────────────────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
def ui():
    if UI_PATH.exists():
        return HTMLResponse(UI_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Reconciliation UI missing</h1>", status_code=500)


@router.get("/health")
def health():
    eng = _get_engine()
    return {"status": "ok", "master_records": len(eng.master),
            "loaded_upload": _state["filename"],
            "results_cached": len(_state["results"])}


# ── Upload + process ────────────────────────────────────────────────────────
@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv export from Blue Cubes.")
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        incoming = load_incoming(raw, is_path=False)
    except Exception as e:
        raise HTTPException(400, f"Could not parse CSV: {e}")
    if not incoming:
        raise HTTPException(400, "No buyer rows found in the uploaded file.")
    results, summary = _get_engine().run(incoming)
    _state.update(results=results, summary=summary, filename=file.filename)
    return {"summary": summary.to_dict(), "filename": file.filename}


# ── Results (paginated / filtered / sorted) ───────────────────────────────────
@router.get("/results")
def results(status: str = Query("all"), q: str = "", sort: str = "confidence",
            order: str = "desc", page: int = 1, page_size: int = 25):
    rows = _state["results"]
    if not rows:
        raise HTTPException(404, "No results — upload a Blue Cubes export first.")
    filt = rows
    if status and status != "all":
        filt = [r for r in filt if r.classification.value == status]
    if q:
        ql = q.lower()
        filt = [r for r in filt if ql in r.incoming_name.lower()
                or ql in (r.master_name or "").lower() or ql in r.buyer_number.lower()]
    key = {"confidence": lambda r: r.confidence,
           "name": lambda r: r.incoming_name.lower(),
           "status": lambda r: r.classification.value,
           "changes": lambda r: len(r.changed_fields)}.get(sort, lambda r: r.confidence)
    filt = sorted(filt, key=key, reverse=(order == "desc"))
    total = len(filt)
    start = max(0, (page - 1) * page_size)
    page_rows = filt[start:start + page_size]
    return {"total": total, "page": page, "page_size": page_size,
            "rows": [r.to_dict() for r in page_rows]}


@router.get("/results/{index}")
def result_detail(index: int):
    rows = _state["results"]
    match = next((r for r in rows if r.index == index), None)
    if match is None:
        raise HTTPException(404, "Unknown result index.")
    return match.to_dict(full=True)


# ── Reviewer decisions ─────────────────────────────────────────────────────────
@router.post("/decide")
def decide(payload: dict):
    action = payload.get("action", "").upper()
    indices = payload.get("indices", [])
    try:
        act = Action(action)
    except ValueError:
        raise HTTPException(400, f"Invalid action '{action}'.")
    idxset = set(indices)
    n = 0
    for r in _state["results"]:
        if not indices or r.index in idxset:
            r.action = act; n += 1
    return {"updated": n, "action": act.value}


# ── Exports ────────────────────────────────────────────────────────────────────
@router.get("/export")
def export(fmt: str = "csv"):
    rows = _state["results"]
    if not rows:
        raise HTTPException(404, "Nothing to export.")
    if fmt == "json":
        return Response(to_json(rows, _state["summary"]), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=reconciliation.json"})
    return Response(to_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=reconciliation.csv"})


@router.get("/odoo-preview")
def odoo_preview():
    rows = _state["results"]
    if not rows:
        raise HTTPException(404, "Nothing to preview.")
    return JSONResponse(odoo_intermediate(rows))


# ── Lots import preview (Hammer forced 0) ─────────────────────────────────────
@router.get("/lots")
def lots_preview(limit: int = 25):
    if not Path(LOTS_PATH).exists():
        raise HTTPException(404, "No lot list export available on the server.")
    lots = load_lots(LOTS_PATH)
    return {"total": len(lots), "hammer_rule": "forced to 0 on import",
            "lots": lots[:limit]}
