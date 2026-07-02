#!/usr/bin/env bash
# deVeres Auction — Stop both product servers
pkill -f "uvicorn recon_app:app" 2>/dev/null && echo "Contact Reconciliation stopped." || echo "Reconciliation not running."
pkill -f "uvicorn api:app" 2>/dev/null && echo "Bidder Evaluation stopped." || echo "Bidder Evaluation not running."
