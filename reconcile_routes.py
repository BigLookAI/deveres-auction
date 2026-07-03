"""
deVeres Auction — Contact Reconciliation · API routes
=======================================================

A self-contained FastAPI APIRouter that exposes the reconciliation engine and
serves the review UI. Wired into the Product-1 app via `app.include_router`.

Core flow (2-Jul-2026 meeting):  upload → review → edit → approve → STAGING →
push to Odoo. Approving never touches Odoo directly; it stages the approved
values, and the staging repository is the only push payload.

  GET  /reconcile                          → review UI (SPA)
  GET  /reconcile/health                   → status + master size
  POST /reconcile/upload                   → process an uploaded Blue Cubes CSV
  GET  /reconcile/results                  → paginated / filtered / sorted rows
  GET  /reconcile/results/{index}          → full detail incl. match evidence
  GET  /reconcile/progress                 → live per-state counters
  POST /reconcile/records/{index}/edit     → save manual field edits (staging-only)
  DELETE /reconcile/records/{index}/edit   → discard edits
  POST /reconcile/records/{index}/approve  → approve → write to staging
  POST /reconcile/records/{index}/reject   → reject (withdraws staging entry)
  POST /reconcile/records/{index}/reopen   → reopen a rejected/decided record
  POST /reconcile/records/{index}/keep-existing → confirm no change needed
  GET  /reconcile/records/{index}/history  → approval/state history
  POST /reconcile/approve-bulk             → approve many (indices or state)
  GET  /reconcile/staging                  → pending changes (the push payload)
  GET  /reconcile/staging/export?fmt=csv   → pending-changes file
  POST /reconcile/decide                   → legacy bulk decision (state-engine backed)
  GET  /reconcile/export?fmt=csv|json|xlsx|pdf → reconciled results
  GET  /reconcile/odoo-preview             → Odoo-ready intermediate model
  POST /reconcile/odoo-import              → dry-run/live push FROM STAGING
  GET  /reconcile/master-quality           → master data-quality report
  GET  /reconcile/lots                     → Lot List import preview (Hammer forced 0)

Security: HTTP Basic. RECON_USER/RECON_PASS is the admin (read-write) account;
optional RECON_VIEWER_USER/RECON_VIEWER_PASS adds a read-only account. All
consequential actions carry the acting username into the audit trail.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import secrets
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from reconciliation import (
    Action, MasterRepository, ReconciliationEngine, StagingRepository,
    RecordState, TransitionError, initial_state, validate_transition,
    STATE_LABELS, STAGED_STATES, load_lots,
)
from reconciliation.models import ReconResult, recon_result_from_dict
from reconciliation.repository import load_upload
from reconciliation.export import to_csv, to_json, to_xlsx, to_pdf_summary, odoo_intermediate

log = logging.getLogger("reconcile")

# ── Authentication + roles (HTTP Basic) — personal data must not be public ───
_security = HTTPBasic()
RECON_USER = os.environ.get("RECON_USER", "admin@deveres.ie")
RECON_PASS = os.environ.get("RECON_PASS", "Admin2026!")
VIEWER_USER = os.environ.get("RECON_VIEWER_USER", "")
VIEWER_PASS = os.environ.get("RECON_VIEWER_PASS", "")


def _role_for(credentials: HTTPBasicCredentials) -> str | None:
    if (secrets.compare_digest(credentials.username, RECON_USER)
            and secrets.compare_digest(credentials.password, RECON_PASS)):
        return "admin"
    if VIEWER_USER and (secrets.compare_digest(credentials.username, VIEWER_USER)
                        and secrets.compare_digest(credentials.password, VIEWER_PASS)):
        return "viewer"
    return None


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    if _role_for(credentials) is None:
        raise HTTPException(401, "Invalid credentials",
                            headers={"WWW-Authenticate": "Basic realm=reconciliation"})
    return credentials.username


def require_editor(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """Write actions (edit/approve/reject/push) need the admin role — the
    optional viewer account is strictly read-only."""
    role = _role_for(credentials)
    if role is None:
        raise HTTPException(401, "Invalid credentials",
                            headers={"WWW-Authenticate": "Basic realm=reconciliation"})
    if role != "admin":
        raise HTTPException(403, "Read-only account: this action needs the admin login.")
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

# Fields the reviewer may edit before approval (per the 2-Jul meeting).
EDITABLE_FIELDS = {"first_name", "last_name", "email", "phone", "company",
                   "address1", "address2", "town", "county", "postcode",
                   "country", "notes"}
_CONTACT_FIELDS = ["first_name", "last_name", "email", "phone", "company",
                   "address1", "address2", "town", "county", "postcode", "country"]

# ── Lazy singletons + durable session ────────────────────────────────────────
_master: MasterRepository | None = None
_engine: ReconciliationEngine | None = None
_staging: StagingRepository | None = None
_state: dict = {"results": [], "summary": None, "filename": None, "kind": None,
                "session_id": None, "loaded_from_disk": False,
                "master_fallback": None}


def _master_source_setting() -> str:
    """RECON_MASTER_SOURCE = csv | odoo | auto (default).
    auto → Odoo when ODOO_URL is configured, else the static CSV. This makes
    the 3-Jul cut-over automatic wherever Odoo credentials exist, while servers
    without them (e.g. the DGX until De Veres share their instance) keep
    working unchanged."""
    return (os.environ.get("RECON_MASTER_SOURCE") or "auto").strip().lower()


def _load_master() -> MasterRepository:
    """Build the master from the configured source. In auto mode an Odoo
    failure falls back to the CSV (loudly — flagged in /health and the audit
    log); explicit odoo mode fails fast so a misconfiguration can't silently
    reconcile against a stale spreadsheet."""
    setting = _master_source_setting()
    want_odoo = setting == "odoo" or (setting == "auto" and os.environ.get("ODOO_URL"))
    if want_odoo:
        try:
            repo = MasterRepository.from_odoo()
            _state["master_fallback"] = None
            return repo
        except Exception as exc:
            if setting == "odoo":
                raise
            _state["master_fallback"] = f"{type(exc).__name__}: {exc}"
            log.error("reconcile: Odoo master fetch failed (%s) — falling back "
                      "to the static CSV. Reconciliation is running against a "
                      "SNAPSHOT, not the system of record.", exc)
            _audit("master_fallback", error=str(exc), source_setting=setting)
    return MasterRepository.from_csv(MASTER_PATH)


def _get_engine() -> ReconciliationEngine:
    global _master, _engine
    if _engine is None:
        _master = _load_master()
        _engine = ReconciliationEngine(_master)
        log.info("reconcile: master loaded from %s (%d records)",
                 _master.source, len(_master))
    return _engine


def _get_staging() -> StagingRepository:
    global _staging
    if _staging is None:
        _staging = StagingRepository()
    return _staging


def _session_id() -> str:
    return _state.get("session_id") or _state.get("filename") or "default"


def _save_session() -> None:
    """Persist the session (results + decisions + states) so a restart never
    loses reviewer work. Best-effort — failures are logged, not raised."""
    try:
        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "filename": _state["filename"], "kind": _state["kind"],
            "session_id": _state.get("session_id"),
            "uploaded_at": _state.get("uploaded_at"),
            "summary": _state["summary"].to_dict() if hasattr(_state["summary"], "to_dict") else _state["summary"],
            "results": [r.to_dict(full=True) for r in _state["results"]],
        }
        SESSION_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        # keep the named snapshot in sync so re-activating it later keeps decisions
        sid = _state.get("session_id")
        if sid:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            (SESSIONS_DIR / f"{sid}.json").write_text(
                SESSION_PATH.read_text(encoding="utf-8"), encoding="utf-8")
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
            # Heal sessions persisted before NEW clients carried a field report:
            # rebuild their diffs (incoming vs empty master) so the review
            # drawer's Incoming column is populated on old sessions too.
            from reconciliation.classify import diff_fields
            for r in _state["results"]:
                if not r.diffs and r.incoming and not r.master_ref:
                    r.diffs = diff_fields(r.incoming, {})
            _state["summary"] = payload.get("summary")
            _state["filename"] = payload.get("filename")
            _state["kind"] = payload.get("kind")
            _state["session_id"] = payload.get("session_id") or payload.get("filename")
            _state["uploaded_at"] = payload.get("uploaded_at")
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


def _get_result(index: int) -> ReconResult:
    _restore_session()
    match = next((r for r in _state["results"] if r.index == index), None)
    if match is None:
        raise HTTPException(404, "Unknown result index.")
    return match


# ── Workflow core: transition + staging as one unit ──────────────────────────
def _transition(r: ReconResult, target: RecordState, actor: str, note: str = "") -> None:
    """Validate + apply + persist + audit a state change. Raises 409 on an
    illegal move so the UI can explain instead of silently doing nothing."""
    try:
        validate_transition(r.state, target)
    except TransitionError as e:
        raise HTTPException(409, str(e))
    frm = r.state.value
    r.record_transition(target, actor, note)
    _get_staging().log_transition(_session_id(), r.index, frm, target.value, actor, note)
    _audit("state", index=r.index, buyer=r.buyer_number, frm=frm,
           to=target.value, actor=actor, note=note)


def _approved_values(r: ReconResult) -> tuple[dict, list[str], list[str]]:
    """Merge = incoming snapshot overlaid with the reviewer's edits (editable
    fields only). Returns (approved, changed_fields, edited_fields) where
    changed_fields are canonical field names destined for the Odoo write."""
    approved = {f: r.incoming.get(f, "") for f in _CONTACT_FIELDS}
    edited = []
    for f, v in (r.edits or {}).items():
        if f in EDITABLE_FIELDS and f != "notes":
            approved[f] = (v or "").strip()
            edited.append(f)
    # fields that genuinely change the master: significant diffs + any edits.
    # NEW clients have no master to change — their diffs are vs an empty
    # record (display only), so they contribute nothing here.
    changed = [d.field for d in r.diffs
               if d.significant and d.status.value in ("changed", "new_info")] \
        if r.master_ref else []
    for f in edited:
        if f not in changed:
            changed.append(f)
    return approved, changed, edited


def _stage(r: ReconResult, change_type: str, actor: str, note: str = "") -> None:
    approved, changed, edited = _approved_values(r)
    r.approved_values = approved
    _get_staging().stage(
        session=_session_id(), record_index=r.index, buyer_number=r.buyer_number,
        change_type=change_type, master_ref=r.master_ref or "",
        name=r.incoming_name or r.master_name,
        original=r.master or {}, incoming=r.incoming or {}, approved=approved,
        edited_fields=edited, changed_fields=changed,
        confidence=r.confidence, matched_by=r.matched_by, lots=r.lots or [],
        actor=actor, note=note or (r.edits.get("notes", "") if r.edits else ""))


def _unstage_if_staged(r: ReconResult, actor: str, note: str) -> None:
    _get_staging().withdraw(_session_id(), r.index, actor, note)


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
            "master_source": eng.master.source,
            "master_loaded_at": eng.master.loaded_at,
            "master_source_setting": _master_source_setting(),
            "master_fallback": _state.get("master_fallback"),
            "loaded_upload": _state["filename"], "upload_kind": _state["kind"],
            "session_id": _state.get("session_id"),
            "results_cached": len(_state["results"]),
            "session_persisted": SESSION_PATH.exists(),
            "staging_counts": _get_staging().counts(_session_id())}


@router.post("/master/reload")
def master_reload(user: str = Depends(require_editor)):
    """Re-fetch the master from the configured source without a restart —
    e.g. straight after an Odoo push, so the next reconciliation sees the
    partners it just created/updated (keeps re-uploads idempotent)."""
    global _master, _engine
    t0 = time.perf_counter()
    try:
        repo = _load_master()
    except Exception as exc:
        raise HTTPException(502, f"Master reload failed: {exc}")
    _master, _engine = repo, ReconciliationEngine(repo)
    ms = round((time.perf_counter() - t0) * 1000)
    _audit("master_reload", source=repo.source, records=len(repo),
           duration_ms=ms, actor=user)
    log.info("reconcile: master reloaded from %s (%d records, %dms) by %s",
             repo.source, len(repo), ms, user)
    return {"master_source": repo.source, "master_records": len(repo),
            "master_loaded_at": repo.loaded_at, "duration_ms": ms,
            "master_fallback": _state.get("master_fallback")}


@router.get("/session")
def session():
    """Restore point for the UI: the last processed upload's summary, so a page
    reload (or server restart) lands back on the dashboard, not a blank screen."""
    _restore_session()
    if not _state["results"]:
        raise HTTPException(404, "No reconciliation session yet.")
    summary = _state["summary"]
    return {"summary": summary.to_dict() if hasattr(summary, "to_dict") else summary,
            "filename": _state["filename"], "kind": _state["kind"],
            "session_id": _state.get("session_id"),
            "uploaded_at": _state.get("uploaded_at")}


@router.get("/sample-csv")
def sample_csv():
    """Synthetic Blue Cubes export (fake data only) for demos and training:
    includes new clients, typos, format noise and all three manual-review cases.
    Upload it to see every workflow pathway populated."""
    p = BASE_DIR / "tests" / "fixtures" / "bluecube_test_export.csv"
    if not p.exists():
        raise HTTPException(404, "Sample dataset not present on this server.")
    return Response(p.read_text(encoding="utf-8"), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=bluecube-sample-export.csv"})


# ── Upload + process ────────────────────────────────────────────────────────
@router.post("/upload")
async def upload(file: UploadFile = File(...), user: str = Depends(require_editor)):
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
    cid = uuid.uuid4().hex[:12]
    eng = _get_engine()
    results, summary = eng.run(incoming)
    sid = time.strftime("%Y%m%d-%H%M%S") + "-" + "".join(
        c if c.isalnum() else "-" for c in file.filename)[:60]
    uploaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _state.update(results=results, summary=summary, filename=file.filename,
                  kind=kind, session_id=sid, uploaded_at=uploaded_at)
    _save_session()
    _audit("upload", cid=cid, filename=file.filename, kind=kind,
           contacts=len(results), session=sid, actor=user,
           master_source=eng.master.source, master_records=len(eng.master))
    log.info("reconcile[%s]: processed '%s' (%s, %d contacts) against %s master "
             "(%d records) in %.0fms", cid, file.filename, kind, len(results),
             eng.master.source, len(eng.master), summary.processing_ms)
    return {"summary": summary.to_dict(), "filename": file.filename, "kind": kind,
            "session": sid, "uploaded_at": uploaded_at, "correlation_id": cid,
            "master_source": eng.master.source,
            "shared_buyer_number_contacts": sum(1 for i in incoming
                                                if i.get("shared_buyer_number"))}


# ── Results (paginated / filtered / sorted) ───────────────────────────────────
@router.get("/results")
def results(status: str = Query("all"), state: str = Query("all"),
            q: str = "", sort: str = "confidence",
            order: str = "desc", page: int = 1, page_size: int = 25):
    _restore_session()
    rows = _state["results"]
    if not rows:
        raise HTTPException(404, "No results — upload a Blue Cubes export first.")
    filt = rows
    if status and status != "all":
        filt = [r for r in filt if r.classification.value == status]
    if state and state != "all":
        if state == "staged":                      # convenience filter: ready for Odoo
            filt = [r for r in filt if r.state in STAGED_STATES]
        else:
            filt = [r for r in filt if r.state.value == state]
    if q:
        ql = q.lower()

        def _hit(r) -> bool:
            if (ql in r.incoming_name.lower() or ql in (r.master_name or "").lower()
                    or ql in r.buyer_number.lower()):
                return True
            for rec in (r.incoming, r.master):
                for f in ("email", "phone", "mobile", "company", "town", "county"):
                    if ql in (rec.get(f, "") or "").lower():
                        return True
            return False
        filt = [r for r in filt if _hit(r)]
    key = {"confidence": lambda r: r.confidence,
           "name": lambda r: r.incoming_name.lower(),
           "status": lambda r: r.classification.value,
           "state": lambda r: r.state.value,
           "changes": lambda r: len(r.changed_fields)}.get(sort, lambda r: r.confidence)
    filt = sorted(filt, key=key, reverse=(order == "desc"))
    total = len(filt)
    start = max(0, (page - 1) * page_size)
    page_rows = filt[start:start + page_size]
    return {"total": total, "page": page, "page_size": page_size,
            "rows": [r.to_dict() for r in page_rows]}


@router.get("/progress")
def progress():
    """Live workflow counters: how many records sit in each lifecycle state,
    plus the staging (pending-changes) totals. Drives the UI progress bar."""
    _restore_session()
    rows = _state["results"]
    by_state = {s.value: 0 for s in RecordState}
    for r in rows:
        by_state[r.state.value] += 1
    return {"total": len(rows), "by_state": by_state,
            "labels": {s.value: STATE_LABELS[s] for s in RecordState},
            "staging": _get_staging().counts(_session_id()),
            "session_id": _session_id()}


@router.get("/results/{index}")
def result_detail(index: int):
    r = _get_result(index)
    d = r.to_dict(full=True)
    d["state_label"] = STATE_LABELS[r.state]
    d["editable_fields"] = sorted(EDITABLE_FIELDS)
    return d


@router.get("/records/{index}/history")
def record_history(index: int):
    r = _get_result(index)
    return {"index": index, "buyer_number": r.buyer_number,
            "state": r.state.value, "history": r.history,
            "transitions": _get_staging().history(_session_id(), index)}


# ── Manual edit (edits live ONLY in the session + staging; originals untouched) ─
@router.post("/records/{index}/edit")
def edit_record(index: int, payload: dict, user: str = Depends(require_editor)):
    r = _get_result(index)
    fields = payload.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        raise HTTPException(400, "Provide 'fields': {field: newValue, …}.")
    bad = sorted(set(fields) - EDITABLE_FIELDS)
    if bad:
        raise HTTPException(400, f"Field(s) not editable: {', '.join(bad)}. "
                                 f"Editable: {', '.join(sorted(EDITABLE_FIELDS))}.")
    if r.state == RecordState.PUSHED_TO_ODOO:
        raise HTTPException(409, "Record already pushed to Odoo — no further edits.")
    # keep only real changes vs the incoming snapshot
    cleaned = {f: (v or "").strip() for f, v in fields.items()}
    r.edits.update(cleaned)
    r.edits = {f: v for f, v in r.edits.items()
               if f == "notes" or v != (r.incoming.get(f, "") or "")}
    was_staged = r.state in STAGED_STATES
    if r.state != RecordState.MANUAL_EDIT:
        _transition(r, RecordState.MANUAL_EDIT, user,
                    f"edited: {', '.join(sorted(cleaned))}")
    if was_staged:   # editing a staged record pulls it back out of the push
        _unstage_if_staged(r, user, "edited after approval — re-approve to restage")
    _save_session()
    _audit("edit", index=index, buyer=r.buyer_number, fields=sorted(cleaned), actor=user)
    return {"index": index, "state": r.state.value, "state_label": STATE_LABELS[r.state],
            "edits": r.edits}


@router.delete("/records/{index}/edit")
def discard_edits(index: int, user: str = Depends(require_editor)):
    r = _get_result(index)
    if not r.edits:
        raise HTTPException(400, "No edits to discard.")
    r.edits = {}
    if r.state == RecordState.MANUAL_EDIT:
        _transition(r, initial_state(r.classification), user, "edits discarded")
    _save_session()
    _audit("edit_discard", index=index, buyer=r.buyer_number, actor=user)
    return {"index": index, "state": r.state.value, "state_label": STATE_LABELS[r.state]}


# ── Approve / reject / reopen / keep-existing ────────────────────────────────
def _approve_one(r: ReconResult, as_type: str | None, user: str) -> None:
    """Approve a record into staging. as_type overrides the change type for
    NEEDS_REVIEW records ('update' or 'new'); otherwise it is derived."""
    if as_type not in (None, "", "update", "new"):
        raise HTTPException(400, "'as' must be 'update' or 'new'.")
    derived = "new" if (r.state == RecordState.NEW_RECORD
                        or (r.state == RecordState.MANUAL_EDIT and not r.master_ref)
                        or (not r.master_ref and r.classification.value == "new")) else "update"
    change = as_type or derived
    if change == "update" and not r.master_ref:
        raise HTTPException(409, "Cannot approve as update: no master record is linked. "
                                 "Approve as 'new' instead.")
    target = RecordState.IMPORT_READY if change == "new" else RecordState.UPDATE_READY
    _transition(r, target, user, f"approved as {change}")
    _stage(r, "create" if change == "new" else "update", user)
    r.action = Action.ADD if change == "new" else Action.UPDATE


@router.post("/records/{index}/approve")
def approve_record(index: int, payload: dict | None = None,
                   user: str = Depends(require_editor)):
    r = _get_result(index)
    _approve_one(r, (payload or {}).get("as"), user)
    _save_session()
    return {"index": index, "state": r.state.value, "state_label": STATE_LABELS[r.state],
            "staging": _get_staging().counts(_session_id())}


@router.post("/records/{index}/reject")
def reject_record(index: int, payload: dict | None = None,
                  user: str = Depends(require_editor)):
    r = _get_result(index)
    reason = (payload or {}).get("reason", "")
    _transition(r, RecordState.REJECTED, user, reason or "rejected")
    _unstage_if_staged(r, user, reason or "rejected")
    r.action = Action.IGNORE
    _save_session()
    return {"index": index, "state": r.state.value, "state_label": STATE_LABELS[r.state]}


@router.post("/records/{index}/reopen")
def reopen_record(index: int, user: str = Depends(require_editor)):
    r = _get_result(index)
    target = RecordState.MANUAL_EDIT if r.edits else initial_state(r.classification)
    _transition(r, target, user, "reopened")
    _unstage_if_staged(r, user, "reopened — removed from pending push")
    _save_session()
    return {"index": index, "state": r.state.value, "state_label": STATE_LABELS[r.state]}


@router.post("/records/{index}/keep-existing")
def keep_existing(index: int, user: str = Depends(require_editor)):
    r = _get_result(index)
    _transition(r, RecordState.EXISTING_OK, user, "reviewer chose to keep existing record")
    _unstage_if_staged(r, user, "keep existing")
    r.action = Action.IGNORE
    _save_session()
    return {"index": index, "state": r.state.value, "state_label": STATE_LABELS[r.state]}


@router.post("/approve-bulk")
def approve_bulk(payload: dict, user: str = Depends(require_editor)):
    """Approve many records at once — by explicit indices or by current state
    (e.g. every 'update_suggested'). Illegal transitions are reported, not fatal."""
    _restore_session()
    indices = payload.get("indices") or []
    state_f = (payload.get("state") or "").lower()
    if not indices and not state_f:
        raise HTTPException(400, "Provide 'indices' or 'state' — refusing an empty scope.")
    idxset = set(indices)
    done, skipped = [], []
    for r in _state["results"]:
        if (indices and r.index in idxset) or (state_f and r.state.value == state_f):
            try:
                _approve_one(r, payload.get("as"), user)
                done.append(r.index)
            except HTTPException as e:
                skipped.append({"index": r.index, "reason": e.detail})
    _save_session()
    _audit("approve_bulk", approved=len(done), skipped=len(skipped), actor=user)
    return {"approved": done, "skipped": skipped,
            "staging": _get_staging().counts(_session_id())}


# ── Staging (pending changes = the Odoo push payload) ─────────────────────────
@router.get("/staging")
def staging_list(status: str = "ready"):
    _restore_session()
    repo = _get_staging()
    return {"session": _session_id(), "counts": repo.counts(_session_id()),
            "entries": repo.entries(_session_id(), status)}


@router.post("/staging/purge")
def staging_purge(payload: dict | None = None, user: str = Depends(require_editor)):
    """Retention purge: remove pushed/withdrawn staging rows older than the
    retention window (default 90 days; env RECON_STAGING_RETENTION_DAYS).
    Pending ('ready') rows and the audit/transition history are never touched."""
    days = (payload or {}).get("retention_days")
    try:
        result = _get_staging().purge(days)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _audit("staging_purge", actor=user, **result)
    return result


@router.get("/staging/export")
def staging_export(fmt: str = "csv", status: str = "ready"):
    repo = _get_staging()
    _restore_session()
    if fmt == "json":
        return Response(repo.export_json(_session_id(), status),
                        media_type="application/json",
                        headers={"Content-Disposition":
                                 "attachment; filename=pending-changes.json"})
    return Response(repo.export_csv(_session_id(), status), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=pending-changes.csv"})


# ── Legacy bulk decisions (kept for compatibility; state-engine backed) ───────
@router.post("/decide")
def decide(payload: dict, user: str = Depends(require_editor)):
    """Set a reviewer action on an EXPLICIT scope — either specific row indices
    or all rows of a given classification. Now drives the state engine: UPDATE/
    ADD approve into staging, IGNORE keeps existing, MANUAL_REVIEW rejects into
    review. Illegal transitions are skipped and reported."""
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
    n, skipped = 0, []
    for r in _state["results"]:
        if not ((indices and r.index in idxset) or (status and r.classification.value == status)):
            continue
        try:
            if act == Action.UPDATE:
                _approve_one(r, "update", user)
            elif act == Action.ADD:
                _approve_one(r, "new", user)
            elif act == Action.IGNORE:
                if r.state != RecordState.EXISTING_OK:
                    _transition(r, RecordState.EXISTING_OK, user, "decide: keep existing")
                _unstage_if_staged(r, user, "decide: keep existing")
                r.action = Action.IGNORE
            elif act == Action.MANUAL_REVIEW:
                if r.state != RecordState.NEEDS_REVIEW:
                    _transition(r, RecordState.NEEDS_REVIEW, user, "decide: flag for review")
                r.action = Action.MANUAL_REVIEW
            n += 1
        except HTTPException as e:
            skipped.append({"index": r.index, "reason": e.detail})
    _save_session()
    _audit("decide", action=act.value, rows=n, skipped=len(skipped),
           indices=len(indices), status=status or None, actor=user)
    return {"updated": n, "action": act.value, "skipped": skipped}


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
                        "active": f.stem == (_state.get("session_id") or "")})
        except Exception:
            continue
    return {"sessions": out}


@router.post("/sessions/{sid}/activate")
def activate_session(sid: str, user: str = Depends(require_editor)):
    f = SESSIONS_DIR / f"{Path(sid).name}.json"
    if not f.exists():
        raise HTTPException(404, "Unknown session.")
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    _state.update(results=[], summary=None, filename=None, kind=None,
                  session_id=None, loaded_from_disk=False)
    _restore_session()
    if not _state.get("session_id"):
        _state["session_id"] = sid
    _audit("session_activate", session=sid, actor=user)
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


@router.get("/master-quality/export")
def master_quality_export():
    """De-duplication worksheet: every intra-master duplicate group as CSV, for
    a supervised clean-up pass by De Veres (2,813 groups at last count)."""
    import csv as _csv
    import io as _io
    from reconciliation import normalize as N
    eng = _get_engine()
    idx = eng.index
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["matched_on", "key", "count", "client_refs", "names", "emails", "phones"])
    for kind, index in (("email", idx.by_email), ("phone", idx.by_phone), ("name", idx.by_name)):
        for key, ids in sorted(index.items(), key=lambda kv: -len(kv[1])):
            if len(ids) < 2:
                continue
            recs = [eng.master.records[i] for i in ids]
            w.writerow([kind, key, len(ids),
                        "|".join(r.get("client_ref", "") for r in recs),
                        "|".join(f"{r.get('first_name','')} {r.get('last_name','')}".strip() for r in recs),
                        "|".join(r.get("email", "") for r in recs),
                        "|".join(r.get("phone", "") or r.get("mobile", "") for r in recs)])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=master-duplicates-worksheet.csv"})


# ── Odoo import — FROM STAGING ONLY (dry-run default; live writes env-gated) ─
@router.post("/odoo-import")
def odoo_import(payload: dict | None = None, user: str = Depends(require_editor)):
    """Push the STAGED (approved) changes to Odoo res.partner. The staging
    repository is the only payload — un-approved records can never reach Odoo.
    dry_run=true (default): plan + resolve only — NO writes. Live writes require
    dry_run=false AND RECON_ALLOW_ODOO_WRITE=1 on the server."""
    from reconciliation.odoo_import import OdooImporter, plan_from_staging
    _restore_session()
    repo = _get_staging()
    entries = repo.entries(_session_id(), status="ready")
    if not entries:
        raise HTTPException(404, "Staging is empty — approve records first. "
                                 "Only approved (staged) changes can be pushed.")
    payload = payload or {}
    dry_run = bool(payload.get("dry_run", True))
    cid = uuid.uuid4().hex[:12]
    log.info("odoo-import[%s]: %d staged entries, dry_run=%s, actor=%s",
             cid, len(entries), dry_run, user)
    ops = plan_from_staging(entries, source_file=_state.get("filename") or "")
    connected = bool(os.environ.get("ODOO_URL"))
    if not connected:
        result = {"summary": {"dry_run": True, "connected": False,
                              "create": sum(1 for o in ops if o.op == "create"),
                              "write": sum(1 for o in ops if o.op == "write"),
                              "skip": sum(1 for o in ops if o.op == "skip"),
                              "total": len(ops),
                              "id_checks_required": sum(1 for o in ops if o.id_check)},
                  "operations": [o.to_dict() for o in ops],
                  "note": "ODOO_URL not configured — returning the import plan only.",
                  "correlation_id": cid}
        _audit("odoo_import_plan", cid=cid, actor=user, **result["summary"])
        return result
    try:
        importer = OdooImporter()
        result = importer.execute(ops, dry_run=dry_run)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(502, f"Odoo connection failed: {e}")
    result["summary"]["connected"] = True
    if not dry_run:
        # Mark staged rows pushed + move records to the terminal state — but
        # ONLY for operations that actually succeeded (create/write) or had
        # nothing to write (skip). Errored ops stay 'ready' so a re-push
        # retries them (creates are idempotent by ref).
        by_index = {e["record_index"]: e for e in entries}
        op_by_ref: dict[str, dict] = {o["ref"]: o for o in result.get("operations", [])}
        for idx, entry in by_index.items():
            ref = entry["master_ref"] or f"BC-{entry['buyer_number']}"
            op = op_by_ref.get(ref) or {}
            if op.get("op") == "error" or str(op.get("reason", "")).startswith("VALIDATION"):
                log.warning("odoo import: ref=%s not pushed, staging row stays ready (%s)",
                            ref, op.get("reason"))
                continue
            partner = op.get("partner_id")
            repo.mark_pushed(_session_id(), idx, partner)
            r = next((x for x in _state["results"] if x.index == idx), None)
            if r is not None and r.state in STAGED_STATES:
                _transition(r, RecordState.PUSHED_TO_ODOO, user,
                            f"pushed (partner_id={partner})")
        _save_session()
    # summary already carries dry_run — passing it twice was a TypeError (500).
    result["correlation_id"] = cid
    _audit("odoo_import", cid=cid, actor=user, **result["summary"])
    log.info("odoo-import[%s]: done — %s", cid, result["summary"])
    return result


# ── Lots import preview (Hammer forced 0) ─────────────────────────────────────
@router.get("/lots")
def lots_preview(limit: int = 25):
    if not Path(LOTS_PATH).exists():
        raise HTTPException(404, "No lot list export available on the server.")
    lots = load_lots(LOTS_PATH)
    return {"total": len(lots), "hammer_rule": "forced to 0 on import",
            "lots": lots[:limit]}
