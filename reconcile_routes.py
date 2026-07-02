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

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

from reconciliation import (
    Action, MasterRepository, ReconciliationEngine, load_lots,
)
from reconciliation.models import recon_result_from_dict
from reconciliation.repository import load_upload
from reconciliation.export import to_csv, to_json, to_xlsx, to_pdf_summary, odoo_intermediate

log = logging.getLogger("reconcile")

BASE_DIR     = Path(__file__).resolve().parent
MASTER_PATH  = os.environ.get("RECON_MASTER_CSV", str(BASE_DIR / "All Clients.csv"))
LOTS_PATH    = os.environ.get("RECON_LOTS_CSV",   str(BASE_DIR / "Lot List Export 30 June 2026.csv"))
UI_PATH      = BASE_DIR / "static" / "reconcile.html"
SESSION_PATH = BASE_DIR / "output" / "reconcile_session.json"

router = APIRouter(prefix="/reconcile", tags=["reconciliation"])

# ── Lazy singletons + durable session ────────────────────────────────────────
_master: MasterRepository | None = None
_engine: ReconciliationEngine | None = None
_state: dict = {"results": [], "summary": None, "filename": None, "kind": None,
                "loaded_from_disk": False}


def _get_engine() -> ReconciliationEngine:
    global _master, _engine
    if _engine is None:
        _master = MasterRepository.from_csv(MASTER_PATH)
        _engine = ReconciliationEngine(_master)
        log.info("reconcile: master loaded (%d records)", len(_master))
    return _engine


def _save_session() -> None:
    """Persist the session (results + decisions) so a restart / --reload never
    loses reviewer work. Best-effort — failures are logged, not raised."""
    try:
        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "filename": _state["filename"], "kind": _state["kind"],
            "summary": _state["summary"].to_dict() if hasattr(_state["summary"], "to_dict") else _state["summary"],
            "results": [r.to_dict(full=True) for r in _state["results"]],
        }
        SESSION_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log.warning("reconcile: session save failed: %s", exc)


def _restore_session() -> None:
    """Load the last persisted session once per process (survives --reload)."""
    if _state["loaded_from_disk"] or _state["results"]:
        return
    _state["loaded_from_disk"] = True
    try:
        if SESSION_PATH.exists():
            payload = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
            _state["results"] = [recon_result_from_dict(d) for d in payload.get("results", [])]
            _state["summary"] = payload.get("summary")
            _state["filename"] = payload.get("filename")
            _state["kind"] = payload.get("kind")
            log.info("reconcile: restored session '%s' (%d results)",
                     _state["filename"], len(_state["results"]))
    except Exception as exc:
        log.warning("reconcile: session restore failed: %s", exc)


# ── UI ────────────────────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
def ui():
    if UI_PATH.exists():
        return HTMLResponse(UI_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Reconciliation UI missing</h1>", status_code=500)


@router.get("/health")
def health():
    eng = _get_engine()
    _restore_session()
    return {"status": "ok", "master_records": len(eng.master),
            "loaded_upload": _state["filename"], "upload_kind": _state["kind"],
            "results_cached": len(_state["results"]),
            "session_persisted": SESSION_PATH.exists()}


@router.get("/session")
def session():
    """Restore point for the UI: the last processed upload's summary, so a page
    reload (or server restart) lands back on the dashboard, not a blank screen."""
    _restore_session()
    if not _state["results"]:
        raise HTTPException(404, "No reconciliation session yet.")
    summary = _state["summary"]
    return {"summary": summary.to_dict() if hasattr(summary, "to_dict") else summary,
            "filename": _state["filename"], "kind": _state["kind"]}


# ── Upload + process ────────────────────────────────────────────────────────
@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv export from Blue Cubes.")
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        kind, incoming = load_upload(raw)      # auto-detects buyers vs sellers export
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Could not parse CSV: {e}")
    if not incoming:
        raise HTTPException(400, "No contact rows found in the uploaded file.")
    results, summary = _get_engine().run(incoming)
    _state.update(results=results, summary=summary, filename=file.filename, kind=kind)
    _save_session()
    log.info("reconcile: processed '%s' (%s, %d contacts)", file.filename, kind, len(results))
    return {"summary": summary.to_dict(), "filename": file.filename, "kind": kind}


# ── Results (paginated / filtered / sorted) ───────────────────────────────────
@router.get("/results")
def results(status: str = Query("all"), q: str = "", sort: str = "confidence",
            order: str = "desc", page: int = 1, page_size: int = 25):
    _restore_session()
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
    _restore_session()
    rows = _state["results"]
    match = next((r for r in rows if r.index == index), None)
    if match is None:
        raise HTTPException(404, "Unknown result index.")
    return match.to_dict(full=True)


# ── Reviewer decisions ─────────────────────────────────────────────────────────
@router.post("/decide")
def decide(payload: dict):
    """Set a reviewer action on an EXPLICIT scope — either specific row indices
    or all rows of a given classification (e.g. every 'update'). An empty scope
    is rejected rather than silently applying to everything."""
    _restore_session()
    action = payload.get("action", "").upper()
    indices = payload.get("indices") or []
    status = (payload.get("status") or "").lower()
    try:
        act = Action(action)
    except ValueError:
        raise HTTPException(400, f"Invalid action '{action}'.")
    if not indices and not status:
        raise HTTPException(400, "Provide 'indices' (row list) or 'status' "
                                 "(classification, e.g. 'update') — refusing an empty scope.")
    idxset = set(indices)
    n = 0
    for r in _state["results"]:
        if (indices and r.index in idxset) or (status and r.classification.value == status):
            r.action = act; n += 1
    _save_session()
    log.info("reconcile: decision %s applied to %d rows (indices=%d, status=%s)",
             act.value, n, len(indices), status or "-")
    return {"updated": n, "action": act.value}


# ── Exports (CSV / JSON / Excel / PDF summary) ───────────────────────────────
@router.get("/export")
def export(fmt: str = "csv"):
    _restore_session()
    rows = _state["results"]
    if not rows:
        raise HTTPException(404, "Nothing to export.")
    summary = _state["summary"]
    if fmt == "json":
        return Response(to_json(rows, summary), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=reconciliation.json"})
    if fmt == "xlsx":
        try:
            data = to_xlsx(rows, summary)
        except ImportError:
            raise HTTPException(501, "Excel export requires 'openpyxl' on the server.")
        return Response(data,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=reconciliation.xlsx"})
    if fmt == "pdf":
        try:
            data = to_pdf_summary(rows, summary)
        except ImportError:
            raise HTTPException(501, "PDF export requires 'fpdf2' on the server.")
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=reconciliation-summary.pdf"})
    return Response(to_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=reconciliation.csv"})


@router.get("/odoo-preview")
def odoo_preview():
    _restore_session()
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
