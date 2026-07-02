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

from .fieldmap import INCOMING_MAP, LOT_MAP, MASTER_MAP
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
