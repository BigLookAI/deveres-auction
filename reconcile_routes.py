"""
deVeres Auction — Contact Reconciliation · API routes
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

import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from reconciliation import (
    Action, MasterRepository, ReconciliationEngine, load_lots,
)
from reconciliation.models import recon_result_from_dict
from reconciliation.repository import load_upload
from reconciliation.export import to_csv, to_json, to_xlsx, to_pdf_summary, odoo_intermediate

log = logging.getLogger("reconcile")

# ── Authentication (HTTP Basic) — buyer personal data must not be public ────
_security = HTTPBasic()
RECON_USER = os.environ.get("RECON_USER", "admin@deveres.ie")
RECON_PASS = os.environ.get("RECON_PASS", "Admin2026!")


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    ok = (secrets.compare_digest(credentials.username, RECON_USER)
          and secrets.compare_digest(credentials.password, RECON_PASS))
    if not ok:
        raise HTTPException(401, "Invalid credentials",
                            headers={"WWW-Authenticate": "Basic realm=reconciliation"})
    return credentials.username

BASE_DIR     = Path(__file__).resolve().parent
MASTER_PATH  = os.environ.get("RECON_MASTER_CSV", str(BASE_DIR / "All Clients.csv"))
LOTS_PATH    = os.environ.get("RECON_LOTS_CSV",   str(BASE_DIR / "Lot List Export 30 June 2026.csv"))
UI_PATH      = BASE_DIR / "static" / "reconcile.html"
SESSION_PATH = BASE_DIR / "output" / "reconcile_session.json"
SESSIONS_DIR = BASE_DIR / "output" / "sessions"
AUDIT_PATH   = BASE_DIR / "output" / "reconcile_audit.log"

router = APIRouter(prefix="/reconcile", tags=["reconciliation"],
                   dependencies=[Depends(require_auth)])

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


def _audit(event: str, **kw) -> None:
    """Append-only audit trail of consequential reconciliation actions."""
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **kw}
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("reconcile: audit write failed: %s", exc)


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
    # named per-upload snapshot (multi-session support)
    sid = time.strftime("%Y%m%d-%H%M%S") + "-" + "".join(
        c if c.isalnum() else "-" for c in file.filename)[:60]
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        (SESSIONS_DIR / f"{sid}.json").write_text(SESSION_PATH.read_text(encoding="utf-8"),
                                                  encoding="utf-8")
    except Exception as exc:
        log.warning("reconcile: session snapshot failed: %s", exc)
    _audit("upload", filename=file.filename, kind=kind, contacts=len(results), session=sid)
    log.info("reconcile: processed '%s' (%s, %d contacts)", file.filename, kind, len(results))
    return {"summary": summary.to_dict(), "filename": file.filename, "kind": kind, "session": sid}


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
    _audit("decide", action=act.value, rows=n, indices=len(indices), status=status or None)
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


# ── Named sessions (one per uploaded auction file) ────────────────────────────
@router.get("/sessions")
def list_sessions():
    if not SESSIONS_DIR.exists():
        return {"sessions": []}
    out = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"sid": f.stem, "filename": d.get("filename"), "kind": d.get("kind"),
                        "total": (d.get("summary") or {}).get("total"),
                        "active": d.get("filename") == _state.get("filename")})
        except Exception:
            continue
    return {"sessions": out}


@router.post("/sessions/{sid}/activate")
def activate_session(sid: str):
    f = SESSIONS_DIR / f"{Path(sid).name}.json"
    if not f.exists():
        raise HTTPException(404, "Unknown session.")
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    _state.update(results=[], summary=None, filename=None, kind=None, loaded_from_disk=False)
    _restore_session()
    _audit("session_activate", session=sid)
    return {"activated": sid, "results": len(_state["results"])}


# ── Master data-quality report (intra-master duplicates, misfiled Eircodes) ──
@router.get("/master-quality")
def master_quality(sample: int = 8):
    from reconciliation import normalize as N
    eng = _get_engine()
    idx = eng.index
    groups = []
    for kind, index in (("email", idx.by_email), ("phone", idx.by_phone), ("name", idx.by_name)):
        for key, ids in index.items():
            if len(ids) > 1:
                groups.append({"matched_on": kind, "key": key, "count": len(ids),
                               "refs": [eng.master.records[i].get("client_ref") for i in ids[:6]],
                               "names": [f"{eng.master.records[i].get('first_name','')} "
                                         f"{eng.master.records[i].get('last_name','')}".strip()
                                         for i in ids[:6]]})
    misfiled = sum(1 for m in eng.master.records
                   if N.is_eircode(m.get("town", "")) and not m.get("postcode"))
    groups.sort(key=lambda g: g["count"], reverse=True)
    return {"master_records": len(eng.master),
            "duplicate_groups": len(groups),
            "duplicate_breakdown": {k: sum(1 for g in groups if g["matched_on"] == k)
                                    for k in ("email", "phone", "name")},
            "misfiled_eircodes": misfiled,
            "sample_groups": groups[:sample],
            "note": "Duplicate groups share a normalised email/phone/name key. "
                    "Recommend a supervised de-duplication pass before Odoo import."}


# ── Odoo import (dry-run by default; live writes env-gated) ──────────────────
@router.post("/odoo-import")
def odoo_import(payload: dict | None = None):
    """Apply approved reconciliation actions to Odoo res.partner.
    dry_run=true (default): plan + resolve only — NO writes. Live writes require
    dry_run=false AND RECON_ALLOW_ODOO_WRITE=1 on the server."""
    from reconciliation.odoo_import import OdooImporter, plan as build_plan
    _restore_session()
    rows = _state["results"]
    if not rows:
        raise HTTPException(404, "Nothing to import — run a reconciliation first.")
    payload = payload or {}
    dry_run = bool(payload.get("dry_run", True))
    intermediate = odoo_intermediate(rows)
    ops = build_plan(intermediate, source_file=_state.get("filename") or "")
    connected = bool(os.environ.get("ODOO_URL"))
    if not connected:
        # plan-only mode: no Odoo credentials configured on this server
        result = {"summary": {"dry_run": True, "connected": False,
                              "create": sum(1 for o in ops if o.op == "create"),
                              "write": sum(1 for o in ops if o.op == "write"),
                              "skip": sum(1 for o in ops if o.op == "skip"),
                              "total": len(ops),
                              "id_checks_required": sum(1 for o in ops if o.id_check)},
                  "operations": [o.to_dict() for o in ops],
                  "note": "ODOO_URL not configured — returning the import plan only."}
        _audit("odoo_import_plan", **result["summary"])
        return result
    try:
        importer = OdooImporter()
        result = importer.execute(ops, dry_run=dry_run)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(502, f"Odoo connection failed: {e}")
    result["summary"]["connected"] = True
    _audit("odoo_import", **result["summary"])
    return result


# ── Lots import preview (Hammer forced 0) ─────────────────────────────────────
@router.get("/lots")
def lots_preview(limit: int = 25):
    if not Path(LOTS_PATH).exists():
        raise HTTPException(404, "No lot list export available on the server.")
    lots = load_lots(LOTS_PATH)
    return {"total": len(lots), "hammer_rule": "forced to 0 on import",
            "lots": lots[:limit]}
