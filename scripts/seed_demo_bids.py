#!/usr/bin/env python3
"""
deVeres — seed BIDDING HISTORY + an upcoming auction into the DEMO Odoo, so
the Bidder Evaluation app runs on the live system of record (pilot close-out:
"bidding history linked into Odoo").

Creates (idempotently, demo database only):
  1. an UPCOMING auction ("… September 2026") with 12 catalogued lots carrying
     artist + category on internal_notes ("artist: X | category: Y" — the
     interim convention until artworks are modelled per-lot),
  2. artist/category notes on the July auction's sold lots (past-lot pool),
  3. sor.bid history: for every sold lot, the winning bid by its actual buyer
     plus 1–2 underbids from other demo partners — deterministic RNG.

Env: ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD.
"""
from __future__ import annotations

import os
import random
import sys
import xmlrpc.client

URL = os.environ.get("ODOO_URL", "http://localhost:8071")
DB = os.environ.get("ODOO_DB", "deveres_demo")
USER = os.environ.get("ODOO_USERNAME", "admin")
PWD = os.environ.get("ODOO_PASSWORD", "admin")

if not (DB.startswith("deveres_demo") or DB.startswith("deveres_bidding")):
    sys.exit(f"refusing: ODOO_DB={DB!r} is not a synthetic sandbox database")

UPCOMING = "deVeres Demo Auction — September 2026"
ARTISTS = ["Séamus Ó Colmáin", "Aoibhinn Walsh", "Deirdre Ní Bhriain",
           "Pádraig MacSuibhne", "Nuala Redmond", "Colm Gallagher"]
CATS = ["painting", "print", "sculpture", "furniture", "silver", "ceramics"]
UPCOMING_LOTS = [
    ("201", "Evening over Killary Harbour", 0, 0), ("202", "Dublin Quays, Etching II", 1, 1),
    ("203", "Bronze Study of a Dancer", 2, 2), ("204", "Regency Side Table", 3, 3),
    ("205", "Georgian Cream Jug", 4, 4), ("206", "Abstract in Ochre", 0, 0),
    ("207", "Wicklow Uplands, watercolour", 1, 0), ("208", "Figure in Repose", 2, 2),
    ("209", "Set of Six Dining Chairs", 3, 3), ("210", "Celtic Revival Bowl", 5, 5),
    ("211", "Storm at Hook Head", 0, 0), ("212", "Limited Print: Liffey Bridges", 1, 1),
]


def main() -> None:
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, PWD, {})
    if not uid:
        sys.exit("Odoo auth failed")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

    def x(model, method, *a, **kw):
        return models.execute_kw(DB, uid, PWD, model, method, list(a), kw)

    rng = random.Random(20260713)

    # 0. a PAST auction with results (whiteboard 14-Jul: past + future =
    #    different data). On the demo db sold lots come from reconciliation
    #    pushes; on a fresh bidding sandbox nothing is sold yet — close the
    #    July auction deterministically: ~60% of lots sold to seeded partners
    #    at a hammer between the estimates. Idempotent: skips if sales exist.
    if not x("sor.lot", "search", [["state", "=", "sold"]], limit=1):
        past = x("sor.event", "search",
                 [["name", "like", "deVeres Demo Auction — July%"]], limit=1)
        if past:
            plots = x("sor.lot", "search_read",
                      [["auction_id", "=", past[0]], ["state", "!=", "withdrawn"]],
                      fields=["id", "lot_number", "estimate_low", "estimate_high"],
                      order="id")
            buyers = x("res.partner", "search",
                       [["is_company", "=", False],
                        ["email", "like", "@example.test"]], limit=400)
            closed = 0
            for l in plots:
                if rng.random() > 0.6 or not buyers:
                    continue
                low = float(l.get("estimate_low") or 300)
                high = float(l.get("estimate_high") or low * 1.8)
                hammer = round(rng.uniform(low * 0.9, high * 1.1) / 10) * 10
                x("sor.lot", "write", [l["id"]],
                  {"hammer_price": hammer, "buyer_id": rng.choice(buyers),
                   "state": "sold", "auction_result": "sold"})
                closed += 1
            print(f"past auction id {past[0]}: {closed} lots closed as sold")

    # 1. upcoming auction + lots
    ev = x("sor.event", "search", [["name", "=", UPCOMING]], limit=1)
    ev_id = ev[0] if ev else x("sor.event", "create", {
        "name": UPCOMING, "event_type": "auction",
        "date_start": "2026-09-18 14:00:00"})
    created = 0
    for num, title, ai, ci in UPCOMING_LOTS:
        if x("sor.lot", "search", [["auction_id", "=", ev_id],
                                   ["lot_number", "=", num]], limit=1):
            continue
        low = rng.choice([400, 600, 900, 1500, 2500, 4000])
        x("sor.lot", "create", {
            "auction_id": ev_id, "lot_number": num, "lot_title": title,
            "estimate_low": low, "estimate_high": int(low * 1.8),
            "reserve_price": int(low * 0.85),
            "hammer_price": 0.0, "state": "catalogued",
            "internal_notes": f"artist: {ARTISTS[ai]} | category: {CATS[ci]}",
        })
        created += 1
    print(f"upcoming auction id {ev_id}: {created} lots created "
          f"({x('sor.lot','search_count',[['auction_id','=',ev_id]])} total)")

    # 2. artist/category notes on the July sold lots (the past pool)
    sold = x("sor.lot", "search_read", [["state", "=", "sold"]],
             fields=["id", "lot_number", "internal_notes", "buyer_id",
                     "hammer_price", "reserve_price"])
    noted = 0
    for l in sold:
        if "artist:" in str(l.get("internal_notes") or ""):
            continue
        ai = rng.randrange(len(ARTISTS)); ci = rng.randrange(len(CATS))
        x("sor.lot", "write", [l["id"]],
          {"internal_notes": f"artist: {ARTISTS[ai]} | category: {CATS[ci]}"})
        noted += 1
    print(f"annotated {noted} sold lots with artist/category")

    # 3. bidding history on the sold lots
    partners = x("res.partner", "search",
                 [["is_company", "=", False], ["email", "like", "@example.test"]],
                 limit=400)
    made = 0
    for l in sold:
        if x("sor.bid", "search", [["lot_id", "=", l["id"]]], limit=1):
            continue
        hammer = float(l.get("hammer_price") or 0)
        buyer = (l.get("buyer_id") or [None])[0]
        if not hammer:
            continue
        when = f"2026-07-11 {rng.randrange(14,17):02d}:{rng.randrange(60):02d}:00"
        if buyer:
            x("sor.bid", "create", {
                "lot_id": l["id"], "bidder_id": buyer, "amount": hammer,
                "bid_type": "floor", "is_winning_bid": True,
                "bid_datetime": when})
            made += 1
        for _ in range(rng.randrange(1, 3)):          # underbidders
            ub = rng.choice(partners)
            if ub == buyer:
                continue
            x("sor.bid", "create", {
                "lot_id": l["id"], "bidder_id": ub,
                "amount": round(hammer * rng.uniform(0.55, 0.95), 0),
                "bid_type": rng.choice(["floor", "phone", "absentee", "online"]),
                "is_winning_bid": False, "bid_datetime": when})
            made += 1
    total = x("sor.bid", "search_count", [])
    print(f"bids created: {made} (total sor.bid rows: {total})")


if __name__ == "__main__":
    main()
