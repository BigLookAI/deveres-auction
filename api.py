"""
deVeres Auction — FastAPI Service v2
Port: 8003

Endpoints:
  POST /evaluate              — run full pipeline
  GET  /results               — list all evaluation results
  GET  /results/{id}          — single bidder detail
  POST /decision/{id}         — manual accept / reject override
  DELETE /decision/{id}       — clear override (revert to algo)
  GET  /reports/{id}          — Markdown report
  GET  /emails/{id}           — drafted email
  POST /compose-email         — store / schedule outreach email
  GET  /pending-emails        — list composed emails
  GET  /summary               — summary table Markdown
  GET  /health                — health check
  GET  /                      — HTML dashboard (SPA)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from pipeline.aggregator import evaluate_all
from pipeline.email_drafter import draft_all_emails
from pipeline.odoo_client import load_from_json
from pipeline.recommender import generate_all_reports, generate_summary_table
from pipeline.models import EvaluationResult, Recommendation
from pipeline.rationale import generate_rationale, build_source_table
from pipeline.aggregator import build_artist_index, get_bidder_artists

# ── Config ─────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent
DATA_DIR        = BASE_DIR / "data"
OUTPUT_DIR      = BASE_DIR / "output"
REPORTS_DIR     = OUTPUT_DIR / "reports"
LOTS_PATH       = DATA_DIR / "sample_upcoming_lots.json"
BIDDERS_PATH    = DATA_DIR / "sample_bidding_history.json"
PAST_LOTS_PATH  = DATA_DIR / "sample_past_lots.json"
GEMMA4_URL      = os.environ.get("GEMMA4_URL", "http://localhost:8000/generate")

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "deVeres Auction — Bidder Evaluation API",
    description = "Deterministic bidder scoring pipeline for deVeres Auction, by Cimelium",
    version     = "2.0.0",
)

# In-memory state
_results_cache:      list[EvaluationResult] = []
_emails_cache:       list[dict]             = []
_decision_overrides: dict[str, str]         = {}   # bidder_id -> "approve"|"reject"|"review"
_composed_emails:    list[dict]             = []   # sent / scheduled emails
_past_lots_cache:    list                   = []   # raw Lot objects from last evaluate
_profiles_cache:     list                   = []   # raw BidderProfile objects
_lots_by_id_cache:   dict                   = {}   # lot_id -> Lot


# ── Pydantic models ────────────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    use_odoo:       bool           = False
    dry_run:        bool           = True
    lots_path:      Optional[str]  = None
    bidders_path:   Optional[str]  = None
    past_lots_path: Optional[str]  = None
    weights:        Optional[dict] = None   # operator-configurable dimension weights (normalised client-side)

class BidderSummary(BaseModel):
    bidder_id:       str
    bidder_name:     str
    bidder_email:    str
    score:           float
    recommendation:  str
    manual_decision: Optional[str] = None
    total_bids:      int
    total_wins:      int
    trajectory:      str
    matched_lots:    int

class EvaluateResponse(BaseModel):
    total:           int
    approved:        int
    reviewed:        int
    rejected:        int
    reports_written: int
    emails_drafted:  int
    results:         list[BidderSummary]

class DecisionRequest(BaseModel):
    decision: str  # "approve" | "reject" | "review"

class ComposeEmailRequest(BaseModel):
    to:          str
    cc:          str           = ""
    subject:     str
    body:        str
    schedule_at: Optional[str] = None   # ISO datetime


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":             "ok",
        "service":            "deveres-auction",
        "version":            "2.0.0",
        "port":               8003,
        "results_cached":     len(_results_cache),
        "decision_overrides": len(_decision_overrides),
        "emails_queued":      len(_composed_emails),
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest):
    global _results_cache, _emails_cache, _past_lots_cache, _profiles_cache, _lots_by_id_cache

    lots_path      = req.lots_path      or str(LOTS_PATH)
    bidders_path   = req.bidders_path   or str(BIDDERS_PATH)
    past_lots_path = req.past_lots_path or (str(PAST_LOTS_PATH) if PAST_LOTS_PATH.exists() else None)

    if req.use_odoo:
        from pipeline.odoo_client import OdooClient
        client     = OdooClient()
        lots       = client.fetch_upcoming_lots()
        profiles   = client.fetch_bidder_profiles()
        past_lots  = []
    else:
        lots, profiles, past_lots = load_from_json(lots_path, bidders_path, past_lots_path)

    # Sanitise operator-supplied weights to the known dimensions (ignore junk keys).
    _valid_dims = {"win_loss_rate", "bid_count", "reserve_ratio",
                   "repeat_buyer", "price_band_trajectory", "hammer_influence"}
    _weights = None
    if req.weights:
        _weights = {k: float(v) for k, v in req.weights.items()
                    if k in _valid_dims and isinstance(v, (int, float))}
        if not _weights or sum(_weights.values()) <= 0:
            _weights = None

    results = evaluate_all(profiles, lots, weights=_weights,
                           past_lots=past_lots if past_lots else None)

    # ── Build caches for rationale generation ──────────────────────────
    _past_lots_cache[:] = past_lots or []
    _profiles_cache[:] = profiles
    _lots_by_id_cache.clear()
    _artist_index = build_artist_index(past_lots or [])
    for _lot in lots:
        _lots_by_id_cache[_lot.lot_id] = _lot
    for _pl in (past_lots or []):
        _lots_by_id_cache[_pl.lot_id] = _pl

    # ── Generate NLP rationale for each result ──────────────────────
    for _result in results:
        _profile = next((p for p in profiles if p.bidder_id == _result.bidder_id), None)
        if _profile:
            _bidder_artists = get_bidder_artists(_profile.bids, _artist_index)
            _all_artist_bids = [b for bids_list in _bidder_artists.values() for b in bids_list]
        else:
            _all_artist_bids = []
        _result.rationale   = generate_rationale(_result, _all_artist_bids, gemma4_url=GEMMA4_URL)
        _result.source_bids = build_source_table(_result, _all_artist_bids, _lots_by_id_cache)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_all_reports(results, REPORTS_DIR)

    summary_md = generate_summary_table(results)
    (OUTPUT_DIR / "summary.md").write_text(summary_md, encoding="utf-8")

    emails = draft_all_emails(results, vllm_url=GEMMA4_URL, dry_run=req.dry_run)
    (OUTPUT_DIR / "emails.json").write_text(
        json.dumps(emails, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    _results_cache = results
    _emails_cache  = emails

    approved = sum(1 for r in results if r.recommendation == Recommendation.APPROVE)
    reviewed = sum(1 for r in results if r.recommendation == Recommendation.REVIEW)
    rejected = sum(1 for r in results if r.recommendation == Recommendation.REJECT)
    drafted  = sum(1 for e in emails if e.get("status") in ("drafted", "dry_run"))

    return EvaluateResponse(
        total           = len(results),
        approved        = approved,
        reviewed        = reviewed,
        rejected        = rejected,
        reports_written = len(results),
        emails_drafted  = drafted,
        results         = [_to_summary(r) for r in results],
    )


@app.get("/results", response_model=list[BidderSummary])
def list_results():
    if not _results_cache:
        raise HTTPException(404, "No results yet — call POST /evaluate first")
    return [_to_summary(r) for r in _results_cache]


@app.get("/results/{bidder_id}")
def get_result(bidder_id: str):
    result = _find_result(bidder_id)
    b = result.breakdown
    return {
        "bidder_id":       result.bidder_id,
        "bidder_name":     result.bidder_name,
        "bidder_email":    result.bidder_email,
        "score":           result.score,
        "recommendation":  result.recommendation.value,
        "manual_decision": _decision_overrides.get(result.bidder_id),
        "evaluated_at":    result.evaluated_at,
        "breakdown": {
            "win_loss_rate":         b.win_loss_rate,
            "bid_count":             b.bid_count,
            "reserve_ratio":         b.reserve_ratio,
            "repeat_buyer":          b.repeat_buyer,
            "price_band_trajectory": b.price_band_trajectory,
            "hammer_influence":      b.hammer_influence,
            "total_bids":            b.total_bids,
            "total_wins":            b.total_wins,
            "bids_above_reserve":    b.bids_above_reserve,
            "distinct_lots_won":     b.distinct_lots_won,
            "trajectory":            b.trajectory.value,
            "insufficient_history":  b.insufficient_history,
        },
        "matched_lots": [
            {
                "lot_id":        ml.lot_id,
                "title":         ml.title,
                "artist":        ml.artist,
                "category":      ml.category,
                "estimate_low":  ml.estimate_low,
                "estimate_high": ml.estimate_high,
                "auction_date":  ml.auction_date,
                "match_reason":  ml.match_reason,
            }
            for ml in result.matched_lots
        ],
        "per_lot_scores": [
            {
                "lot_id":        ls.lot_id,
                "title":         ls.title,
                "artist":        ls.artist,
                "category":      ls.category,
                "estimate_low":  ls.estimate_low,
                "estimate_high": ls.estimate_high,
                "auction_date":  ls.auction_date,
                "score":         ls.score,
                "artist_bids":   ls.artist_bids,
                "breakdown": {
                    "win_loss_rate":         ls.breakdown.win_loss_rate,
                    "bid_count":             ls.breakdown.bid_count,
                    "reserve_ratio":         ls.breakdown.reserve_ratio,
                    "repeat_buyer":          ls.breakdown.repeat_buyer,
                    "price_band_trajectory": ls.breakdown.price_band_trajectory,
                    "hammer_influence":      ls.breakdown.hammer_influence,
                    "total_bids":            ls.breakdown.total_bids,
                    "total_wins":            ls.breakdown.total_wins,
                    "trajectory":            ls.breakdown.trajectory.value,
                },
            }
            for ls in result.per_lot_scores
        ],
        "rejection_reasons": result.rejection_reasons,
    }


@app.post("/decision/{bidder_id}")
def update_decision(bidder_id: str, req: DecisionRequest):
    """Manually override algorithmic recommendation."""
    if req.decision not in ("approve", "reject", "review"):
        raise HTTPException(400, f"Invalid decision '{req.decision}'")
    _find_result(bidder_id)
    _decision_overrides[bidder_id] = req.decision
    return {"ok": True, "bidder_id": bidder_id, "decision": req.decision}


@app.delete("/decision/{bidder_id}")
def clear_decision(bidder_id: str):
    """Revert bidder to algorithmic recommendation."""
    _decision_overrides.pop(bidder_id, None)
    return {"ok": True, "bidder_id": bidder_id}


@app.get("/reports/{bidder_id}", response_class=PlainTextResponse)
def get_report(bidder_id: str):
    path = REPORTS_DIR / f"report_{bidder_id.lower().replace('/', '-')}.md"
    if not path.exists():
        result = _find_result(bidder_id)
        from pipeline.recommender import generate_markdown_report
        return generate_markdown_report(result)
    return path.read_text(encoding="utf-8")


@app.get("/emails/{bidder_id}")
def get_email(bidder_id: str):
    if not _emails_cache:
        raise HTTPException(404, "No emails yet — call POST /evaluate first")
    email = next((e for e in _emails_cache if e.get("bidder_id") == bidder_id), None)
    if not email:
        raise HTTPException(404, f"No email for bidder {bidder_id}")
    return email


@app.post("/compose-email")
def compose_email_route(req: ComposeEmailRequest):
    """Log a composed outreach email (sent now or scheduled)."""
    entry = {
        "id":          f"mail_{len(_composed_emails)+1:04d}",
        "to":          req.to,
        "cc":          req.cc,
        "subject":     req.subject,
        "body":        req.body,
        "schedule_at": req.schedule_at,
        "sent_at":     None if req.schedule_at else datetime.now(timezone.utc).isoformat(),
        "status":      "scheduled" if req.schedule_at else "sent",
        "created_at":  datetime.now(timezone.utc).isoformat(),
    }
    _composed_emails.append(entry)
    return {"ok": True, "email_id": entry["id"], "status": entry["status"]}


@app.get("/pending-emails")
def get_pending_emails():
    return _composed_emails


@app.get("/summary", response_class=PlainTextResponse)
def get_summary():
    path = OUTPUT_DIR / "summary.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    if not _results_cache:
        raise HTTPException(404, "No results yet — call POST /evaluate first")
    return generate_summary_table(_results_cache)


@app.get("/rationale/{bidder_id}")
def get_rationale(bidder_id: str):
    """Return the NLP rationale text for a bidder (Layer 2)."""
    result = _find_result(bidder_id)
    return {
        "bidder_id": bidder_id,
        "bidder_name": result.bidder_name,
        "rationale": result.rationale or "(Run /evaluate to generate rationales)",
    }


@app.get("/sources/{bidder_id}")
def get_sources(bidder_id: str):
    """Return the expandable source data table for a bidder (Layer 3)."""
    result = _find_result(bidder_id)
    return {
        "bidder_id": bidder_id,
        "bidder_name": result.bidder_name,
        "sources": result.source_bids,
    }


@app.get("/", response_class=HTMLResponse)
def results_viewer():
    return HTMLResponse(_build_html_viewer())


# ── Helpers ────────────────────────────────────────────────────────────────

def _to_summary(r: EvaluationResult) -> BidderSummary:
    return BidderSummary(
        bidder_id       = r.bidder_id,
        bidder_name     = r.bidder_name,
        bidder_email    = r.bidder_email,
        score           = r.score,
        recommendation  = r.recommendation.value,
        manual_decision = _decision_overrides.get(r.bidder_id),
        total_bids      = r.breakdown.total_bids,
        total_wins      = r.breakdown.total_wins,
        trajectory      = r.breakdown.trajectory.value,
        matched_lots    = len(r.matched_lots),
    )


def _find_result(bidder_id: str) -> EvaluationResult:
    if not _results_cache:
        raise HTTPException(404, "No results yet — call POST /evaluate first")
    r = next((x for x in _results_cache if x.bidder_id == bidder_id), None)
    if not r:
        raise HTTPException(404, f"Bidder {bidder_id!r} not found")
    return r


# ── HTML SPA ───────────────────────────────────────────────────────────────

def _build_html_viewer() -> str:
    # Inject server-side data as JSON so JS can use it without escaping hell
    if _results_cache:
        _stats = {
            "approved":  sum(1 for r in _results_cache if r.recommendation.value == "approve"),
            "reviewed":  sum(1 for r in _results_cache if r.recommendation.value == "review"),
            "rejected":  sum(1 for r in _results_cache if r.recommendation.value == "reject"),
            "total":     len(_results_cache),
            "top_score": round(max(r.score for r in _results_cache), 4),
            "last_run":  _results_cache[0].evaluated_at[:16].replace("T", " ") + " UTC",
        }
        _bidders = [
            {
                "id":    r.bidder_id,
                "name":  r.bidder_name,
                "email": r.bidder_email,
                "score": round(r.score, 4),
                "rec":   r.recommendation.value,
                "manual": _decision_overrides.get(r.bidder_id),
                "bids":  r.breakdown.total_bids,
                "wins":  r.breakdown.total_wins,
                "traj":  r.breakdown.trajectory.value,
                "lots":  len(r.matched_lots),
            }
            for r in _results_cache
        ]
        stats_json   = json.dumps(_stats)
        bidders_json = json.dumps(_bidders)
    else:
        stats_json   = "null"
        bidders_json = "[]"

    overrides_json = json.dumps(_decision_overrides)

    # ── CSS (plain string — no f-string escaping needed) ──────────────────
    CSS = """
:root {
  --bg:      #080b18;
  --s1:      #0c0f1f;
  --s2:      #111428;
  --s3:      #171b30;
  --s4:      #1d2238;
  --border:  #1f2540;
  --border2: #272d4a;
  --text:    #dde3f5;
  --muted:   #5a6485;
  --muted2:  #7880a8;
  --accent:  #6366f1;
  --acch:    #818cf8;
  --green:   #22c55e;
  --yellow:  #eab308;
  --red:     #ef4444;
  --blue:    #3b82f6;
  --radius:  10px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', -apple-system, system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.55;
  min-height: 100vh;
}

/* ── Login ── */
#login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse 80% 60% at 50% 0%, rgba(99,102,241,.18) 0%, transparent 70%), var(--bg);
}
.login-card {
  background: var(--s1);
  border: 1px solid var(--border2);
  border-radius: 16px;
  padding: 44px 40px 36px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 24px 80px rgba(0,0,0,.5);
}
.login-logo {
  width: 52px; height: 52px;
  background: linear-gradient(135deg, #6366f1, #a78bfa);
  border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 900; color: #fff;
  margin: 0 auto 20px;
}
.login-card h1 { font-size: 22px; font-weight: 800; text-align: center; }
.login-card .login-sub {
  color: var(--muted2); font-size: 13px; text-align: center; margin: 6px 0 28px;
}
.role-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 24px;
}
.role-btn {
  padding: 12px; border-radius: 9px;
  background: var(--s3); border: 2px solid var(--border2);
  color: var(--muted2); cursor: pointer; font-size: 13px; font-weight: 600;
  transition: all .15s; text-align: center;
}
.role-btn:hover { border-color: var(--accent); color: var(--text); }
.role-btn.selected { border-color: var(--accent); background: rgba(99,102,241,.12); color: var(--acch); }
.role-btn .role-icon { font-size: 20px; display: block; margin-bottom: 4px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--muted2); margin-bottom: 5px; font-weight: 500; }
.form-group input, .form-group textarea, .form-group select {
  width: 100%; background: var(--s3);
  border: 1px solid var(--border2); border-radius: 8px;
  padding: 10px 13px; color: var(--text); font-size: 13px;
  transition: border-color .15s;
}
.form-group input:focus, .form-group textarea:focus {
  outline: none; border-color: var(--accent);
}
.login-error {
  color: var(--red); font-size: 12px; margin-bottom: 12px;
  min-height: 16px; text-align: center;
}
.login-hint {
  color: var(--muted); font-size: 11px; text-align: center;
  margin-top: 20px; line-height: 1.7;
  background: var(--s3); border-radius: 7px; padding: 9px 12px;
}
.login-hint code { color: var(--muted2); font-family: monospace; }

/* ── App shell ── */
#app { display: none; }
.header {
  background: var(--s1);
  border-bottom: 1px solid var(--border);
  padding: 0 28px;
  height: 56px;
  display: flex; align-items: center;
  gap: 20px;
  position: sticky; top: 0; z-index: 200;
}
.h-logo {
  width: 32px; height: 32px;
  background: linear-gradient(135deg, #6366f1, #a78bfa);
  border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 900; color: #fff;
}
.h-brand { line-height: 1.2; }
.h-brand-name { font-size: 14px; font-weight: 700; }
.h-brand-sub  { font-size: 10px; color: var(--muted); }
.tab-nav { display: flex; gap: 2px; margin-left: 24px; }
.tab-btn {
  padding: 7px 14px; border-radius: 7px;
  background: transparent; border: none;
  color: var(--muted2); font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all .15s; white-space: nowrap;
}
.tab-btn:hover { background: var(--s3); color: var(--text); }
.tab-btn.active { background: rgba(99,102,241,.15); color: var(--acch); font-weight: 600; }
.h-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.user-chip {
  display: flex; align-items: center; gap: 7px;
  background: var(--s3); border: 1px solid var(--border2);
  border-radius: 999px; padding: 4px 12px 4px 6px;
}
.user-avatar {
  width: 24px; height: 24px; border-radius: 50%;
  background: var(--accent); display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: 700; color: #fff;
}
.user-name { font-size: 12px; font-weight: 600; }
.role-chip {
  font-size: 10px; padding: 1px 6px; border-radius: 999px;
  font-weight: 700; text-transform: uppercase; letter-spacing: .4px;
}
.role-admin  { background: rgba(99,102,241,.2);  color: var(--acch); }
.role-viewer { background: rgba(59,130,246,.2); color: var(--blue); }
.btn-logout {
  background: transparent; border: 1px solid var(--border2);
  color: var(--muted2); border-radius: 7px; padding: 5px 12px;
  font-size: 12px; cursor: pointer; transition: all .15s;
}
.btn-logout:hover { border-color: var(--red); color: var(--red); }

/* ── Main content ── */
.main { padding: 28px 28px 60px; max-width: 1340px; margin: 0 auto; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* ── Scoring weights panel ── */
.weights-panel { background:#161a22; border:1px solid #232833; border-radius:12px; padding:14px 16px; margin:0 0 18px; }
.weights-panel .wp-title { font-size:13px; font-weight:700; margin-bottom:10px; }
.weights-panel .wp-sub { font-weight:400; color:#8b93a7; font-size:12px; }
.weights-panel .wp-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px 16px; }
.weights-panel label { display:flex; flex-direction:column; font-size:11px; color:#8b93a7; gap:4px; }
.weights-panel input { background:#0f131a; border:1px solid #232833; border-radius:7px; padding:6px 8px; color:#fff; font-size:13px; width:100%; }
.weights-panel .wp-actions { display:flex; justify-content:space-between; align-items:center; margin-top:12px; }
.weights-panel .wp-sum { font-size:12px; color:#8b93a7; }
@media (max-width:700px){ .weights-panel .wp-grid { grid-template-columns:1fr 1fr; } }

/* ── Toolbar ── */
.toolbar {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 24px; flex-wrap: wrap;
}
.last-run { margin-left: auto; font-size: 12px; color: var(--muted); }

/* ── Buttons ── */
.btn-primary {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--accent); color: #fff; border: none;
  border-radius: 8px; padding: 9px 18px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  transition: background .15s;
}
.btn-primary:hover:not(:disabled) { background: var(--acch); }
.btn-primary:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary {
  display: inline-flex; align-items: center; gap: 6px;
  background: transparent; color: var(--muted2);
  border: 1px solid var(--border2); border-radius: 8px;
  padding: 8px 14px; font-size: 13px; cursor: pointer;
  transition: all .15s;
}
.btn-secondary:hover { background: var(--s3); color: var(--text); }
.btn-sm {
  padding: 4px 10px; font-size: 11px; border-radius: 6px;
  font-weight: 600; cursor: pointer; border: none; transition: all .15s;
}
.btn-accept { background: rgba(34,197,94,.15);  color: var(--green); }
.btn-accept:hover { background: rgba(34,197,94,.28); }
.btn-reject { background: rgba(239,68,68,.15);  color: var(--red); }
.btn-reject:hover { background: rgba(239,68,68,.28); }
.btn-email  { background: rgba(99,102,241,.15); color: var(--acch); }
.btn-email:hover  { background: rgba(99,102,241,.28); }
.btn-detail { background: var(--s4); color: var(--muted2); border: 1px solid var(--border2); }
.btn-detail:hover { color: var(--text); }

/* ── Toast ── */
.toast {
  display: none; align-items: center; gap: 8px;
  padding: 8px 14px; border-radius: 8px; font-size: 13px;
  border: 1px solid transparent;
}
.toast.show      { display: inline-flex; }
.toast.t-success { background: rgba(34,197,94,.12);  border-color: rgba(34,197,94,.3);  color: var(--green); }
.toast.t-error   { background: rgba(239,68,68,.12);  border-color: rgba(239,68,68,.3);  color: var(--red); }
.toast.t-info    { background: rgba(99,102,241,.12); border-color: rgba(99,102,241,.3); color: var(--acch); }

/* ── Stats grid ── */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px; margin-bottom: 24px;
}
.stat-card {
  background: var(--s1); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px 22px;
}
.stat-num { font-size: 36px; font-weight: 800; line-height: 1; }
.stat-lbl { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .6px; margin-top: 6px; }
.c-green  { color: var(--green); }
.c-yellow { color: var(--yellow); }
.c-red    { color: var(--red); }
.c-accent { color: var(--acch); }
.c-blue   { color: var(--blue); }

/* ── Bidder table ── */
.table-card {
  background: var(--s1); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
.rtable { width: 100%; border-collapse: collapse; }
.rtable thead th {
  background: var(--s2); padding: 11px 16px;
  text-align: left; font-size: 11px;
  color: var(--muted); text-transform: uppercase; letter-spacing: .6px;
  border-bottom: 1px solid var(--border); white-space: nowrap;
}
.rtable tbody td { padding: 14px 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.rtable tbody tr:last-child td { border-bottom: none; }
.rtable tbody tr { cursor: pointer; transition: background .1s; }
.rtable tbody tr:hover td { background: rgba(99,102,241,.04); }
.rtable tbody tr.row-active td { background: rgba(99,102,241,.09); }
.td-r { text-align: right; }
.td-c { text-align: center; }
.bidder-name  { font-weight: 600; font-size: 14px; }
.bidder-email { font-size: 12px; color: var(--muted2); margin-top: 2px; }
.score-col { display: flex; align-items: center; gap: 9px; }
.score-bar  { flex: 0 0 80px; height: 5px; background: var(--s4); border-radius: 3px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 3px; }
.score-val  { font-size: 13px; font-weight: 700; min-width: 34px; }
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 9px; border-radius: 999px;
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px;
}
.b-approve { background: rgba(34,197,94,.12);  color: var(--green); }
.b-review  { background: rgba(234,179,8,.12);  color: var(--yellow); }
.b-reject  { background: rgba(239,68,68,.12);  color: var(--red); }
.b-manual  {
  background: rgba(59,130,246,.12); color: var(--blue);
  font-size: 9px; padding: 2px 6px;
}
.traj-up   { color: var(--green); }
.traj-down { color: var(--red); }
.actions-col { display: flex; gap: 5px; align-items: center; flex-wrap: nowrap; }

/* ── Detail drawer ── */
.drawer-overlay {
  display: none;
  position: fixed; inset: 0; z-index: 300;
  background: rgba(0,0,0,.5);
  backdrop-filter: blur(2px);
}
.drawer-overlay.open { display: block; }
.drawer {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: 520px; max-width: 95vw;
  background: var(--s1); border-left: 1px solid var(--border2);
  overflow-y: auto;
  transform: translateX(100%);
  transition: transform .25s cubic-bezier(.4,0,.2,1);
  display: flex; flex-direction: column;
}
.drawer-overlay.open .drawer { transform: translateX(0); }
.drawer-head {
  padding: 20px 22px 18px;
  border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: flex-start;
  position: sticky; top: 0; background: var(--s1); z-index: 1;
}
.drawer-head-left h3 { font-size: 16px; font-weight: 700; }
.drawer-head-left .d-meta { font-size: 12px; color: var(--muted2); margin-top: 5px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.close-btn {
  width: 30px; height: 30px; border-radius: 7px;
  background: var(--s3); border: 1px solid var(--border2);
  color: var(--muted2); cursor: pointer; font-size: 17px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.close-btn:hover { color: var(--text); background: var(--s4); }
.drawer-body { padding: 20px 22px; flex: 1; }
.d-section { margin-bottom: 22px; }
.d-section-title {
  font-size: 10px; color: var(--muted); text-transform: uppercase;
  letter-spacing: .7px; font-weight: 700; margin-bottom: 10px;
}
.dim-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
}
.dim-card {
  background: var(--s2); border: 1px solid var(--border);
  border-radius: 9px; padding: 13px 14px;
}
.dim-label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: .4px; }
.dim-value { font-size: 22px; font-weight: 800; margin-top: 3px; }
.dim-bar   { height: 3px; background: var(--s4); border-radius: 2px; margin-top: 6px; overflow: hidden; }
.dim-fill  { height: 100%; border-radius: 2px; }
.lot-grid  { display: grid; gap: 8px; }
.lot-card  {
  background: var(--s2); border: 1px solid var(--border);
  border-radius: 9px; padding: 12px 14px;
}
.lot-title { font-weight: 600; font-size: 13px; }
.lot-meta  { font-size: 12px; color: var(--muted2); margin-top: 3px; }
.lot-price { color: var(--acch); font-weight: 600; }
.rationale-text {
  font-size: 13px;
  line-height: 1.65;
  color: var(--text);
  padding: 12px 14px;
  background: var(--s2);
  border-radius: 8px;
  border-left: 3px solid var(--accent);
}
.sources-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.sources-table th {
  text-align: left;
  padding: 5px 8px;
  color: var(--muted2);
  border-bottom: 1px solid var(--border2);
  font-weight: 600;
  white-space: nowrap;
}
.sources-table td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.outcome-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}
.outcome-won  { background: rgba(34,197,94,.15); color: var(--green); }
.outcome-lost { background: rgba(239,68,68,.12);  color: var(--red); }
.flag-item { color: var(--red); font-size: 12px; margin: 5px 0; }
.breakdown-row {
  display: flex; justify-content: space-between;
  padding: 7px 0; border-bottom: 1px solid var(--border); font-size: 13px;
}
.breakdown-row:last-child { border-bottom: none; }
.breakdown-label { color: var(--muted2); }
.breakdown-val   { font-weight: 600; }
.drawer-footer {
  padding: 16px 22px; border-top: 1px solid var(--border);
  display: flex; gap: 8px; background: var(--s1);
  position: sticky; bottom: 0;
}

/* ── Email modal ── */
.modal-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,.65); backdrop-filter: blur(3px);
  z-index: 400; align-items: center; justify-content: center;
}
.modal-overlay.open { display: flex; }
.modal-box {
  background: var(--s1); border: 1px solid var(--border2);
  border-radius: 14px; width: 640px; max-width: 95vw; max-height: 92vh;
  display: flex; flex-direction: column;
  box-shadow: 0 32px 100px rgba(0,0,0,.6);
  animation: modal-in .2s ease;
}
@keyframes modal-in {
  from { opacity: 0; transform: scale(.96) translateY(8px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}
.modal-head {
  padding: 20px 22px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.modal-head h3 { font-size: 16px; font-weight: 700; }
.modal-body { padding: 20px 22px; overflow-y: auto; flex: 1; }
.modal-footer {
  padding: 16px 22px; border-top: 1px solid var(--border);
  display: flex; gap: 8px; justify-content: flex-end;
}
.form-group textarea {
  resize: vertical; min-height: 180px; font-family: inherit;
}
.send-opts { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
.radio-label {
  display: flex; align-items: center; gap: 6px;
  cursor: pointer; font-size: 13px; color: var(--text);
}
.radio-label input[type=radio] { accent-color: var(--accent); width: 15px; height: 15px; }
#schedule-dt {
  background: var(--s3); border: 1px solid var(--border2);
  border-radius: 8px; padding: 8px 11px;
  color: var(--text); font-size: 13px;
  display: none;
}
#schedule-dt.show { display: inline-block; }

/* ── Summary tab ── */
.panel-hd { margin-bottom: 22px; }
.panel-hd h2 { font-size: 18px; font-weight: 700; }
.panel-hd p  { color: var(--muted2); font-size: 13px; margin-top: 4px; }
.summary-table-wrap {
  background: var(--s1); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
.summary-table-wrap table { width: 100%; border-collapse: collapse; }
.summary-table-wrap th {
  background: var(--s2); padding: 11px 16px; text-align: left;
  font-size: 11px; color: var(--muted); text-transform: uppercase;
  letter-spacing: .6px; border-bottom: 1px solid var(--border);
}
.summary-table-wrap td {
  padding: 13px 16px; border-bottom: 1px solid var(--border); font-size: 13px;
}
.summary-table-wrap tr:last-child td { border-bottom: none; }

/* ── API Reference tab ── */
.api-grid { display: grid; gap: 12px; }
.api-card {
  background: var(--s1); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
.api-card-head {
  padding: 14px 18px; display: flex; align-items: center; gap: 12px;
  border-bottom: 1px solid var(--border);
}
.method {
  font-size: 11px; font-weight: 800; padding: 3px 8px;
  border-radius: 5px; letter-spacing: .5px; min-width: 52px; text-align: center;
}
.m-get    { background: rgba(34,197,94,.15);  color: var(--green); }
.m-post   { background: rgba(99,102,241,.15); color: var(--acch); }
.m-delete { background: rgba(239,68,68,.15);  color: var(--red); }
.api-path { font-family: monospace; font-size: 14px; font-weight: 600; }
.api-desc { color: var(--muted2); font-size: 13px; margin-left: auto; }
.api-body { padding: 14px 18px; }
.api-body pre {
  background: var(--s2); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 14px;
  font-size: 12px; overflow-x: auto; color: var(--text);
  line-height: 1.6;
}

/* ── Health tab ── */
.health-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px; margin-bottom: 22px;
}
.health-card {
  background: var(--s1); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px 22px;
}
.health-status { display: flex; align-items: center; gap: 8px; }
.status-dot {
  width: 10px; height: 10px; border-radius: 50%;
}
.dot-ok  { background: var(--green); box-shadow: 0 0 6px var(--green); }
.dot-err { background: var(--red);   box-shadow: 0 0 6px var(--red); }
.health-val  { font-size: 20px; font-weight: 800; margin-top: 6px; }
.health-lbl  { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .6px; margin-top: 4px; }

/* ── Empty state ── */
.empty-state {
  background: var(--s1); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 64px 32px; text-align: center;
}
.empty-icon { font-size: 44px; margin-bottom: 14px; }
.empty-state h3 { font-size: 18px; margin-bottom: 8px; }
.empty-state p  { color: var(--muted2); max-width: 440px; margin: 0 auto 6px; }
.empty-state pre {
  background: var(--s2); border: 1px solid var(--border);
  border-radius: 8px; padding: 14px 18px;
  font-size: 12px; text-align: left; display: inline-block;
  margin-top: 14px; color: var(--text); max-width: 100%; overflow: auto;
}

/* ── Spinner ── */
@keyframes spin { to { transform: rotate(360deg); } }
.spinner {
  width: 15px; height: 15px;
  border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%;
  animation: spin .7s linear infinite; flex-shrink: 0;
}
"""

    # ── JavaScript (plain string — no f-string escaping needed) ──────────
    JS = r"""
// ── Credentials ──────────────────────────────────────────────────────────
const CREDS = {
  'admin@deveres.ie':  { pass: 'Admin2026!', role: 'admin',  name: 'Admin' },
  'viewer@deveres.ie': { pass: 'View2026',   role: 'viewer', name: 'Viewer' },
};

let currentUser = null;
let currentRole = null;
let selectedRole = 'admin';
let activeDrawerId = null;
let emailTargetId = null;

// ── Login ─────────────────────────────────────────────────────────────────
function selectRole(r) {
  selectedRole = r;
  document.getElementById('role-admin').classList.toggle('selected', r === 'admin');
  document.getElementById('role-viewer').classList.toggle('selected', r === 'viewer');
}

function doLogin(e) {
  e.preventDefault();
  const email = document.getElementById('l-email').value.trim().toLowerCase();
  const pass  = document.getElementById('l-pass').value;
  const err   = document.getElementById('l-error');
  const cred  = CREDS[email];
  if (!cred || cred.pass !== pass || cred.role !== selectedRole) {
    err.textContent = 'Invalid credentials or role. Please try again.';
    return;
  }
  currentUser = email;
  currentRole = cred.role;
  sessionStorage.setItem('da_user', JSON.stringify({ email, role: currentRole, name: cred.name }));
  bootApp();
}

function logout() {
  sessionStorage.removeItem('da_user');
  currentUser = null; currentRole = null;
  document.getElementById('app').style.display = 'none';
  document.getElementById('login-page').style.display = 'flex';
}

function bootApp() {
  document.getElementById('login-page').style.display = 'none';
  document.getElementById('app').style.display = 'block';

  // User chip
  const initials = currentUser[0].toUpperCase();
  document.getElementById('user-avatar').textContent = initials;
  document.getElementById('user-name').textContent = CREDS[currentUser].name;
  document.getElementById('role-chip').textContent = currentRole;
  document.getElementById('role-chip').className = 'role-chip role-' + currentRole;

  // Admin-only elements
  document.querySelectorAll('.admin-only').forEach(el => {
    el.style.display = currentRole === 'admin' ? '' : 'none';
  });

  showTab('bidders');
}

// ── Tab management ────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelector(`.tab-btn[data-tab="${name}"]`).classList.add('active');
  closeDetail();
  if (name === 'bidders') { renderBidders(); }
  if (name === 'summary') { loadSummary(); }
  if (name === 'health')  { loadHealth(); }
  if (name === 'apidocs') { /* static, already rendered */ }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Bidders tab ───────────────────────────────────────────────────────────
function renderBidders() {
  const stats   = INITIAL_STATS;
  const bidders = INITIAL_BIDDERS;

  if (stats) {
    document.getElementById('last-run').textContent = 'Last run: ' + stats.last_run;
    document.getElementById('stats-grid').innerHTML = `
      <div class="stat-card"><div class="stat-num c-green">${stats.approved}</div><div class="stat-lbl">Approved</div></div>
      <div class="stat-card"><div class="stat-num c-yellow">${stats.reviewed}</div><div class="stat-lbl">For Review</div></div>
      <div class="stat-card"><div class="stat-num c-red">${stats.rejected}</div><div class="stat-lbl">Rejected</div></div>
      <div class="stat-card"><div class="stat-num">${stats.total}</div><div class="stat-lbl">Total Bidders</div></div>
      <div class="stat-card"><div class="stat-num c-accent">${stats.top_score.toFixed(2)}</div><div class="stat-lbl">Top Score</div></div>
    `;
  } else {
    document.getElementById('stats-grid').innerHTML = '';
    document.getElementById('last-run').textContent = '';
  }

  if (!bidders || bidders.length === 0) {
    document.getElementById('bidders-content').innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📊</div>
        <h3>No evaluation results yet</h3>
        <p>Click <strong>Run Evaluation</strong> above to score all bidders against upcoming lots.</p>
        <p style="font-size:12px;margin-top:14px;color:var(--muted)">Or via the API:</p>
        <pre>curl -X POST http://localhost:8003/evaluate \\
  -H "Content-Type: application/json" \\
  -d '{"dry_run": true}'</pre>
      </div>`;
    return;
  }

  const rows = bidders.map(b => {
    const overrides = DECISION_OVERRIDES;
    const manual  = overrides[b.id] || b.manual;
    const display = manual || b.rec;
    const bcls    = { approve: 'b-approve', review: 'b-review', reject: 'b-reject' }[display] || '';
    const barClr  = display === 'approve' ? 'var(--green)' : display === 'review' ? 'var(--yellow)' : 'var(--red)';
    const barPct  = Math.round(b.score * 100);
    const trajCls = b.traj === 'up' ? 'traj-up' : b.traj === 'down' ? 'traj-down' : '';
    const trajIcon= { up: '↑', down: '↓', stable: '→', eclectic: '⟳', unknown: '?' }[b.traj] || '';
    const manualBadge = manual ? ' <span class="badge b-manual">Manual</span>' : '';
    const adminBtns = currentRole === 'admin' ? `
      <button class="btn-sm btn-accept" onclick="updateDecision(event,'${b.id}','approve')" title="Accept">✓ Accept</button>
      <button class="btn-sm btn-reject" onclick="updateDecision(event,'${b.id}','reject')" title="Reject">✗ Reject</button>
      <button class="btn-sm btn-email"  onclick="openEmail(event,'${b.id}')" title="Compose email">✉ Email</button>
    ` : '';
    return `
      <tr class="bidder-row" id="row-${b.id}" onclick="openDetail('${b.id}')">
        <td><div class="bidder-name">${b.name}</div><div class="bidder-email">${b.email}</div></td>
        <td>
          <div class="score-col">
            <div class="score-bar"><div class="score-fill" style="width:${barPct}%;background:${barClr}"></div></div>
            <span class="score-val">${b.score.toFixed(2)}</span>
          </div>
        </td>
        <td><span class="badge ${bcls}">${display}</span>${manualBadge}</td>
        <td class="td-r">${b.bids}</td>
        <td class="td-r">${b.wins}</td>
        <td><span class="${trajCls}">${trajIcon} ${b.traj}</span></td>
        <td class="td-r">${b.lots}</td>
        <td onclick="event.stopPropagation()">
          <div class="actions-col">
            ${adminBtns}
            <button class="btn-sm btn-detail" onclick="openDetail('${b.id}')">Detail</button>
          </div>
        </td>
      </tr>`;
  }).join('');

  document.getElementById('bidders-content').innerHTML = `
    <div class="table-card">
      <table class="rtable">
        <thead>
          <tr>
            <th>Bidder</th><th>Score</th><th>Decision</th>
            <th class="td-r">Bids</th><th class="td-r">Wins</th>
            <th>Trajectory</th><th class="td-r">Lots</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ── Scoring weights (operator-configurable) ─────────────────────────────────
const DEFAULT_WEIGHTS = { win_loss_rate:0.25, bid_count:0.20, reserve_ratio:0.20,
                          repeat_buyer:0.15, price_band_trajectory:0.10, hammer_influence:0.10 };
function toggleWeights() {
  const p = document.getElementById('weights-panel');
  p.style.display = (p.style.display === 'none') ? 'block' : 'none';
  updateWeightSum();
}
function readWeights() {
  let w = {}, sum = 0;
  for (const k in DEFAULT_WEIGHTS) {
    const el = document.getElementById('w-' + k);
    const v = el ? (parseFloat(el.value) || 0) : DEFAULT_WEIGHTS[k];
    w[k] = v; sum += v;
  }
  return { w, sum };
}
function updateWeightSum() {
  const { sum } = readWeights();
  const el = document.getElementById('wp-sum');
  if (el) el.textContent = 'Sum: ' + sum.toFixed(2) + (Math.abs(sum - 1) > 0.001 ? ' — will be normalised to 1' : '');
}
function resetWeights() {
  for (const k in DEFAULT_WEIGHTS) { const el = document.getElementById('w-' + k); if (el) el.value = DEFAULT_WEIGHTS[k]; }
  updateWeightSum();
}
function normalisedWeights() {
  const { w, sum } = readWeights();
  if (sum <= 0) return null;
  const n = {}; for (const k in w) n[k] = +(w[k] / sum).toFixed(4);
  return n;
}

// ── Run Evaluation ────────────────────────────────────────────────────────
async function runEval() {
  const btn = document.getElementById('eval-btn');
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div> Running…';
  showToast('Running pipeline…', 'info');
  try {
    const weights = normalisedWeights();
    const resp = await fetch('/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(weights ? { dry_run: true, weights } : { dry_run: true }),
    });
    if (resp.ok) {
      const d = await resp.json();
      showToast(`Done — ${d.approved} approved, ${d.reviewed} review, ${d.rejected} rejected`, 'success');
      setTimeout(() => window.location.reload(), 900);
    } else {
      showToast('Error: ' + (await resp.text()).substring(0, 120), 'error');
    }
  } catch(err) {
    showToast('Network error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

// ── Manual decisions ──────────────────────────────────────────────────────
async function updateDecision(ev, id, decision) {
  ev.stopPropagation();
  try {
    const resp = await fetch('/decision/' + id, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    });
    if (resp.ok) {
      DECISION_OVERRIDES[id] = decision;
      renderBidders();
      showToast(`${id} marked as ${decision}`, 'success');
      if (activeDrawerId === id) openDetail(id);
    } else {
      showToast('Failed to update decision', 'error');
    }
  } catch(err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// ── Bidder detail drawer ──────────────────────────────────────────────────
async function openDetail(id) {
  if (activeDrawerId === id) { closeDetail(); return; }
  activeDrawerId = id;
  document.querySelectorAll('.bidder-row').forEach(r => r.classList.remove('row-active'));
  const row = document.getElementById('row-' + id);
  if (row) row.classList.add('row-active');

  document.querySelector('.drawer-overlay').classList.add('open');

  const resp = await fetch('/results/' + id);
  if (!resp.ok) return;
  const d = await resp.json();

  const displayRec = DECISION_OVERRIDES[id] || d.recommendation;
  const bcls = { approve: 'b-approve', review: 'b-review', reject: 'b-reject' }[displayRec] || '';
  const manualBadge = DECISION_OVERRIDES[id]
    ? ' <span class="badge b-manual">Manual Override</span>' : '';

  document.getElementById('drawer-name').textContent = d.bidder_name;
  document.getElementById('drawer-meta').innerHTML =
    `<span>${d.bidder_email}</span>
     <span class="badge ${bcls}">${displayRec}</span>${manualBadge}
     <span>Score: <strong>${d.score.toFixed(3)}</strong></span>`;

  const dims = [
    ['win_loss_rate','Win Rate'],['bid_count','Bid Count'],['reserve_ratio','Reserve Ratio'],
    ['repeat_buyer','Repeat Buyer'],['price_band_trajectory','Price Trajectory'],['hammer_influence','Hammer Influence'],
  ];
  const dimsHtml = dims.map(([k, lbl]) => {
    const pct = Math.round(d.breakdown[k] * 100);
    const clr = pct >= 70 ? 'var(--green)' : pct >= 40 ? 'var(--yellow)' : 'var(--red)';
    return `<div class="dim-card">
      <div class="dim-label">${lbl}</div>
      <div class="dim-value" style="color:${clr}">${pct}%</div>
      <div class="dim-bar"><div class="dim-fill" style="width:${pct}%;background:${clr}"></div></div>
    </div>`;
  }).join('');

  // Per-lot scores (v2 artist-based matching)
  const perLotHtml = (d.per_lot_scores && d.per_lot_scores.length) ? `
    <div class="d-section">
      <div class="d-section-title">Per-Lot Artist Scores</div>
      <div class="lot-grid">
        ${d.per_lot_scores.map(ls => {
          const pct = Math.round(ls.score * 100);
          const barClr = pct >= 70 ? 'var(--green)' : pct >= 40 ? 'var(--yellow)' : 'var(--red)';
          return `<div class="lot-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
              <div>
                <div class="lot-title">${ls.title}</div>
                <div class="lot-meta" style="margin-top:3px">
                  <span style="color:var(--muted2);font-size:11px">${ls.artist}</span>
                  &nbsp;·&nbsp; <span class="lot-price">€${ls.estimate_low.toLocaleString()}–€${ls.estimate_high.toLocaleString()}</span>
                  &nbsp;·&nbsp; ${ls.auction_date.substring(0,10)}
                </div>
              </div>
              <div style="text-align:right;flex-shrink:0;margin-left:10px">
                <div style="font-size:18px;font-weight:800;color:${barClr}">${ls.score.toFixed(2)}</div>
                <div style="font-size:10px;color:var(--muted)">${ls.artist_bids} past bids</div>
              </div>
            </div>
            <div style="margin-top:8px;height:3px;background:var(--s4);border-radius:2px;overflow:hidden">
              <div style="width:${pct}%;height:100%;background:${barClr};border-radius:2px"></div>
            </div>
          </div>`;
        }).join('')}
      </div>
    </div>` : (d.matched_lots && d.matched_lots.length ? `
    <div class="d-section">
      <div class="d-section-title">Matched Upcoming Lots</div>
      <div class="lot-grid">
        ${d.matched_lots.map(l => `
          <div class="lot-card">
            <div class="lot-title">${l.title}</div>
            <div class="lot-meta">
              <span style="color:var(--muted2);font-size:11px">${l.artist || ''}</span>
              &nbsp;·&nbsp; <span class="lot-price">€${l.estimate_low.toLocaleString()}–€${l.estimate_high.toLocaleString()}</span>
              &nbsp;·&nbsp; ${l.auction_date.substring(0,10)}
            </div>
            <div style="font-size:11px;color:var(--muted);margin-top:4px">${l.match_reason}</div>
          </div>`).join('')}
      </div>
    </div>` : '');

  const flagsHtml = d.rejection_reasons.length ? `
    <div class="d-section">
      <div class="d-section-title" style="color:var(--red)">Flags</div>
      ${d.rejection_reasons.map(f => `<div class="flag-item">⚠ ${f}</div>`).join('')}
    </div>` : '';

  const bk = d.breakdown;
  const breakdownHtml = `
    <div class="d-section">
      <div class="d-section-title">Full Breakdown</div>
      ${[
        ['Total Bids', bk.total_bids],
        ['Lots Won', bk.total_wins],
        ['Bids Above Reserve', bk.bids_above_reserve],
        ['Distinct Lots Won', bk.distinct_lots_won],
        ['Price Trajectory', bk.trajectory],
        ['Insufficient History', bk.insufficient_history ? 'Yes' : 'No'],
        ['Evaluated At', d.evaluated_at.replace('T',' ').substring(0,16) + ' UTC'],
      ].map(([l,v]) => `
        <div class="breakdown-row">
          <span class="breakdown-label">${l}</span>
          <span class="breakdown-val">${v}</span>
        </div>`).join('')}
    </div>`;

  const adminFooter = currentRole === 'admin' ? `
    <button class="btn-sm btn-accept" onclick="updateDecision(event,'${id}','approve')">✓ Accept</button>
    <button class="btn-sm btn-reject" onclick="updateDecision(event,'${id}','reject')">✗ Reject</button>
    <button class="btn-sm btn-email"  onclick="openEmail(event,'${id}')">✉ Compose Email</button>
    <a href="/reports/${id}" target="_blank" class="btn-secondary" style="font-size:12px;padding:5px 10px;text-decoration:none">Report ↗</a>
  ` : `<a href="/reports/${id}" target="_blank" class="btn-secondary" style="font-size:12px;padding:5px 10px;text-decoration:none">View Report ↗</a>`;

  // ── Layer 2: NLP Rationale ──────────────────────────────────────────────
  const rationaleHtml = d.rationale ? `
    <div class="d-section" id="rationale-section-${id}">
      <div class="d-section-title" style="display:flex;justify-content:space-between;align-items:center">
        <span>AI Rationale</span>
        <span style="font-size:10px;color:var(--muted);font-weight:400">Why shortlisted</span>
      </div>
      <div class="rationale-text">${d.rationale}</div>
    </div>` : '';

  // ── Layer 3: Expandable Source Table ──────────────────────────────────────
  const sourcesHtml = (d.source_bids && d.source_bids.length) ? `
    <div class="d-section">
      <div class="sources-toggle" onclick="toggleSources('${id}')" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
        <span class="d-section-title" style="margin-bottom:0">See Sources</span>
        <span id="sources-arrow-${id}" style="color:var(--muted);font-size:12px;transition:transform .2s">▼ ${d.source_bids.length} bids</span>
      </div>
      <div id="sources-table-${id}" style="display:none;margin-top:10px;overflow-x:auto">
        <table class="sources-table">
          <thead><tr>
            <th>Lot</th><th>Artist</th><th>Bid</th><th>Outcome</th><th>Estimate</th><th>Date</th>
          </tr></thead>
          <tbody>
            ${d.source_bids.map(s => `<tr>
              <td title="${s.lot_id}">${s.lot_title || s.lot_id}</td>
              <td>${s.artist || '—'}</td>
              <td style="color:var(--green);font-weight:600">€${Number(s.bid_amount).toLocaleString()}</td>
              <td><span class="outcome-badge outcome-${s.outcome}">${s.outcome}</span></td>
              <td style="color:var(--muted2)">${s.estimate}</td>
              <td style="color:var(--muted)">${s.timestamp}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>` : '';

  document.getElementById('drawer-body').innerHTML = `
    <div class="d-section">
      <div class="d-section-title">Score Breakdown</div>
      <div class="dim-grid">${dimsHtml}</div>
    </div>
    ${rationaleHtml}
    ${sourcesHtml}
    ${perLotHtml}
    ${flagsHtml}
    ${breakdownHtml}`;

  document.getElementById('drawer-footer').innerHTML = adminFooter;
}

function closeDetail(ev) {
  if (ev && ev.target !== ev.currentTarget) return;
  document.querySelector('.drawer-overlay').classList.remove('open');
  document.querySelectorAll('.bidder-row').forEach(r => r.classList.remove('row-active'));
  activeDrawerId = null;
}

// ── Email composer ────────────────────────────────────────────────────────
async function openEmail(ev, id) {
  if (ev) ev.stopPropagation();
  emailTargetId = id;

  // Pre-fill from /emails/{id} if available
  try {
    const resp = await fetch('/emails/' + id);
    if (resp.ok) {
      const e = await resp.json();
      document.getElementById('e-to').value      = e.bidder_email || '';
      document.getElementById('e-subject').value = e.subject || '';
      document.getElementById('e-body').value    = e.body    || '';
    } else {
      // Fallback: try to get bidder email from results
      const r2 = await fetch('/results/' + id);
      if (r2.ok) {
        const d2 = await r2.json();
        document.getElementById('e-to').value = d2.bidder_email || '';
      }
      document.getElementById('e-subject').value = 'Preview Invitation — Upcoming Auction Lots Selected for You';
      document.getElementById('e-body').value    = '';
    }
  } catch(err) {
    document.getElementById('e-to').value = '';
  }
  document.getElementById('e-cc').value = '';
  document.getElementById('email-modal').classList.add('open');
}

function closeEmailModal(ev) {
  if (ev && ev.target !== ev.currentTarget) return;
  document.getElementById('email-modal').classList.remove('open');
}

function toggleSchedule() {
  const sched = document.querySelector('input[name="send-time"]:checked').value === 'schedule';
  document.getElementById('schedule-dt').classList.toggle('show', sched);
}

async function sendEmail() {
  const to      = document.getElementById('e-to').value.trim();
  const cc      = document.getElementById('e-cc').value.trim();
  const subject = document.getElementById('e-subject').value.trim();
  const body    = document.getElementById('e-body').value.trim();
  const isSchedule = document.querySelector('input[name="send-time"]:checked').value === 'schedule';
  const schedule_at = isSchedule ? document.getElementById('schedule-dt').value : null;

  if (!to || !subject || !body) {
    showToast('To, Subject, and Message are required.', 'error');
    return;
  }
  if (isSchedule && !schedule_at) {
    showToast('Please select a date and time to schedule.', 'error');
    return;
  }

  const sendBtn = document.getElementById('send-btn');
  sendBtn.disabled = true;
  sendBtn.innerHTML = '<div class="spinner"></div> Sending…';

  try {
    const resp = await fetch('/compose-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, cc, subject, body, schedule_at: schedule_at || null }),
    });
    if (resp.ok) {
      const d = await resp.json();
      closeEmailModal();
      showToast(isSchedule ? `Email scheduled (${d.email_id})` : `Email sent to ${to} (${d.email_id})`, 'success');
    } else {
      showToast('Failed: ' + (await resp.text()).substring(0,100), 'error');
    }
  } catch(err) {
    showToast('Error: ' + err.message, 'error');
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = isSchedule ? 'Schedule' : 'Send Now';
  }
}

// ── Summary tab ───────────────────────────────────────────────────────────
async function loadSummary() {
  const el = document.getElementById('summary-content');
  el.innerHTML = '<p style="color:var(--muted)">Loading…</p>';
  try {
    const resp = await fetch('/summary');
    if (!resp.ok) {
      el.innerHTML = '<div class="empty-state"><div class="empty-icon">📋</div><h3>No summary yet</h3><p>Run an evaluation first.</p></div>';
      return;
    }
    const md = await resp.text();
    // Parse markdown table into HTML
    const lines = md.split('\n').filter(l => l.trim());
    let tableHtml = '';
    let inTable = false;
    let headers = [];
    for (const line of lines) {
      if (line.trim().startsWith('|') && !line.includes('---')) {
        const cells = line.split('|').slice(1, -1).map(c => c.trim());
        if (!inTable) {
          headers = cells;
          tableHtml += '<table><thead><tr>' + cells.map(c => `<th>${c}</th>`).join('') + '</tr></thead><tbody>';
          inTable = true;
        } else {
          const rec = cells[3] || '';
          const badgeCls = rec.includes('Approve') ? 'b-approve' : rec.includes('Reject') ? 'b-reject' : rec.includes('Review') ? 'b-review' : '';
          const scoreCell = cells[2] || '';
          const score = parseFloat(scoreCell);
          const clr = score >= 0.7 ? 'var(--green)' : score >= 0.4 ? 'var(--yellow)' : 'var(--red)';
          tableHtml += '<tr>' + cells.map((c, i) => {
            if (i === 2) return `<td style="color:${clr};font-weight:700">${c}</td>`;
            if (i === 3) return `<td><span class="badge ${badgeCls}">${c.replace(/[✅❌🟡]/g,'').trim()}</span></td>`;
            return `<td>${c}</td>`;
          }).join('') + '</tr>';
        }
      } else if (!line.startsWith('|') && inTable) {
        tableHtml += '</tbody></table>';
        inTable = false;
      }
    }
    if (inTable) tableHtml += '</tbody></table>';

    // Render header text (lines before table)
    const headerLines = lines.filter(l => !l.startsWith('|') && !l.startsWith('#')).join('<br>');
    const h2 = lines.find(l => l.startsWith('# '));
    el.innerHTML = `
      <div style="margin-bottom:16px;padding:16px 20px;background:var(--s1);border:1px solid var(--border);border-radius:var(--radius)">
        <strong>${h2 ? h2.replace('# ','') : 'Evaluation Summary'}</strong><br>
        <span style="color:var(--muted2);font-size:13px">${headerLines}</span>
      </div>
      <div class="summary-table-wrap">${tableHtml}</div>`;
  } catch(err) {
    el.innerHTML = '<p style="color:var(--red)">Error loading summary: ' + err.message + '</p>';
  }
}

// ── Health tab ────────────────────────────────────────────────────────────
async function loadHealth() {
  const el = document.getElementById('health-content');
  el.innerHTML = '<p style="color:var(--muted)">Checking service health…</p>';
  try {
    const resp = await fetch('/health');
    const d    = await resp.json();
    const dotCls = d.status === 'ok' ? 'dot-ok' : 'dot-err';
    el.innerHTML = `
      <div class="panel-hd">
        <h2>System Health</h2>
        <p>Live service status · <a href="#" onclick="loadHealth();return false" style="color:var(--acch)">Refresh</a></p>
      </div>
      <div class="health-grid">
        <div class="health-card">
          <div class="health-status"><div class="status-dot ${dotCls}"></div><strong>${d.status.toUpperCase()}</strong></div>
          <div class="health-lbl">Service Status</div>
        </div>
        <div class="health-card">
          <div class="health-val">${d.service}</div>
          <div class="health-lbl">Service Name</div>
        </div>
        <div class="health-card">
          <div class="health-val" style="color:var(--acch)">v${d.version}</div>
          <div class="health-lbl">Version</div>
        </div>
        <div class="health-card">
          <div class="health-val" style="color:var(--blue)">${d.port}</div>
          <div class="health-lbl">Port</div>
        </div>
        <div class="health-card">
          <div class="health-val" style="color:var(--green)">${d.results_cached}</div>
          <div class="health-lbl">Results Cached</div>
        </div>
        <div class="health-card">
          <div class="health-val">${d.decision_overrides}</div>
          <div class="health-lbl">Manual Overrides</div>
        </div>
        <div class="health-card">
          <div class="health-val">${d.emails_queued}</div>
          <div class="health-lbl">Emails Logged</div>
        </div>
        <div class="health-card">
          <div class="health-val" style="font-size:13px">${d.timestamp.replace('T',' ').substring(0,19)} UTC</div>
          <div class="health-lbl">Last Checked</div>
        </div>
      </div>`;
  } catch(err) {
    el.innerHTML = `<div class="empty-state">
      <div class="empty-icon">⚠️</div>
      <h3>Health check failed</h3>
      <p>${err.message}</p>
    </div>`;
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────
let toastTimer = null;
function showToast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show t-' + (type || 'info');
  clearTimeout(toastTimer);
  if (type !== 'error') toastTimer = setTimeout(() => { t.className = 'toast'; }, 4000);
}

// ── Boot ──────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  selectRole('admin');

  // Restore session
  const saved = sessionStorage.getItem('da_user');
  if (saved) {
    try {
      const u = JSON.parse(saved);
      currentUser = u.email; currentRole = u.role;
      bootApp();
      return;
    } catch(e) {}
  }
  document.getElementById('login-page').style.display = 'flex';
});
"""

    # ── API Reference content (static HTML) ───────────────────────────────
    API_DOCS_HTML = """
<div class="panel-hd"><h2>API Reference</h2><p>deVeres Auction — Bidder Evaluation API v2.0</p></div>
<div class="api-grid">
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-get">GET</span>
      <span class="api-path">/health</span>
      <span class="api-desc">Service health &amp; stats</span>
    </div>
    <div class="api-body"><pre>{ "status": "ok", "version": "2.0.0", "port": 8003,
  "results_cached": 5, "decision_overrides": 1,
  "emails_queued": 2, "timestamp": "2026-05-11T20:00:00Z" }</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-post">POST</span>
      <span class="api-path">/evaluate</span>
      <span class="api-desc">Run full bidder scoring pipeline</span>
    </div>
    <div class="api-body"><pre>Request:  { "dry_run": true, "use_odoo": false }
Response: { "total": 5, "approved": 3, "reviewed": 0, "rejected": 2,
            "reports_written": 5, "emails_drafted": 3, "results": [...] }</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-get">GET</span>
      <span class="api-path">/results</span>
      <span class="api-desc">List all evaluated bidders</span>
    </div>
    <div class="api-body"><pre>[{ "bidder_id": "BDR-001", "bidder_name": "Margaret O'Sullivan",
   "score": 0.7133, "recommendation": "approve",
   "manual_decision": null, "total_bids": 8, "matched_lots": 3 }, ...]</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-get">GET</span>
      <span class="api-path">/results/{bidder_id}</span>
      <span class="api-desc">Full detail for one bidder</span>
    </div>
    <div class="api-body"><pre>{ "bidder_id": "BDR-004", "score": 0.7633,
  "breakdown": { "win_loss_rate": 1.0, "bid_count": 0.567, ... },
  "matched_lots": [...], "rejection_reasons": [] }</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-post">POST</span>
      <span class="api-path">/decision/{bidder_id}</span>
      <span class="api-desc">Manual accept / reject override (admin only)</span>
    </div>
    <div class="api-body"><pre>Request:  { "decision": "approve" }   // or "reject" | "review"
Response: { "ok": true, "bidder_id": "BDR-004", "decision": "approve" }</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-delete">DELETE</span>
      <span class="api-path">/decision/{bidder_id}</span>
      <span class="api-desc">Revert to algorithmic recommendation</span>
    </div>
    <div class="api-body"><pre>Response: { "ok": true, "bidder_id": "BDR-004" }</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-get">GET</span>
      <span class="api-path">/emails/{bidder_id}</span>
      <span class="api-desc">Drafted outreach email for one bidder</span>
    </div>
    <div class="api-body"><pre>{ "subject": "Preview Invitation — Upcoming Auction Lots...",
  "body": "Dear Patrick, ...", "status": "dry_run" }</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-post">POST</span>
      <span class="api-path">/compose-email</span>
      <span class="api-desc">Log and optionally schedule an outreach email</span>
    </div>
    <div class="api-body"><pre>Request:  { "to": "bidder@example.ie", "cc": "", "subject": "...",
            "body": "...", "schedule_at": "2026-05-15T10:00:00" }
Response: { "ok": true, "email_id": "mail_0001", "status": "sent" }</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-get">GET</span>
      <span class="api-path">/pending-emails</span>
      <span class="api-desc">List all composed / scheduled emails</span>
    </div>
    <div class="api-body"><pre>[{ "id": "mail_0001", "to": "...", "subject": "...",
   "status": "sent", "sent_at": "2026-05-11T21:00:00Z" }, ...]</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-get">GET</span>
      <span class="api-path">/summary</span>
      <span class="api-desc">Markdown summary table of all results</span>
    </div>
    <div class="api-body"><pre># deVeres Auction — Bidder Evaluation Summary
| # | Bidder | Score | Recommendation | Bids | Wins | Trajectory |
|---|--------|-------|----------------|------|------|------------|
| 1 | Patrick Doyle | 0.76 | ✅ Approve | ... |</pre></div>
  </div>
  <div class="api-card">
    <div class="api-card-head">
      <span class="method m-get">GET</span>
      <span class="api-path">/reports/{bidder_id}</span>
      <span class="api-desc">Detailed Markdown report for one bidder</span>
    </div>
    <div class="api-body"><pre>Returns full Markdown report with score bar, dimension table,
matched lots, and recommendations. Plain text response.</pre></div>
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>deVeres Auction</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>{CSS}</style>
</head>
<body>

<!-- ── LOGIN PAGE ──────────────────────────────────────────────────────── -->
<div id="login-page" style="display:none">
  <div class="login-card">
    <div class="login-logo">D</div>
    <h1>deVeres Auction</h1>
    <p class="login-sub">Bidder Evaluation Platform &nbsp;·&nbsp; by Cimelium</p>

    <div class="role-row">
      <button class="role-btn" id="role-admin" onclick="selectRole('admin')">
        <span class="role-icon">🔑</span> Admin
      </button>
      <button class="role-btn" id="role-viewer" onclick="selectRole('viewer')">
        <span class="role-icon">👁</span> Viewer
      </button>
    </div>

    <form onsubmit="doLogin(event)">
      <div class="form-group">
        <label for="l-email">Email address</label>
        <input type="email" id="l-email" placeholder="you@deveres.ie" required autocomplete="email"/>
      </div>
      <div class="form-group">
        <label for="l-pass">Password</label>
        <input type="password" id="l-pass" placeholder="••••••••••" required/>
      </div>
      <div class="login-error" id="l-error"></div>
      <button type="submit" class="btn-primary" style="width:100%;justify-content:center;padding:11px">
        Sign In
      </button>
    </form>

    <div class="login-hint">
      <strong>Demo credentials</strong><br>
      Admin &nbsp;— <code>admin@deveres.ie</code> / <code>Admin2026!</code><br>
      Viewer — <code>viewer@deveres.ie</code> / <code>View2026</code>
    </div>
  </div>
</div>

<!-- ── APP ────────────────────────────────────────────────────────────── -->
<div id="app">

  <header class="header">
    <div class="h-logo">D</div>
    <div class="h-brand">
      <div class="h-brand-name">deVeres Auction</div>
      <div class="h-brand-sub">by Cimelium</div>
    </div>

    <nav class="tab-nav">
      <button class="tab-btn" data-tab="bidders"  onclick="showTab('bidders')">Bidders</button>
      <button class="tab-btn" data-tab="summary"  onclick="showTab('summary')">Summary</button>
      <button class="tab-btn" data-tab="apidocs"  onclick="showTab('apidocs')">API Reference</button>
      <button class="tab-btn" data-tab="health"   onclick="showTab('health')">Health</button>
    </nav>

    <div class="h-right">
      <div class="user-chip">
        <div class="user-avatar" id="user-avatar">A</div>
        <span class="user-name" id="user-name">Admin</span>
        <span class="role-chip" id="role-chip">admin</span>
      </div>
      <button class="btn-logout" onclick="logout()">Sign out</button>
    </div>
  </header>

  <main class="main">

    <!-- Bidders Tab -->
    <div id="tab-bidders" class="tab-panel">
      <div class="toolbar">
        <button class="btn-primary admin-only" id="eval-btn" onclick="runEval()">
          <span>▶</span> Run Evaluation
        </button>
        <button class="btn-secondary admin-only" id="weights-toggle" onclick="toggleWeights()">⚖ Weights</button>
        <button class="btn-secondary" onclick="showTab('bidders')">↻ Refresh</button>
        <div id="toast" class="toast"></div>
        <span class="last-run" id="last-run">{_results_cache[0].evaluated_at[:16].replace("T", " ") + " UTC" if _results_cache else ""}</span>
      </div>
      <div id="weights-panel" class="weights-panel admin-only" style="display:none">
        <div class="wp-title">Scoring weights <span class="wp-sub">— tune how each signal contributes, then Run Evaluation. Values are normalised to sum to 1.</span></div>
        <div class="wp-grid">
          <label>Win / loss rate<input type="number" step="0.05" min="0" id="w-win_loss_rate" value="0.25" oninput="updateWeightSum()"></label>
          <label>Bid count / engagement<input type="number" step="0.05" min="0" id="w-bid_count" value="0.20" oninput="updateWeightSum()"></label>
          <label>Reserve ratio (intent)<input type="number" step="0.05" min="0" id="w-reserve_ratio" value="0.20" oninput="updateWeightSum()"></label>
          <label>Repeat buyer<input type="number" step="0.05" min="0" id="w-repeat_buyer" value="0.15" oninput="updateWeightSum()"></label>
          <label>Price-band trajectory<input type="number" step="0.05" min="0" id="w-price_band_trajectory" value="0.10" oninput="updateWeightSum()"></label>
          <label>Hammer influence<input type="number" step="0.05" min="0" id="w-hammer_influence" value="0.10" oninput="updateWeightSum()"></label>
        </div>
        <div class="wp-actions"><span id="wp-sum" class="wp-sum"></span><button class="btn-secondary" onclick="resetWeights()">Reset defaults</button></div>
      </div>
      <div id="stats-grid" class="stats"></div>
      <div id="bidders-content"></div>
    </div>

    <!-- Summary Tab -->
    <div id="tab-summary" class="tab-panel">
      <div class="panel-hd">
        <h2>Evaluation Summary</h2>
        <p>Full scoring results for all evaluated bidders</p>
      </div>
      <div id="summary-content"><p style="color:var(--muted)">Loading…</p></div>
    </div>

    <!-- API Reference Tab -->
    <div id="tab-apidocs" class="tab-panel">
      {API_DOCS_HTML}
    </div>

    <!-- Health Tab -->
    <div id="tab-health" class="tab-panel">
      <div id="health-content"><p style="color:var(--muted)">Loading…</p></div>
    </div>

  </main>
</div>

<!-- ── BIDDER DETAIL DRAWER ───────────────────────────────────────────── -->
<div class="drawer-overlay" onclick="closeDetail(event)">
  <div class="drawer">
    <div class="drawer-head">
      <div class="drawer-head-left">
        <h3 id="drawer-name">Bidder Detail</h3>
        <div class="d-meta" id="drawer-meta"></div>
      </div>
      <button class="close-btn" onclick="closeDetail()">×</button>
    </div>
    <div class="drawer-body" id="drawer-body"></div>
    <div class="drawer-footer" id="drawer-footer"></div>
  </div>
</div>

<!-- ── EMAIL COMPOSER MODAL ───────────────────────────────────────────── -->
<div class="modal-overlay" id="email-modal" onclick="closeEmailModal(event)">
  <div class="modal-box">
    <div class="modal-head">
      <h3>Compose Outreach Email</h3>
      <button class="close-btn" onclick="closeEmailModal()">×</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label>To</label>
        <input type="email" id="e-to" placeholder="recipient@example.com" required/>
      </div>
      <div class="form-group">
        <label>CC <span style="color:var(--muted);font-weight:400">(optional)</span></label>
        <input type="email" id="e-cc" placeholder="cc@example.com"/>
      </div>
      <div class="form-group">
        <label>Subject</label>
        <input type="text" id="e-subject" placeholder="Email subject line" required/>
      </div>
      <div class="form-group">
        <label>Message</label>
        <textarea id="e-body" rows="12" placeholder="Write your message here…" required></textarea>
      </div>
      <div class="form-group">
        <label>Delivery</label>
        <div class="send-opts">
          <label class="radio-label">
            <input type="radio" name="send-time" value="now" checked onchange="toggleSchedule()"/> Send Now
          </label>
          <label class="radio-label">
            <input type="radio" name="send-time" value="schedule" onchange="toggleSchedule()"/> Schedule for later
          </label>
          <input type="datetime-local" id="schedule-dt"/>
        </div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-secondary" onclick="closeEmailModal()">Cancel</button>
      <button class="btn-primary" id="send-btn" onclick="sendEmail()">Send Now</button>
    </div>
  </div>
</div>

<script>
const INITIAL_STATS      = {stats_json};
const INITIAL_BIDDERS    = {bidders_json};
const DECISION_OVERRIDES = {overrides_json};
</script>
<script>{JS}</script>
</body>
</html>"""

# ── Product separation (2-Jul-2026 decision) ─────────────────────────────────
# This app is PRODUCT 2: AI Bidder Evaluation ONLY. Contact Reconciliation is a
# completely separate product served by recon_app.py — no shared routes, no
# shared landing page, no shared navigation.
