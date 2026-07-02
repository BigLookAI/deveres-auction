#!/usr/bin/env bash
# deVeres Auction — Stop the API server
pkill -f "uvicorn api:app" 2>/dev/null && echo "deVeres Auction stopped." || echo "Not running."
