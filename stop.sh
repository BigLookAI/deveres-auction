#!/usr/bin/env bash
echo "Stopping Deviours Auction..."
pkill -f "uvicorn api:app" 2>/dev/null && echo "✓ Stopped" || echo "Not running"
