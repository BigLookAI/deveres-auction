"""
Deviours Auction — Reconciliation · Repository layer
====================================================

All CSV I/O lives here (repository pattern), so the engine never touches files.

  • MasterRepository — loads the immutable canonical All Clients.csv ONCE and
    builds the blocking index. Baked into the app; never mutated by reconciliation.
  • load_incoming   — parses an uploaded Blue Cubes buyer export, deduplicating
    the per-lot rows down to one record per unique buyer (aggregating their lots).
  • load_lots       — parses a Lot List export, forcing Hammer = 0 (meeting rule).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .fieldmap import INCOMING_MAP, LOT_MAP, MASTER_MAP, SELLER_MAP
from .matching import MasterIndex

_CANON_CONTACT_FIELDS = [
    "client_ref", "title", "first_name", "last_name", "company",
    "email", "phone", "mobile", "address1", "address2", "address3",
    "town", "county", "country", "postcode",
]


def _rows(text_or_path, is_path: bool) -> list[dict]:
    if is_path:
        with open(text_or_path, encoding="utf-8-sig", errors="replace", newline="") as f:
            return list(csv.DictReader(f))
    return list(csv.DictReader(io.StringIO(text_or_path)))


def _map_row(row: dict, colmap: dict) -> dict:
    return {canon: (row.get(col) or "").strip() for canon, col in colmap.items()}


class MasterRepository:
    """The canonical client database (source of truth). Read-only."""

    def __init__(self, records: list[dict]):
        self.records = records
        self.index = MasterIndex(records)

    @classmethod
    def from_csv(cls, path: str | Path) -> "MasterRepository":
        recs = [_map_row(r, MASTER_MAP) for r in _rows(str(path), is_path=True)]
        # keep only fields we reason about, plus a stable ref
        for i, r in enumerate(recs):
            r.setdefault("client_ref", str(i + 1))
        return cls(recs)

    def __len__(self) -> int:
        return len(self.records)


def load_incoming(text_or_path, is_path: bool = True) -> list[dict]:
    """Parse the uploaded Blue Cubes export → one aggregated contact per buyer.

    The export is per-LOT (a buyer repeats across the lots they won), so we group
    by Buyer Number, take the first non-empty value for each contact field, and
    collect the buyer's lots + winning bids for context.
    """
    raw = _rows(text_or_path, is_path)
    by_buyer: dict[str, dict] = {}
    for r in raw:
        m = _map_row(r, INCOMING_MAP)
        key = m.get("buyer_number") or f"row-{len(by_buyer)}"
        rec = by_buyer.setdefault(key, {
            "buyer_number": key,
            **{f: "" for f in _CANON_CONTACT_FIELDS},
            "lots": [],
        })
        for f in _CANON_CONTACT_FIELDS:
            if not rec.get(f) and m.get(f):
                rec[f] = m[f]
        if m.get("lot_number") or m.get("winning_bid"):
            rec["lots"].append({
                "lot_number": m.get("lot_number", ""),
                "lot_title": m.get("lot_title", ""),
                "winning_bid": m.get("winning_bid", ""),
            })
    return list(by_buyer.values())


def detect_format(text_or_path, is_path: bool = True) -> str:
    """Sniff which Blue Cubes export was uploaded from its header row.
    Returns 'buyers' (per-lot buyer export), 'sellers' (seller list), or 'unknown'."""
    rows = _rows(text_or_path, is_path)
    headers = set(rows[0].keys()) if rows else set()
    if {"Buyer Number", "Winning Bid"} <= headers:
        return "buyers"
    if {"Seller Ref", "Commission"} <= headers or {"Seller Ref", "Telephone"} <= headers:
        return "sellers"
    return "unknown"


def load_sellers(text_or_path, is_path: bool = True) -> list[dict]:
    """Parse a Seller List export → one canonical contact per seller.
    Sellers have no lots/bids in this export; they reconcile like any contact."""
    out = []
    for r in _rows(text_or_path, is_path):
        m = _map_row(r, SELLER_MAP)
        if not any(m.get(f) for f in ("first_name", "last_name", "email", "company")):
            continue   # skip blank/padding rows
        rec = {"buyer_number": m.get("buyer_number", ""),
               **{f: "" for f in _CANON_CONTACT_FIELDS}, "lots": []}
        for f in _CANON_CONTACT_FIELDS:
            if m.get(f):
                rec[f] = m[f]
        out.append(rec)
    return out


def load_upload(text: str) -> tuple[str, list[dict]]:
    """Auto-detect an uploaded export's format and parse it accordingly.
    Returns (kind, records) where kind ∈ {'buyers','sellers'}. Raises ValueError
    on an unrecognised header row, listing what we expected."""
    kind = detect_format(text, is_path=False)
    if kind == "buyers":
        return kind, load_incoming(text, is_path=False)
    if kind == "sellers":
        return kind, load_sellers(text, is_path=False)
    raise ValueError("Unrecognised CSV format — expected a Blue Cubes buyer export "
                     "(Buyer Number / Winning Bid columns) or a Seller List export "
                     "(Seller Ref / Telephone columns).")


def load_lots(text_or_path, is_path: bool = True) -> list[dict]:
    """Parse a Lot List export. HAMMER IS FORCED TO 0 regardless of the export
    value (auction-import rule from the 1-Jul meeting)."""
    lots = []
    for r in _rows(text_or_path, is_path):
        m = _map_row(r, LOT_MAP)
        m["hammer_export"] = m.get("hammer", "")   # keep original for audit
        m["hammer"] = 0                            # ← forced zero on import
        lots.append(m)
    return lots
