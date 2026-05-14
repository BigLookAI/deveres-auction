"""
Deviours Auction — Odoo API Client
Fetches upcoming lots and historical bidding data from Odoo via XML-RPC.
Writes evaluation results back to bidder records.

Requires environment variables:
  ODOO_URL      — e.g. https://your-instance.odoo.com
  ODOO_DB       — database name
  ODOO_USERNAME — login email
  ODOO_PASSWORD — API key (Settings > Technical > API Keys)

NOTE: This client is a stub — activate after Carl confirms Odoo data is ready (Wed 13 May).
"""
from __future__ import annotations

import os
import xmlrpc.client
from datetime import datetime, timezone
from typing import Any, Optional

from .models import Bid, BidOutcome, BidderProfile, EvaluationResult, Lot


class OdooClient:
    def __init__(
        self,
        url:      Optional[str] = None,
        db:       Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.url      = url      or os.environ["ODOO_URL"]
        self.db       = db       or os.environ["ODOO_DB"]
        self.username = username or os.environ["ODOO_USERNAME"]
        self.password = password or os.environ["ODOO_PASSWORD"]
        self._uid: Optional[int] = None
        self._models: Optional[xmlrpc.client.ServerProxy] = None

    def _connect(self) -> None:
        if self._uid is not None:
            return
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._uid = common.authenticate(self.db, self.username, self.password, {})
        if not self._uid:
            raise ConnectionError(f"Odoo authentication failed for user {self.username}")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def _execute(self, model: str, method: str, *args, **kwargs) -> Any:
        self._connect()
        return self._models.execute_kw(
            self.db, self._uid, self.password,
            model, method, list(args), kwargs,
        )

    # ── Fetch upcoming lots ───────────────────────────────────────────────────

    def fetch_upcoming_lots(self) -> list[Lot]:
        """
        Fetch upcoming auction lots from Odoo.
        Assumes a custom model 'auction.lot' or equivalent.
        Adjust model name and field names to match your Odoo instance.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        records = self._execute(
            "auction.lot",
            "search_read",
            [[["auction_date", ">=", today], ["state", "=", "open"]]],
            fields=["id", "name", "category_id", "estimate_min", "estimate_max",
                    "reserve_price", "auction_date", "description"],
            limit=200,
        )
        return [
            Lot(
                lot_id        = str(r["id"]),
                title         = r.get("name", ""),
                category      = r.get("category_id", [None, "unknown"])[1].lower()
                                if isinstance(r.get("category_id"), list) else "unknown",
                estimate_low  = float(r.get("estimate_min", 0)),
                estimate_high = float(r.get("estimate_max", 0)),
                reserve_price = float(r.get("reserve_price", 0)),
                auction_date  = str(r.get("auction_date", "")),
                description   = r.get("description", "") or "",
            )
            for r in records
        ]

    # ── Fetch bidding history ─────────────────────────────────────────────────

    def fetch_bidder_profiles(self, limit: int = 500) -> list[BidderProfile]:
        """
        Fetch all bidders with their bidding history.
        Adjust model/field names to match your Odoo 'auction.bid' model.
        """
        bid_records = self._execute(
            "auction.bid",
            "search_read",
            [[]],
            fields=["id", "bidder_id", "lot_id", "amount", "date", "state", "hammer_price"],
            limit=limit * 20,  # fetch many bids, group by bidder
        )

        # Group bids by bidder
        from collections import defaultdict
        bids_by_bidder: dict[str, list[Bid]] = defaultdict(list)
        for r in bid_records:
            bidder_ref = r.get("bidder_id")
            if not bidder_ref:
                continue
            bidder_id = str(bidder_ref[0]) if isinstance(bidder_ref, list) else str(bidder_ref)
            lot_ref   = r.get("lot_id")
            lot_id    = str(lot_ref[0]) if isinstance(lot_ref, list) else str(lot_ref)
            outcome   = BidOutcome.WON if r.get("state") == "won" else BidOutcome.LOST
            bids_by_bidder[bidder_id].append(Bid(
                bid_id      = str(r["id"]),
                bidder_id   = bidder_id,
                lot_id      = lot_id,
                bid_amount  = float(r.get("amount", 0)),
                timestamp   = str(r.get("date", "2000-01-01")),
                outcome     = outcome,
                hammer_price= float(r["hammer_price"]) if r.get("hammer_price") else None,
            ))

        # Fetch partner details for each unique bidder
        bidder_ids_int = [int(k) for k in bids_by_bidder.keys() if k.isdigit()]
        partners = self._execute(
            "res.partner",
            "search_read",
            [[["id", "in", bidder_ids_int]]],
            fields=["id", "name", "email", "country_id", "phone"],
        )
        partner_map = {str(p["id"]): p for p in partners}

        profiles: list[BidderProfile] = []
        for bidder_id, bids in bids_by_bidder.items():
            p = partner_map.get(bidder_id, {})
            profiles.append(BidderProfile(
                bidder_id = bidder_id,
                name      = p.get("name", f"Bidder {bidder_id}"),
                email     = p.get("email", ""),
                bids      = bids,
                country   = p.get("country_id", [None, ""])[1] if isinstance(p.get("country_id"), list) else "",
                phone     = p.get("phone", "") or "",
            ))
        return profiles[:limit]

    # ── Write evaluation results back ─────────────────────────────────────────

    def write_evaluation_results(self, results: list[EvaluationResult]) -> int:
        """
        Write score + recommendation back to res.partner records in Odoo.
        Uses custom fields x_bidder_score, x_evaluation_status, x_evaluated_at.
        Returns number of records updated.
        """
        updated = 0
        for r in results:
            if not r.bidder_id.isdigit():
                continue
            try:
                self._execute(
                    "res.partner",
                    "write",
                    [[int(r.bidder_id)]],
                    {
                        "x_bidder_score":       r.score,
                        "x_evaluation_status":  r.recommendation.value,
                        "x_evaluated_at":       r.evaluated_at,
                    },
                )
                updated += 1
            except Exception:
                pass
        return updated


# ─────────────────────────────────────────────────────────────────────────────
# Local JSON loader (used when Odoo is not yet available)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_lots(lots_raw: list[dict]) -> list[Lot]:
    return [
        Lot(
            lot_id        = r["lot_id"],
            title         = r["title"],
            category      = r["category"],
            estimate_low  = float(r["estimate_low"]),
            estimate_high = float(r["estimate_high"]),
            reserve_price = float(r["reserve_price"]),
            auction_date  = r["auction_date"],
            description   = r.get("description", ""),
            artist        = r.get("artist", ""),
        )
        for r in lots_raw
    ]


def load_past_lots(past_lots_path: str) -> list[Lot]:
    """
    Load historical past lots from a local JSON file.
    Used to build the artist index for per-lot scoring.
    """
    import json
    from pathlib import Path
    raw = json.loads(Path(past_lots_path).read_text())
    return _parse_lots(raw)


def load_from_json(
    lots_path:      str,
    bidders_path:   str,
    past_lots_path: str | None = None,
) -> tuple[list[Lot], list[BidderProfile], list[Lot]]:
    """
    Load upcoming lots, bidder profiles, and optionally past lots from local JSON files.
    Used for development / testing before Odoo integration is live.

    Returns:
        (upcoming_lots, profiles, past_lots)
        past_lots is empty list if past_lots_path is None.
    """
    import json
    from pathlib import Path

    lots_raw    = json.loads(Path(lots_path).read_text())
    bidders_raw = json.loads(Path(bidders_path).read_text())

    lots = _parse_lots(lots_raw)

    past_lots: list[Lot] = []
    if past_lots_path:
        past_lots_raw = json.loads(Path(past_lots_path).read_text())
        past_lots = _parse_lots(past_lots_raw)

    profiles: list[BidderProfile] = []
    for bidder in bidders_raw:
        bids = [
            Bid(
                bid_id      = b["bid_id"],
                bidder_id   = bidder["bidder_id"],
                lot_id      = b["lot_id"],
                bid_amount  = float(b["bid_amount"]),
                timestamp   = b["timestamp"],
                outcome     = BidOutcome(b["outcome"]),
                hammer_price= float(b["hammer_price"]) if b.get("hammer_price") else None,
            )
            for b in bidder.get("bids", [])
        ]
        profiles.append(BidderProfile(
            bidder_id = bidder["bidder_id"],
            name      = bidder["name"],
            email     = bidder["email"],
            bids      = bids,
            country   = bidder.get("country", ""),
        ))
    return lots, profiles, past_lots
