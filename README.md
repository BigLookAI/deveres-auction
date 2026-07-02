# deVeres Auction

**Bidder Evaluation & Invitation Intelligence Platform**

A fully portable, self-contained Python service that scores auction bidders against upcoming lots and recommends who to personally invite — with a built-in dashboard, REST API, and report generation.

No database. No GPU. No paid APIs. Runs on any MacBook in under 2 minutes.

---

## Quick Start

```bash
git clone https://github.com/santosh-biglook/deveres-auction
cd deveres-auction
./setup.sh    # one-time: creates .venv, installs deps, runs tests
./run.sh      # start the server
```

Then open **http://localhost:8003** in your browser.

**Login credentials (demo):**
| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@deveres.ie` | `Admin2026!` |
| Viewer | `viewer@deveres.ie` | `View2026` |

Or with Docker:

```bash
docker compose up
```

---

## What it does

deVeres answers: **"Should we invite bidder X for upcoming lot Y?"**

For each bidder, it:

1. Loads their historical bid history
2. Matches them to upcoming lots by **artist** (e.g. bidder has 5 past bids on Alice Burke lots → score them against the upcoming Alice Burke lot)
3. Scores the bidder across **6 dimensions** (all deterministic, no LLM):

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Win/Loss Rate | 25% | Fraction of bids that resulted in a win |
| Bid Count | 20% | Engagement in the last 12 months (recent bids weighted ×1.5) |
| Reserve Ratio | 20% | How often bids exceed the reserve price (intent signal) |
| Repeat Buyer | 15% | Number of distinct lots won |
| Price Band Trajectory | 10% | Whether the bidder is escalating to higher price bands over time |
| Hammer Influence | 10% | How far above estimate the bidder drives the hammer price when winning |

4. Recommends per lot:

| Decision | Score | Action |
|----------|-------|--------|
| **Approve** | ≥ 0.70 | Send personal invitation |
| **Review** | 0.40–0.69 | Human curator should review |
| **Reject** | < 0.40 | Do not invite |

5. Generates a Markdown report and drafts a personalised outreach email for each approved bidder

---

## Requirements

- **Python 3.11+** (tested on 3.11, 3.12, 3.13)
- No database required
- No GPU required
- No API keys required (demo mode works out of the box)

---

## Setup

### Option A — Python venv (recommended for development)

```bash
./setup.sh   # creates .venv, installs deps, runs 40 tests
./run.sh     # starts server at http://localhost:8003
```

To stop: `./stop.sh` or `Ctrl+C`

### Option B — Docker

```bash
# Build and run
docker compose up

# Run in background
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Option C — Manual

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --reload --port 8003
```

---

## Using the Dashboard

After starting, visit **http://localhost:8003**.

1. **Login** as admin or viewer
2. Click **Run Evaluation** — scores all 15 bundled bidders against 8 upcoming lots
3. Click any row to open the **detail drawer** — shows all 6 dimension scores and per-lot recommendations
4. **Accept / Reject** any bidder (admin only) to override the algorithmic recommendation
5. Click **Email** to compose and log an outreach email
6. Switch to **Summary** tab for a full Markdown table

---

## REST API

Base URL: `http://localhost:8003`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/evaluate` | Run full pipeline |
| `GET` | `/results` | List all evaluation results |
| `GET` | `/results/{id}` | Full detail for one bidder |
| `POST` | `/decision/{id}` | Manual override (approve/review/reject) |
| `DELETE` | `/decision/{id}` | Clear override |
| `GET` | `/reports/{id}` | Markdown evaluation report |
| `GET` | `/emails/{id}` | Drafted outreach email |
| `POST` | `/compose-email` | Log/schedule an email |
| `GET` | `/summary` | Full summary table (Markdown) |
| `GET` | `/health` | Health check |
| `GET` | `/` | Dashboard (HTML SPA) |

Interactive docs: **http://localhost:8003/docs**

### Example: Run evaluation

```bash
curl -X POST http://localhost:8003/evaluate \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

### Example: Get bidder detail

```bash
curl http://localhost:8003/results/BDR-001
```

---

## CLI Runner

Run the pipeline from the command line without starting the API server:

```bash
# Using bundled sample data (dry-run, no LLM needed)
.venv/bin/python -m pipeline.run_pipeline --dry-run

# Custom data directory
.venv/bin/python -m pipeline.run_pipeline --data-dir /path/to/data --output-dir output/

# With Odoo live data (requires ODOO_* env vars)
.venv/bin/python -m pipeline.run_pipeline --odoo
```

Output is written to `output/`:
- `output/summary.md` — summary table
- `output/reports/report_*.md` — per-bidder Markdown reports
- `output/emails.json` — drafted outreach emails

---

## Configuration

Copy `.env.example` to `.env` and edit as needed. All variables are optional.

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8003` | Server port |
| `HOST` | `0.0.0.0` | Bind address |
| `VLLM_URL` | _(empty)_ | LLM endpoint for email drafting (auto dry-run if unset) |
| `ODOO_URL` | _(empty)_ | Odoo instance URL |
| `ODOO_DB` | _(empty)_ | Odoo database name |
| `ODOO_USERNAME` | _(empty)_ | Odoo login email |
| `ODOO_PASSWORD` | _(empty)_ | Odoo API key |

### LLM Email Drafting (optional)

By default, email drafting uses a built-in template (no LLM required). To use an LLM:

```bash
# Ollama (local)
ollama pull gemma2:2b
VLLM_URL=http://localhost:11434/api/generate ./run.sh

# Any OpenAI-compatible vLLM server
VLLM_URL=http://localhost:8000/generate ./run.sh
```

### Odoo Integration (optional)

To pull live bidder data from Odoo instead of JSON files:

```bash
ODOO_URL=https://your.odoo.com ODOO_DB=mydb ODOO_USERNAME=admin@you.com \
  ODOO_PASSWORD=your_api_key ./run.sh
```

Then call `/evaluate` with `{"use_odoo": true}`.

---

## Data Format

The system uses three JSON files in `data/`:

### `sample_upcoming_lots.json`
```json
[
  {
    "lot_id": "LOT-2026-U001",
    "title": "Composition in Blue",
    "artist": "Alice Burke",
    "category": "painting",
    "estimate_low": 2000,
    "estimate_high": 3500,
    "reserve_price": 1800,
    "auction_date": "2026-09-15T14:00:00Z"
  }
]
```

### `sample_bidding_history.json`
```json
[
  {
    "bidder_id": "BDR-001",
    "name": "Jane Smith",
    "email": "jane@example.com",
    "bids": [
      {
        "bid_id": "B001",
        "lot_id": "LOT-2024-P001",
        "bid_amount": 2500.00,
        "timestamp": "2025-03-10T11:00:00Z",
        "outcome": "won",
        "hammer_price": 2700.00
      }
    ]
  }
]
```

### `sample_past_lots.json`

Same format as upcoming lots — used to build the artist index that links historical bids to upcoming lots.

---

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

40 tests covering all 6 scoring dimensions and the full evaluation pipeline. Runs in under 1 second.

```
tests/test_scorers.py      — 25 tests (all 6 dimensions, edge cases)
tests/test_aggregator.py   — 15 tests (end-to-end, artist matching, per-lot scoring)
```

---

## Architecture

```
Request
  │
  ▼
FastAPI (api.py)
  │
  ├── POST /evaluate
  │     ├── odoo_client.py  — load JSON / fetch from Odoo
  │     ├── aggregator.py   — build artist index → score per lot → EvaluationResult[]
  │     │     └── scorers.py  — 6 independent dimensions (0–1 each)
  │     ├── recommender.py  — generate Markdown reports
  │     └── email_drafter.py — draft outreach emails (LLM or template)
  │
  └── GET /             — serve embedded HTML dashboard SPA
```

All scoring is **fully deterministic** — no LLM, no external API calls, no randomness.
The LLM is only used for the optional email drafting step.

---

## Project Structure

```
deveres-auction/
├── api.py                      # FastAPI app + embedded dashboard SPA
├── pipeline/
│   ├── __init__.py
│   ├── models.py               # Dataclasses: Bid, Lot, BidderProfile, EvaluationResult…
│   ├── scorers.py              # 6 deterministic scoring functions
│   ├── aggregator.py           # Orchestrator: artist matching + per-lot evaluation
│   ├── recommender.py          # Markdown report + summary table
│   ├── email_drafter.py        # Email drafting (LLM or dry-run)
│   ├── odoo_client.py          # Odoo XML-RPC client + local JSON loader
│   └── run_pipeline.py         # CLI entry point
├── data/
│   ├── sample_upcoming_lots.json    # 8 upcoming auction lots
│   ├── sample_past_lots.json        # 65 historical lots (artist index source)
│   └── sample_bidding_history.json  # 15 bidder profiles, 70+ bids
├── tests/
│   ├── test_scorers.py         # 25 unit tests
│   └── test_aggregator.py      # 15 integration tests
├── skills/
│   └── outreach-email/
│       ├── email_tone.md       # Editable tone guidance for LLM email drafting
│       └── outreach_template.md # Email template (used in dry-run mode)
├── docs/
│   └── deveres_project_report.html  # Full project report (open in browser)
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── setup.sh
├── run.sh
├── stop.sh
├── LICENSE
└── CONTRIBUTING.md
```

---

## Troubleshooting

**`./setup.sh` fails with "Python too old"**
Install Python 3.11+: `brew install python@3.13` (macOS) or from python.org.

**Port 8003 already in use**
```bash
./stop.sh          # stop any running instance
lsof -i :8003      # find what's using the port
```

**`./run.sh` exits immediately**
Check that setup completed: `ls .venv/` should show `bin/`, `lib/`.
Re-run `./setup.sh` if not.

**No results after clicking "Run Evaluation"**
The evaluation runs in-process and stores results in memory. If the page reloads, results persist. If the server restarts, run evaluation again. For persistence across restarts, see the API — results can be exported via `/summary`.

**Email drafting shows `[dry_run]`**
This is expected when `VLLM_URL` is not set. Set it to a local Ollama or vLLM server to get LLM-generated emails. See [LLM Email Drafting](#llm-email-drafting-optional).

**Docker build fails on Apple Silicon**
The image is built for `linux/arm64` automatically on Apple Silicon. If you need `linux/amd64`:
```bash
docker build --platform linux/amd64 -t deveres-auction .
```

---

## Optional Enhancements

| Feature | How to enable |
|---------|--------------|
| LLM email drafting | Set `VLLM_URL` to a local Ollama/vLLM server |
| Live Odoo data | Set `ODOO_*` env vars + use `{"use_odoo": true}` |
| Custom scoring weights | Pass `weights` object to `POST /evaluate` |
| Custom data | Point `LOTS_PATH` / `BIDDERS_PATH` env vars at your own JSON files |

---

## Known Limitations

- **In-memory state** — evaluation results are stored in-process memory. Restarting the server clears them. For production, add a database backend.
- **Demo credentials** — the dashboard uses hardcoded credentials. For production, integrate with your authentication system.
- **Odoo model names** — the Odoo client assumes `auction.lot` and `auction.bid` models. Adjust field names to match your Odoo instance.
- **No pagination** — the `/results` endpoint returns all bidders in one response. Add pagination for >500 bidders.

---

## License

MIT — see [LICENSE](LICENSE).

---

Built by [Cimelium](https://cimelium.com) · Deterministic scoring · No GPU required · Runs on any laptop
