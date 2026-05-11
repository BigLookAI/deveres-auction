"""
Deviours Auction — FastAPI Service
Port: 8003

Endpoints:
  POST /evaluate           — run full pipeline (uses sample JSON or Odoo)
  GET  /results            — list all evaluation results
  GET  /results/{id}       — single bidder evaluation detail
  GET  /reports/{id}       — Markdown report for one bidder
  GET  /emails/{id}        — drafted outreach email for one bidder
  GET  /summary            — summary table Markdown
  GET  /health             — health check
  GET  /                   — HTML results viewer
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from pydantic import BaseModel

from pipeline.aggregator import evaluate_all
from pipeline.email_drafter import draft_all_emails
from pipeline.odoo_client import load_from_json
from pipeline.recommender import generate_all_reports, generate_summary_table
from pipeline.models import EvaluationResult, Recommendation

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
DATA_DIR    = BASE_DIR / "data"
OUTPUT_DIR  = BASE_DIR / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"

LOTS_PATH    = DATA_DIR / "sample_upcoming_lots.json"
BIDDERS_PATH = DATA_DIR / "sample_bidding_history.json"

# Gemma4 on DGX — same instance as hero-gallery (read-only, no dependency)
GEMMA4_URL = os.environ.get("GEMMA4_URL", "http://localhost:8000/generate")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "Deviours Auction — Bidder Evaluation API",
    description = "Deterministic bidder scoring pipeline for Tegiris auction house",
    version     = "1.0.0",
)

# In-memory result cache (survives process; reset on restart)
_results_cache: list[EvaluationResult] = []
_emails_cache:  list[dict]             = []


# ── Request / Response models ─────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    use_odoo:    bool = False    # True = live Odoo data; False = sample JSON
    dry_run:     bool = True     # True = skip Gemma4 email call
    lots_path:   Optional[str]  = None
    bidders_path: Optional[str] = None


class BidderSummary(BaseModel):
    bidder_id:      str
    bidder_name:    str
    bidder_email:   str
    score:          float
    recommendation: str
    total_bids:     int
    total_wins:     int
    trajectory:     str
    matched_lots:   int


class EvaluateResponse(BaseModel):
    total:          int
    approved:       int
    reviewed:       int
    rejected:       int
    reports_written: int
    emails_drafted: int
    results:        list[BidderSummary]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "deviours-auction", "port": 8003}


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest):
    """Run full bidder evaluation pipeline and cache results."""
    global _results_cache, _emails_cache

    lots_path    = req.lots_path    or str(LOTS_PATH)
    bidders_path = req.bidders_path or str(BIDDERS_PATH)

    if req.use_odoo:
        from pipeline.odoo_client import OdooClient
        client   = OdooClient()
        lots     = client.fetch_upcoming_lots()
        profiles = client.fetch_bidder_profiles()
    else:
        lots, profiles = load_from_json(lots_path, bidders_path)

    results = evaluate_all(profiles, lots)

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
    """Return all cached evaluation results (sorted by score desc)."""
    if not _results_cache:
        raise HTTPException(404, "No results yet — call POST /evaluate first")
    return [_to_summary(r) for r in _results_cache]


@app.get("/results/{bidder_id}")
def get_result(bidder_id: str):
    """Return full evaluation detail for one bidder."""
    result = _find_result(bidder_id)
    b = result.breakdown
    return {
        "bidder_id":      result.bidder_id,
        "bidder_name":    result.bidder_name,
        "bidder_email":   result.bidder_email,
        "score":          result.score,
        "recommendation": result.recommendation.value,
        "evaluated_at":   result.evaluated_at,
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
                "lot_id":       ml.lot_id,
                "title":        ml.title,
                "category":     ml.category,
                "estimate_low": ml.estimate_low,
                "estimate_high":ml.estimate_high,
                "auction_date": ml.auction_date,
                "match_reason": ml.match_reason,
            }
            for ml in result.matched_lots
        ],
        "rejection_reasons": result.rejection_reasons,
    }


@app.get("/reports/{bidder_id}", response_class=PlainTextResponse)
def get_report(bidder_id: str):
    """Return Markdown report for one bidder."""
    path = REPORTS_DIR / f"report_{bidder_id.lower().replace('/', '-')}.md"
    if not path.exists():
        # Try to generate from cache
        result = _find_result(bidder_id)
        from pipeline.recommender import generate_markdown_report
        return generate_markdown_report(result)
    return path.read_text(encoding="utf-8")


@app.get("/emails/{bidder_id}")
def get_email(bidder_id: str):
    """Return drafted outreach email for one bidder (APPROVE only)."""
    if not _emails_cache:
        raise HTTPException(404, "No emails yet — call POST /evaluate first")
    email = next((e for e in _emails_cache if e.get("bidder_id") == bidder_id), None)
    if not email:
        raise HTTPException(404, f"No email for bidder {bidder_id}")
    return email


@app.get("/summary", response_class=PlainTextResponse)
def get_summary():
    """Return Markdown summary table of all results."""
    path = OUTPUT_DIR / "summary.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    if not _results_cache:
        raise HTTPException(404, "No results yet — call POST /evaluate first")
    return generate_summary_table(_results_cache)


@app.get("/", response_class=HTMLResponse)
def results_viewer():
    """Simple HTML results dashboard."""
    return HTMLResponse(_build_html_viewer())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_summary(r: EvaluationResult) -> BidderSummary:
    return BidderSummary(
        bidder_id      = r.bidder_id,
        bidder_name    = r.bidder_name,
        bidder_email   = r.bidder_email,
        score          = r.score,
        recommendation = r.recommendation.value,
        total_bids     = r.breakdown.total_bids,
        total_wins     = r.breakdown.total_wins,
        trajectory     = r.breakdown.trajectory.value,
        matched_lots   = len(r.matched_lots),
    )


def _find_result(bidder_id: str) -> EvaluationResult:
    if not _results_cache:
        raise HTTPException(404, "No results yet — call POST /evaluate first")
    r = next((x for x in _results_cache if x.bidder_id == bidder_id), None)
    if not r:
        raise HTTPException(404, f"Bidder {bidder_id!r} not found")
    return r


def _build_html_viewer() -> str:
    if not _results_cache:
        results_html = """
        <div class="empty">
          <p>No results yet.</p>
          <p>Run a pipeline evaluation first:</p>
          <pre>curl -X POST http://localhost:8003/evaluate -H "Content-Type: application/json" -d '{"dry_run": true}'</pre>
          <button onclick="runEval()">▶ Run Evaluation Now</button>
        </div>"""
        stats_html = '<div class="stat"><div class="num">—</div><div class="lbl">Run /evaluate first</div></div>'
    else:
        approved = sum(1 for r in _results_cache if r.recommendation.value == "approve")
        reviewed = sum(1 for r in _results_cache if r.recommendation.value == "review")
        rejected = sum(1 for r in _results_cache if r.recommendation.value == "reject")
        stats_html = f"""
        <div class="stat"><div class="num green">{approved}</div><div class="lbl">Approved</div></div>
        <div class="stat"><div class="num yellow">{reviewed}</div><div class="lbl">Review</div></div>
        <div class="stat"><div class="num red">{rejected}</div><div class="lbl">Rejected</div></div>
        <div class="stat"><div class="num">{len(_results_cache)}</div><div class="lbl">Total</div></div>"""

        rows = []
        for r in _results_cache:
            b  = r.breakdown
            rec = r.recommendation.value
            icon = {"approve": "✅", "review": "🟡", "reject": "❌"}.get(rec, "")
            bar_w = int(r.score * 100)
            rows.append(f"""
            <tr onclick="loadDetail('{r.bidder_id}')" style="cursor:pointer">
              <td><strong>{r.bidder_name}</strong><br><small style="color:#888">{r.bidder_email}</small></td>
              <td>
                <div class="bar-wrap"><div class="bar-fill" style="width:{bar_w}%"></div></div>
                <small>{r.score:.2f}</small>
              </td>
              <td>{icon} {rec.title()}</td>
              <td>{b.total_bids} / {b.total_wins}</td>
              <td>{b.trajectory.value}</td>
              <td>{len(r.matched_lots)}</td>
              <td>
                <a href="/reports/{r.bidder_id}" target="_blank">Report</a> ·
                <a href="/emails/{r.bidder_id}" target="_blank">Email</a>
              </td>
            </tr>""")
        results_html = f"""
        <table class="results-table">
          <thead><tr>
            <th>Bidder</th><th>Score</th><th>Recommendation</th>
            <th>Bids / Wins</th><th>Trajectory</th><th>Matched Lots</th><th>Actions</th>
          </tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Deviours Auction — Results</title>
  <style>
    :root {{--bg:#0f1117;--surface:#1a1d27;--border:#2e3350;--text:#e2e6f3;--muted:#7b82a8;--green:#3ecf8e;--yellow:#f7d56e;--red:#f76e6e;--purple:#9b6ef7;}}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;font-size:14px;padding:32px 24px}}
    h1{{font-size:22px;font-weight:700;margin-bottom:4px}}
    .sub{{color:var(--muted);font-size:13px;margin-bottom:28px}}
    .stats{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px}}
    .stat{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 20px;min-width:120px}}
    .num{{font-size:28px;font-weight:700}}.lbl{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-top:4px}}
    .green{{color:var(--green)}}.yellow{{color:var(--yellow)}}.red{{color:var(--red)}}
    .results-table{{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden}}
    .results-table th{{background:#22263a;padding:10px 14px;text-align:left;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border)}}
    .results-table td{{padding:12px 14px;border-bottom:1px solid rgba(46,51,80,.4)}}
    .results-table tr:last-child td{{border-bottom:none}}
    .results-table tr:hover td{{background:rgba(255,255,255,.02)}}
    .bar-wrap{{background:#22263a;border-radius:4px;height:6px;width:120px;margin-bottom:4px}}
    .bar-fill{{background:var(--purple);height:100%;border-radius:4px}}
    a{{color:var(--purple);text-decoration:none}}.a:hover{{text-decoration:underline}}
    .controls{{display:flex;gap:12px;margin-bottom:20px;align-items:center}}
    button{{background:var(--purple);color:#fff;border:none;border-radius:7px;padding:8px 18px;font-size:13px;cursor:pointer;font-weight:600}}
    button:hover{{opacity:.85}}
    .empty{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:32px;text-align:center;color:var(--muted)}}
    .empty pre{{background:#22263a;padding:12px 16px;border-radius:6px;font-size:12px;margin:12px 0;text-align:left;color:var(--text);overflow:auto}}
    #detail{{display:none;margin-top:24px;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px}}
    #detail h3{{margin-bottom:12px}}
    .dim-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:8px}}
    .dim-card{{background:#22263a;border-radius:8px;padding:12px}}
    .dim-card .dlbl{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.4px}}
    .dim-card .dval{{font-size:20px;font-weight:700;margin-top:2px}}
    .tag{{display:inline-block;background:rgba(155,110,247,.15);color:var(--purple);padding:2px 8px;border-radius:999px;font-size:11px;margin:2px}}
  </style>
</head>
<body>
  <h1>Deviours Auction — Bidder Evaluation</h1>
  <p class="sub">Tegiris Auction House · Deterministic scoring pipeline · Cimelium Ltd</p>
  <div class="controls">
    <button onclick="runEval()">▶ Run Evaluation</button>
    <a href="/docs" target="_blank" style="color:var(--muted);font-size:12px">API Docs ↗</a>
    <a href="/summary" target="_blank" style="color:var(--muted);font-size:12px">Summary MD ↗</a>
  </div>
  <div class="stats">{stats_html}</div>
  {results_html}
  <div id="detail"><h3 id="detail-name">Bidder Detail</h3><div id="detail-body"></div></div>
  <script>
    async function runEval() {{
      const btn = document.querySelector('button');
      btn.textContent = '⏳ Evaluating...';
      btn.disabled = true;
      try {{
        const r = await fetch('/evaluate', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{dry_run:true}})}});
        if (r.ok) {{ window.location.reload(); }}
        else {{ alert('Evaluation failed: ' + await r.text()); }}
      }} finally {{ btn.disabled = false; btn.textContent = '▶ Run Evaluation'; }}
    }}
    async function loadDetail(id) {{
      const r = await fetch('/results/' + id);
      if (!r.ok) return;
      const d = await r.json();
      document.getElementById('detail-name').textContent = d.bidder_name + ' — ' + d.score.toFixed(2);
      const dims = ['win_loss_rate','bid_count','reserve_ratio','repeat_buyer','price_band_trajectory','hammer_influence'];
      const labels = ['Win Rate','Bid Count','Reserve Ratio','Repeat Buyer','Price Trajectory','Hammer Influence'];
      let html = '<div class="dim-grid">' + dims.map((k,i) => `<div class="dim-card"><div class="dlbl">${{labels[i]}}</div><div class="dval">${{(d.breakdown[k]*100).toFixed(0)}}%</div></div>`).join('') + '</div>';
      if (d.matched_lots.length) {{
        html += '<h4 style="margin:16px 0 8px">Matched Lots</h4>';
        d.matched_lots.forEach(l => {{ html += `<span class="tag">€${{l.estimate_low.toLocaleString()}}–€${{l.estimate_high.toLocaleString()}} · ${{l.title}}</span>`; }});
      }}
      if (d.rejection_reasons.length) {{
        html += '<h4 style="margin:16px 0 8px;color:#f76e6e">Flags</h4>';
        d.rejection_reasons.forEach(r => {{ html += `<p style="color:#f76e6e;font-size:12px">⚠ ${{r}}</p>`; }});
      }}
      document.getElementById('detail-body').innerHTML = html;
      document.getElementById('detail').style.display = 'block';
      document.getElementById('detail').scrollIntoView({{behavior:'smooth'}});
    }}
  </script>
</body>
</html>"""
