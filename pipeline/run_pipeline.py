"""
Deviours Auction — Pipeline Runner
Entry point: load data → evaluate → generate reports → draft emails.

Usage:
  # With synthetic JSON data (development):
  python -m pipeline.run_pipeline --data-dir data/ --output-dir output/

  # With Odoo live data:
  python -m pipeline.run_pipeline --odoo --output-dir output/

  # Dry run (no Gemma4 call):
  python -m pipeline.run_pipeline --data-dir data/ --output-dir output/ --dry-run
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .aggregator import evaluate_all
from .email_drafter import draft_all_emails
from .odoo_client import load_from_json, OdooClient
from .recommender import generate_all_reports, generate_summary_table


def run(
    lots_path:    str | None = None,
    bidders_path: str | None = None,
    output_dir:   str = "output",
    use_odoo:     bool = False,
    dry_run:      bool = False,
) -> dict:
    """
    Full pipeline run.
    Returns summary dict: total, approved, reviewed, rejected, reports_written, emails_drafted.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    if use_odoo:
        client   = OdooClient()
        lots     = client.fetch_upcoming_lots()
        profiles = client.fetch_bidder_profiles()
    else:
        data_dir  = Path(lots_path).parent if lots_path else Path("data")
        lots_file = lots_path    or str(data_dir / "sample_upcoming_lots.json")
        bids_file = bidders_path or str(data_dir / "sample_bidding_history.json")
        lots, profiles = load_from_json(lots_file, bids_file)

    print(f"Loaded {len(lots)} lots, {len(profiles)} bidder profiles")

    # ── Evaluate all bidders ──────────────────────────────────────────────────
    results = evaluate_all(profiles, lots)

    approved = [r for r in results if r.recommendation.value == "approve"]
    reviewed = [r for r in results if r.recommendation.value == "review"]
    rejected = [r for r in results if r.recommendation.value == "reject"]

    print(f"Evaluation complete: {len(approved)} approve, {len(reviewed)} review, {len(rejected)} reject")

    # ── Write back to Odoo ────────────────────────────────────────────────────
    if use_odoo:
        n = client.write_evaluation_results(results)
        print(f"Wrote {n} evaluation results back to Odoo")

    # ── Generate Markdown reports ─────────────────────────────────────────────
    reports_dir = out / "reports"
    written     = generate_all_reports(results, reports_dir)
    print(f"Generated {len(written)} bidder reports in {reports_dir}/")

    # ── Summary table ─────────────────────────────────────────────────────────
    summary_md = generate_summary_table(results)
    summary_path = out / "summary.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    print(f"Summary table written to {summary_path}")

    # ── Draft emails for approved bidders ────────────────────────────────────
    emails = draft_all_emails(results, dry_run=dry_run)
    drafted = [e for e in emails if e.get("status") in ("drafted", "dry_run")]
    emails_path = out / "emails.json"
    emails_path.write_text(json.dumps(emails, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Drafted {len(drafted)} outreach emails → {emails_path}")

    return {
        "total":          len(results),
        "approved":       len(approved),
        "reviewed":       len(reviewed),
        "rejected":       len(rejected),
        "reports_written": len(written),
        "emails_drafted":  len(drafted),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deviours Auction Bidder Evaluation Pipeline")
    parser.add_argument("--data-dir",  default="data",   help="Directory with JSON data files")
    parser.add_argument("--output-dir", default="output", help="Output directory for reports")
    parser.add_argument("--odoo",     action="store_true", help="Use live Odoo data")
    parser.add_argument("--dry-run",  action="store_true", help="Skip Gemma4 API calls")
    args = parser.parse_args()

    summary = run(
        lots_path    = str(Path(args.data_dir) / "sample_upcoming_lots.json"),
        bidders_path = str(Path(args.data_dir) / "sample_bidding_history.json"),
        output_dir   = args.output_dir,
        use_odoo     = args.odoo,
        dry_run      = args.dry_run,
    )
    print("\nPipeline complete:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
