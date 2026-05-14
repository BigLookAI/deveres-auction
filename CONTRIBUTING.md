# Contributing to Deviours Auction

Thank you for your interest in contributing. This document explains how to get started.

## Development Setup

```bash
git clone https://github.com/santosh-biglook/deviours-auction
cd deviours-auction
./setup.sh
./run.sh
```

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

All 40 tests should pass in under 1 second. No network or database connection required.

## Project Structure

```
deviours-auction/
├── api.py              # FastAPI application + embedded dashboard SPA
├── pipeline/
│   ├── models.py       # Core dataclasses (Bid, Lot, BidderProfile, EvaluationResult…)
│   ├── scorers.py      # 6 independent scoring dimensions (0–1 each, deterministic)
│   ├── aggregator.py   # Combines scores, artist matching, per-lot evaluation
│   ├── recommender.py  # Markdown report + summary table generation
│   ├── email_drafter.py# Outreach email drafting (LLM or dry-run template)
│   ├── odoo_client.py  # Odoo XML-RPC client + local JSON loader
│   └── run_pipeline.py # CLI entry point
├── data/               # Sample JSON data (lots, bidders, bids)
├── tests/              # pytest test suite
├── skills/             # Editable email tone/template files
└── docs/               # HTML project report
```

## Coding Standards

- Python 3.11+ compatible
- No type: ignore comments — fix the types
- No external AI calls in the scoring engine — scoring is fully deterministic
- All new scoring logic must have corresponding tests in `tests/test_scorers.py`
- Keep `api.py` self-contained — the dashboard SPA is embedded, no build step

## Adding a Scoring Dimension

1. Add the scorer function to `pipeline/scorers.py` following the existing pattern (returns `float [0.0, 1.0]`)
2. Add the field to `ScoreBreakdown` in `pipeline/models.py`
3. Wire it up in `_score_breakdown_for_bids()` in `pipeline/aggregator.py`
4. Update `DEFAULT_WEIGHTS` in `aggregator.py` (ensure weights still sum to 1.0)
5. Add tests in `tests/test_scorers.py`

## Submitting a Pull Request

1. Fork the repo and create a feature branch
2. Ensure all tests pass: `pytest tests/ -q`
3. Open a PR with a clear description of the change and why

## Reporting Issues

Please use [GitHub Issues](https://github.com/santosh-biglook/deviours-auction/issues).
Include Python version, OS, and the full error traceback.
