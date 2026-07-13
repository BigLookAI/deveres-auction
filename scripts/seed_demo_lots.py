#!/usr/bin/env python3
"""
deVeres — seed auction Lots into the DEMO Odoo for the Lot-Reconciliation
pipeline (Phase 11/12 of the 7-Jul follow-up plan).

Creates one demo auction (sor.event) + 50 Live lots (numbers 101–151) with
estimates and reserves set, hammer price 0 and no buyer — an auction before
completion. Lot numbers cover the synthetic Blue Cubes sample export so the
full pipeline can be demonstrated end-to-end.

Two DELIBERATE edge cases for the exception workflow (--no-edge-cases to skip):
  • lot 112 is NOT seeded          → the sample import shows a Missing Lot
    exception (never auto-created — user action required, per the brief)
  • lot 105 also exists in a SECOND auction (Odoo enforces uniqueness only
    within one auction) → cross-auction duplicate detection → manual review

Idempotent: lots are resolved by (auction, lot_number[, title]) before create.
Refuses to run against a non-demo database.

Env: ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import xmlrpc.client

URL = os.environ.get("ODOO_URL", "http://localhost:8071")
DB = os.environ.get("ODOO_DB", "deveres_demo")
USER = os.environ.get("ODOO_USERNAME", "admin")
PWD = os.environ.get("ODOO_PASSWORD", "admin")

AUCTION_NAME = "deVeres Demo Auction — July 2026"
TITLES = ["Irish Landscape, oil on canvas", "Georgian Silver Teapot", "Bronze Figure Study",
          "Victorian Mahogany Desk", "Abstract Composition", "West of Ireland Seascape",
          "Cut Crystal Decanter Set", "Portrait of a Lady", "Art Deco Table Lamp",
          "Still Life with Fruit", "Connemara Marble Clock", "Botanical Watercolour",
          "First-Edition Volume", "Regency Card Table", "Stained Glass Panel"]

if not DB.startswith("deveres_demo"):
    sys.exit(f"refusing: ODOO_DB={DB!r} is not the demo database")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--no-edge-cases", action="store_true")
    args = ap.parse_args()

    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, PWD, {})
    if not uid:
        sys.exit("Odoo auth failed")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

    def x(model, method, *a, **kw):
        return models.execute_kw(DB, uid, PWD, model, method, list(a), kw)

    ev = x("sor.event", "search", [["name", "=", AUCTION_NAME]], limit=1)
    auction_id = ev[0] if ev else x("sor.event", "create", {
        "name": AUCTION_NAME, "event_type": "auction",   # required selection
        "date_start": "2026-07-07 14:00:00"})            # required datetime
    print(f"auction: {AUCTION_NAME} (id {auction_id})")

    rng = random.Random(20260707)
    created = existing = 0
    numbers = [n for n in range(101, 101 + args.count + 1)]
    skip = {112} if not args.no_edge_cases else set()

    def make(lot_number: int, title: str) -> None:
        nonlocal created, existing
        dom = [["auction_id", "=", auction_id],
               ["lot_number", "=", str(lot_number)],
               ["lot_title", "=", title]]
        if x("sor.lot", "search", dom, limit=1):
            existing += 1
            return
        low = rng.choice([100, 150, 200, 300, 500, 800, 1200, 2000])
        x("sor.lot", "create", {
            "auction_id": auction_id,
            "lot_number": str(lot_number),
            "lot_title": title,
            "estimate_low": low,
            "estimate_high": int(low * rng.choice([1.5, 2, 2.5])),
            "reserve_price": int(low * 0.8),
            "hammer_price": 0.0,          # before completion — the import fills it
            "state": "live",              # active auction
        })
        created += 1

    for n in numbers:
        if n in skip:
            continue
        make(n, f"Lot {n} — {TITLES[n % len(TITLES)]}")
    if not args.no_edge_cases:
        # Odoo enforces lot-number uniqueness WITHIN an auction, so the
        # duplicate seed lives in a second auction — the realistic collision.
        ev2 = x("sor.event", "search", [["name", "=", "deVeres Demo Auction — Edge Cases"]], limit=1)
        ev2_id = ev2[0] if ev2 else x("sor.event", "create", {
            "name": "deVeres Demo Auction — Edge Cases",
            "event_type": "auction", "date_start": "2026-07-01 14:00:00"})
        if not x("sor.lot", "search", [["auction_id", "=", ev2_id],
                                       ["lot_number", "=", "105"]], limit=1):
            x("sor.lot", "create", {
                "auction_id": ev2_id, "lot_number": "105",
                "lot_title": "Lot 105 — cross-auction DUPLICATE (review demo)",
                "estimate_low": 100, "estimate_high": 200, "reserve_price": 80,
                "hammer_price": 0.0, "state": "live"})
            created += 1
        print("edge cases: lot 112 omitted (missing-lot demo), lot 105 duplicated across auctions")

    total = x("sor.lot", "search_count", [["auction_id", "=", auction_id]])
    live = x("sor.lot", "search_count", [["auction_id", "=", auction_id], ["state", "=", "live"]])
    print(f"seeded: {created} created, {existing} already present — "
          f"{total} lots in the demo auction ({live} live, hammer=0, no buyer)")


if __name__ == "__main__":
    main()
