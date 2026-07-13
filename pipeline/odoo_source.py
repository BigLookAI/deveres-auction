"""
deVeres Bidder Evaluation — LIVE Odoo data source (pilot close-out item).

The 8-Jul session named "bidding history linked into Odoo" as the end of the
pilot: the evaluation app must run on the system of record instead of static
JSON. This module loads the exact same shapes `load_from_json` produces —
(upcoming_lots, bidder_profiles, past_lots) — from Odoo:

  upcoming lots   sor.lot in state live/catalogued (hammer not yet set)
  past lots       sor.lot in state sold/passed
  bidder profiles res.partner grouped from sor.bid rows; a bid is 'won' when
                  is_winning_bid is set (hammer price read from its lot)

Artist/category interim convention: until artworks are modelled end-to-end
(sor_artwork product per lot), the seeders record them on the lot's
internal_notes as "artist: NAME | category: CAT". This parser reads that and
falls back gracefully — a missing artist simply skips artist-affinity scoring
for that lot, exactly like the JSON fixtures with blank artists.

Selection: env BIDDER_DATA_SOURCE=odoo (or a per-request override in the
API). Any Odoo failure raises — the API layer decides whether to fall back
to the JSON fixtures (and says so in the response) — never a silent switch.
"""
from __future__ import annotations

import logging
import re

from .models import Bid, BidderProfile, BidOutcome, Lot

log = logging.getLogger("bidder.odoo")

_NOTE_RE = re.compile(r"artist:\s*(?P<artist>[^|<]+?)\s*(?:\||$).*?"
                      r"(?:category:\s*(?P<category>[^|<]+?)\s*(?:\||$))?",
                      re.I | re.S)

UPCOMING_STATES = ("live", "catalogued")
PAST_STATES = ("sold", "passed")


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _parse_notes(notes: str) -> tuple[str, str]:
    text = _strip_html(notes)
    artist = category = ""
    m = re.search(r"artist:\s*([^|]+)", text, re.I)
    if m:
        artist = m.group(1).strip()
    m = re.search(r"category:\s*([^|]+)", text, re.I)
    if m:
        category = m.group(1).strip()
    return artist, category


def _lot_from_record(rec: dict, auction_dates: dict) -> Lot:
    artist, category = _parse_notes(rec.get("internal_notes") or "")
    auction = rec.get("auction_id") or [None, ""]
    return Lot(
        lot_id=f"ODOO-{rec['id']}",
        title=(rec.get("lot_title") or f"Lot {rec.get('lot_number', '?')}").strip(),
        category=category or "artwork",
        estimate_low=float(rec.get("estimate_low") or 0),
        estimate_high=float(rec.get("estimate_high") or 0),
        reserve_price=float(rec.get("reserve_price") or 0),
        auction_date=auction_dates.get(auction[0], ""),
        description=_strip_html(rec.get("lot_description") or ""),
        artist=artist,
    )


def load_from_odoo(client=None) -> tuple[list[Lot], list[BidderProfile], list[Lot]]:
    if client is None:
        from .odoo_client import OdooClient
        client = OdooClient()

    events = client._execute("sor.event", "search_read",
                             [["event_type", "=", "auction"]],
                             fields=["id", "date_start"], limit=500)
    auction_dates = {e["id"]: (e.get("date_start") or "").replace(" ", "T")
                     for e in events}

    fields = ["id", "lot_number", "lot_title", "lot_description",
              "internal_notes", "estimate_low", "estimate_high",
              "reserve_price", "hammer_price", "state", "auction_id"]
    upcoming_raw = client._execute("sor.lot", "search_read",
                                   [["state", "in", list(UPCOMING_STATES)]],
                                   fields=fields, limit=5000, order="id")
    past_raw = client._execute("sor.lot", "search_read",
                               [["state", "in", list(PAST_STATES)]],
                               fields=fields, limit=5000, order="id")
    upcoming = [_lot_from_record(r, auction_dates) for r in upcoming_raw]
    past = [_lot_from_record(r, auction_dates) for r in past_raw]
    hammer_by_lot = {r["id"]: float(r.get("hammer_price") or 0) for r in past_raw}

    bids_raw = client._execute("sor.bid", "search_read", [],
                               fields=["id", "lot_id", "bidder_id", "amount",
                                       "is_winning_bid", "bid_datetime"],
                               limit=20000, order="id")
    partner_ids = sorted({(b.get("bidder_id") or [None])[0]
                          for b in bids_raw if b.get("bidder_id")})
    partners = {p["id"]: p for p in client._execute(
        "res.partner", "read", [pid for pid in partner_ids if pid],
        fields=["name", "email", "phone", "country_id"])} if partner_ids else {}

    profiles: dict[int, BidderProfile] = {}
    for b in bids_raw:
        pid = (b.get("bidder_id") or [None])[0]
        lot = (b.get("lot_id") or [None])[0]
        if not pid or not lot:
            continue
        p = partners.get(pid, {})
        prof = profiles.setdefault(pid, BidderProfile(
            bidder_id=f"ODOO-{pid}",
            name=p.get("name") or f"Partner {pid}",
            email=p.get("email") or "",
            phone=p.get("phone") or "",
            country=(p.get("country_id") or [None, ""])[1] or ""))
        won = bool(b.get("is_winning_bid"))
        prof.bids.append(Bid(
            bid_id=f"ODOO-B{b['id']}",
            bidder_id=prof.bidder_id,
            lot_id=f"ODOO-{lot}",
            bid_amount=float(b.get("amount") or 0),
            timestamp=(b.get("bid_datetime") or "").replace(" ", "T"),
            outcome=BidOutcome.WON if won else BidOutcome.LOST,
            hammer_price=hammer_by_lot.get(lot) if won else None))

    log.info("odoo source: %d upcoming lots, %d past lots, %d bidders, %d bids",
             len(upcoming), len(past), len(profiles), len(bids_raw))
    return upcoming, list(profiles.values()), past
