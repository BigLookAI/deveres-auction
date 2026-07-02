#!/usr/bin/env bash
# deVeres Auction — One-time setup script
# Works on macOS (Apple Silicon + Intel) and Linux.
# No conda, no DGX, no GPU required.

set -e
cd "$(dirname "$0")"

PYTHON_MIN="3.11"

# ── Colour helpers ────────────────────────────────────────────────────────────
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[0;33m%s\033[0m\n' "$*"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

bold "============================================"
bold "  deVeres Auction — Setup"
bold "============================================"
echo ""

# ── 1. Check Python ───────────────────────────────────────────────────────────
echo "Checking Python..."
if command -v python3 &>/dev/null; then
    PY=$(python3 --version 2>&1 | awk '{print $2}')
    MAJOR=$(echo "$PY" | cut -d. -f1)
    MINOR=$(echo "$PY" | cut -d. -f2)
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
        green "  ✓ Python $PY found"
        PYTHON=python3
    else
        red "  ✗ Python $PY is too old. Python $PYTHON_MIN+ required."
        echo "  Install from https://www.python.org/downloads/"
        exit 1
    fi
else
    red "  ✗ python3 not found. Install Python $PYTHON_MIN+ first."
    echo "  macOS: brew install python"
    echo "  Or:    https://www.python.org/downloads/"
    exit 1
fi

# ── 2. Create virtual environment ────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv .venv
    green "  ✓ Virtual environment created at .venv/"
else
    green "  ✓ Virtual environment already exists"
fi

# ── 3. Activate and install dependencies ─────────────────────────────────────
echo "Installing dependencies..."
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
green "  ✓ Dependencies installed"

# ── 4. Create .env from example if not present ───────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    yellow "  → Created .env from .env.example"
    yellow "    (Edit .env if you want to add optional services like Odoo or an LLM)"
else
    green "  ✓ .env already exists"
fi

# ── 5. Create output directory ───────────────────────────────────────────────
mkdir -p output/reports
green "  ✓ output/ directory ready"

# ── 6. Run tests ─────────────────────────────────────────────────────────────
echo ""
echo "Running test suite..."
if .venv/bin/python -m pytest tests/ -q --tb=short 2>&1; then
    green "  ✓ All tests passed"
else
    red "  ✗ Some tests failed — see output above"
    exit 1
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
bold "============================================"
green "  Setup complete!"
bold "============================================"
echo ""
echo "  Start the service:   ./run.sh"
echo "  Dashboard:           http://localhost:8003/"
echo "  API docs:            http://localhost:8003/docs"
echo "  Run pipeline CLI:    .venv/bin/python -m pipeline.run_pipeline --dry-run"
echo ""
