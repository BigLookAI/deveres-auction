#!/usr/bin/env bash
# deVeres Auction — Start the API server + Dashboard
# Run ./setup.sh once before using this script.

set -e
cd "$(dirname "$0")"

PORT="${PORT:-8003}"
HOST="${HOST:-0.0.0.0}"

# ── Colour helpers ────────────────────────────────────────────────────────────
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

# ── Check setup has been run ──────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    red "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

# ── Load .env if present ──────────────────────────────────────────────────────
if [ -f ".env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source .env
    set +o allexport
fi

# ── Stop any existing instance ────────────────────────────────────────────────
pkill -f "uvicorn api:app" 2>/dev/null && echo "Stopped existing instance." || true

bold ""
bold "  Starting deVeres Auction on port $PORT..."
bold ""

# ── Launch server ─────────────────────────────────────────────────────────────
exec .venv/bin/uvicorn api:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    --log-level info
