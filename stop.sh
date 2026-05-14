#!/usr/bin/env bash
# Deviours Auction — Stop the API server
pkill -f "uvicorn api:app" 2>/dev/null && echo "Deviours Auction stopped." || echo "Not running."
