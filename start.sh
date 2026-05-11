#!/usr/bin/env bash
# Deviours Auction — Start script
# Completely standalone — no dependency on hero-gallery or sofine-marketing

set -e
cd "$(dirname "$0")"

CONDA_ENV="deviours"
PORT=8003
LOG_FILE="/tmp/deviours.log"

echo "Starting Deviours Auction service on port $PORT..."

source ~/miniconda3/bin/activate "$CONDA_ENV"

# Kill any existing deviours uvicorn
pkill -f "uvicorn api:app" 2>/dev/null || true
sleep 1

nohup uvicorn api:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --reload \
  &> "$LOG_FILE" &

sleep 2

if curl -s "http://localhost:$PORT/health" | grep -q '"ok"'; then
  echo "✓ Deviours Auction running at http://localhost:$PORT"
  echo "  Dashboard:  http://100.101.39.73:$PORT/"
  echo "  API docs:   http://100.101.39.73:$PORT/docs"
  echo "  Logs:       tail -f $LOG_FILE"
else
  echo "✗ Service did not start — check $LOG_FILE"
  tail -20 "$LOG_FILE"
  exit 1
fi
