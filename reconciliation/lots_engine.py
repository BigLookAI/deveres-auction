"""
deVeres Auction — Lot Reconciliation Engine (Phase 11+ of the 7-Jul plan)
==========================================================================

Stage 2 of the Blue Cubes import: after contacts are reconciled and pushed,
the SAME upload's per-lot rows drive the auction-result import:

    find the Odoo lot by LOT NUMBER (primary key — never title alone)
      → update Hammer Price = Winning Bid          (implemented now)
      → assign Buyer = matched contact             (feature-flagged: deferred)
      → set State = Sold                           (feature-flagged: deferred)

The 1.44pm 7-Jul meeting confirmed the demo Odoo is not yet configured for
buyer assignment / Sold transitions from the UI (no bid structure, pending
admin access) — so those two writes sit behind env flags, OFF by default:

    RECON_LOTS_ENABLE_BUYER=1   also write buyer_id for confident matches
    RECON_LOTS_ENABLE_SOLD=1    also set state='sold' + auction_result='sold'

Exception rules (from the brief):
  • Missing lot number in Odoo   → exception, NEVER auto-created
  • Duplicate Odoo lots (same number, several records) → manual review
  • Conflicting results (two different winning bids for one lot; or a lot
    whose hammer is already set to a different value) → manual review
  • Hammer already equals the winning bid → already imported (idempotent)

Buyer matching REUSES the contact engine's outcome: every lot row belongs to
a buyer record in the contact session, which carries the match score, the
matched partner and the workflow state. A buyer is "confident" only when the
contact is linked to a known Odoo partner (pushed/matched ≥ MATCH threshold).

Safety mirrors the contact importer: plan → dry-run default → live only with
RECON_ALLOW_ODOO_WRITE=1 → per-op read-back verification → append-only audit.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("reconcile.lots")

BUYER_CONFIDENCE_FLOOR = 0.90


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("€", "").strip() or 0)
    except ValueError:
        return 0.0


def flags() -> dict:
    return {"buyer": os.environ.get("RECON_LOTS_ENABLE_BUYER") == "1",
            "sold": os.environ.get("RECON_LOTS_ENABLE_SOLD") == "1"}


# ── Odoo side ─────────────────────────────────────────────────────────────────
# lot_suffix was REMOVED upstream in sor_events_auction 19.0.1.1.0 — suffix
# lots ("25A") now live combined in lot_number, matching the Blue Cubes export
# shape. Older databases may still carry the split field, so it is requested
# only when the target schema has it.
LOT_FIELDS = ["id", "lot_number", "lot_title", "state",
              "hammer_price", "buyer_id", "auction_id"]


def _lot_fields(client) -> list[str]:
    try:
        schema = client._execute("sor.lot", "fields_get", ["lot_suffix"])
    except Exception:                                     # noqa: BLE001
        schema = {}
    return LOT_FIELDS + (["lot_suffix"] if "lot_suffix" in (schema or {}) else [])

import re as _re


def lot_key(number, suffix: str = "") -> str:
    """Canonical matching key for a lot number. Handles the real-world suffix
    lots the April data exposed (25A, 78B): Blue Cubes exports the combined
    form ("25A"), Odoo stores number and suffix separately. Numeric parts are
    compared without leading zeros; suffixes case-insensitively."""
    raw = f"{number or ''}{suffix or ''}".strip().upper().replace(" ", "")
    m = _re.match(r"^0*(\d+)([A-Z]*)$", raw)
    return f"{m.group(1)}{m.group(2)}" if m else raw


def fetch_lots(client=None, auction_id: int | None = None) -> list[dict]:
    """Lots from Odoo — optionally scoped to ONE auction so an import can
    never touch another sale's lots (production behaviour; unscoped remains
    available for the cross-auction duplicate check)."""
    if client is None:
        from pipeline.odoo_client import OdooClient
        client = OdooClient()
    domain = [["auction_id", "=", int(auction_id)]] if auction_id else []
    rows = client._execute("sor.lot", "search_read", domain,
                           fields=_lot_fields(client), limit=10000, order="id")
    for r in rows:
        r["lot_number"] = str(r.get("lot_number") or "").strip()
        r["lot_suffix"] = str(r.get("lot_suffix") or "").strip()
        r["match_key"] = lot_key(r["lot_number"], r["lot_suffix"])
    return rows


def fetch_auctions(client=None) -> list[dict]:
    """Auctions with lot counts — drives the UI's target-auction selector."""
    if client is None:
        from pipeline.odoo_client import OdooClient
        client = OdooClient()
    events = client._execute("sor.event", "search_read",
                             [["event_type", "=", "auction"]],
                             fields=["id", "name"], limit=200, order="id")
    counts = client._execute("sor.lot", "read_group", [],
                             ["auction_id"], ["auction_id"])
    by_id = {}
    for c in counts:
        aid = (c.get("auction_id") or [None])[0]
        if aid:
            by_id[aid] = c.get("auction_id_count", 0)
    return [{"id": e["id"], "name": e["name"], "lots": by_id.get(e["id"], 0)}
            for e in events]


# ── reconciliation ────────────────────────────────────────────────────────────
@dataclass
class LotResult:
    lot_number:   str
    lot_title:    str            # from the Blue Cubes export
    winning_bid:  float
    status:       str            # ready|missing_lot|duplicate_lot|conflict|already_imported|no_result
    reason:       str
    # buyer (carried from the contact reconciliation)
    buyer_number: str = ""
    buyer_name:   str = ""
    buyer_partner_id: int | None = None
    buyer_match:  float = 0.0
    buyer_state:  str = ""
    buyer_confident: bool = False
    # Odoo side
    odoo_lot_id:  int | None = None
    odoo_state:   str = ""
    odoo_hammer:  float = 0.0
    odoo_title:   str = ""
    candidates:   list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "lot_number", "lot_title", "winning_bid", "status", "reason",
            "buyer_number", "buyer_name", "buyer_partner_id", "buyer_match",
            "buyer_state", "buyer_confident", "odoo_lot_id", "odoo_state",
            "odoo_hammer", "odoo_title", "candidates")}


def _buyer_context(contact_result, staged_partners: dict | None = None) -> dict:
    """What the contact engine knows about this lot's buyer. A brand-new
    client created by the contact push has no master match — its partner id
    lives in staging (odoo_partner_id on the pushed row). That identity is
    ours by construction, so it counts as fully confident."""
    r = contact_result
    partner = (r.master or {}).get("odoo_id")
    match = round(float(r.confidence), 4)
    confident = bool(partner) and float(r.confidence) >= BUYER_CONFIDENCE_FLOOR
    if not partner and staged_partners:
        created = staged_partners.get(r.buyer_number)
        if created:
            partner, match, confident = created, 1.0, True
    return {
        "buyer_number": r.buyer_number,
        "buyer_name": r.incoming_name,
        "buyer_partner_id": int(partner) if partner else None,
        "buyer_match": match,
        "buyer_state": r.state.value if hasattr(r.state, "value") else str(r.state),
        "buyer_confident": confident,
    }


def reconcile_lots(contact_results: list, odoo_lots: list[dict],
                   staged_partners: dict | None = None) -> list[LotResult]:
    """Match every lot row in the session's upload against the Odoo lots."""
    by_number: dict[str, list[dict]] = {}
    for l in odoo_lots:
        key = l.get("match_key") or lot_key(l.get("lot_number"), l.get("lot_suffix", ""))
        if key:
            by_number.setdefault(key, []).append(l)

    # collect (lot row, owning contact) pairs; detect in-file duplicates
    rows: list[tuple[dict, object]] = []
    seen_bids: dict[str, set[float]] = {}
    for r in contact_results:
        for lot in (r.lots or []):
            rows.append((lot, r))
            n = lot_key(lot.get("lot_number"))
            if n:
                seen_bids.setdefault(n, set()).add(_num(lot.get("winning_bid")))

    out: list[LotResult] = []
    for lot, contact in rows:
        display = str(lot.get("lot_number") or "").strip()
        number = lot_key(display)
        bid = _num(lot.get("winning_bid"))
        base = dict(lot_number=display or number, lot_title=lot.get("lot_title") or "",
                    winning_bid=bid, **_buyer_context(contact, staged_partners))
        if not number or not bid:
            out.append(LotResult(**base, status="no_result",
                                 reason="row carries no lot number / winning bid — nothing to import"))
            continue
        if len(seen_bids.get(number, set())) > 1:
            out.append(LotResult(**base, status="conflict",
                                 reason=f"conflicting auction results: the upload contains "
                                        f"{len(seen_bids[number])} different winning bids for lot {number} "
                                        f"— resolve in Blue Cubes before importing"))
            continue
        cands = by_number.get(number, [])
        if not cands:
            out.append(LotResult(**base, status="missing_lot",
                                 reason=f"Missing Lot — lot {number} does not exist in Odoo. "
                                        f"Cannot import; user action required (lots are never "
                                        f"created automatically)."))
            continue
        if len(cands) > 1:
            out.append(LotResult(**base, status="duplicate_lot",
                                 reason=f"Duplicate lots — {len(cands)} Odoo lots share number "
                                        f"{number} (ids {[c['id'] for c in cands]}). Manual review: "
                                        f"resolve the duplicate before importing.",
                                 candidates=[c["id"] for c in cands]))
            continue
        odoo = cands[0]
        hammer = float(odoo.get("hammer_price") or 0)
        enriched = dict(base, odoo_lot_id=odoo["id"],
                        odoo_state=odoo.get("state") or "",
                        odoo_hammer=hammer,
                        odoo_title=odoo.get("lot_title") or "")
        if hammer and abs(hammer - bid) < 0.005:
            out.append(LotResult(**enriched, status="already_imported",
                                 reason="hammer price already equals the winning bid — nothing to do (idempotent)"))
        elif hammer:
            out.append(LotResult(**enriched, status="conflict",
                                 reason=f"conflicting hammer price: Odoo already records "
                                        f"€{hammer:,.0f} but the import says €{bid:,.0f} — manual review"))
        else:
            out.append(LotResult(**enriched, status="ready",
                                 reason="lot located by number · hammer price will be set from the winning bid"))
    return out


def summarize(results: list[LotResult]) -> dict:
    s = {"total": len(results)}
    for k in ("ready", "missing_lot", "duplicate_lot", "conflict",
              "already_imported", "no_result"):
        s[k] = sum(1 for r in results if r.status == k)
    s["buyer_confident"] = sum(1 for r in results if r.status == "ready" and r.buyer_confident)
    s["flags"] = flags()
    return s


# ── push (hammer now; buyer/sold behind flags) ────────────────────────────────
def plan_updates(results: list[LotResult]) -> list[dict]:
    f = flags()
    ops = []
    for r in results:
        if r.status != "ready":
            continue
        values: dict = {"hammer_price": r.winning_bid}
        applied = ["hammer_price"]
        deferred = []
        if f["buyer"] and r.buyer_confident and r.buyer_partner_id:
            values["buyer_id"] = r.buyer_partner_id
            applied.append("buyer_id")
        elif r.buyer_partner_id:
            deferred.append(f"buyer_id={r.buyer_partner_id} ({r.buyer_name}, "
                            f"match {r.buyer_match:.0%})")
        if f["sold"]:
            values["state"] = "sold"
            values["auction_result"] = "sold"
            applied += ["state", "auction_result"]
        else:
            deferred.append("state=sold")
        ops.append({"lot_id": r.odoo_lot_id, "lot_number": r.lot_number,
                    "values": values, "applied": applied, "deferred": deferred,
                    "buyer_name": r.buyer_name, "winning_bid": r.winning_bid})
    return ops


def bidding_installed(client) -> bool:
    """True when the target Odoo carries the sor_bidding module. The deVeres
    production assembly (deveres.yaml v1.1, Sprint 24) intentionally ships
    WITHOUT sor_bidding — buyer/sold live directly on sor.lot there, and no
    sor.bid record can (or should) be written."""
    try:
        return bool(client._execute(
            "ir.module.module", "search",
            [["name", "=", "sor_bidding"], ["state", "=", "installed"]], limit=1))
    except Exception:                                     # noqa: BLE001
        return False


def execute_updates(ops: list[dict], client=None, dry_run: bool = True) -> dict:
    """Apply the lot updates. Per-op isolation + read-back verification, same
    safety envelope as the contact importer."""
    if not dry_run and os.environ.get("RECON_ALLOW_ODOO_WRITE") != "1":
        raise PermissionError("Refusing live Odoo write: set RECON_ALLOW_ODOO_WRITE=1.")
    if client is None and not dry_run:
        from pipeline.odoo_client import OdooClient
        client = OdooClient()
    can_bid = bidding_installed(client) if not dry_run else False
    written = errors = verified = 0
    for op in ops:
        op["dry_run"] = dry_run
        if dry_run:
            op["result"] = "planned"
            continue
        try:
            client._execute("sor.lot", "write", [op["lot_id"]], op["values"])
            written += 1
            # Sold-workflow decision (13-Jul): when the completion writes a
            # buyer + sold, also record the WINNING BID so the SOR bidding
            # model stays canonical and the evaluation history accumulates.
            # Only where sor_bidding exists — the deVeres production stack
            # ships without it, and the lot write alone is complete there.
            if op["values"].get("state") == "sold" and op["values"].get("buyer_id"):
                if not can_bid:
                    op["winning_bid_skipped"] = "sor_bidding not installed"
                elif not client._execute("sor.bid", "search",
                                         [["lot_id", "=", op["lot_id"]],
                                          ["is_winning_bid", "=", True]], limit=1):
                    client._execute("sor.bid", "create", {
                        "lot_id": op["lot_id"],
                        "bidder_id": op["values"]["buyer_id"],
                        "amount": op["values"].get("hammer_price", 0.0),
                        "bid_type": "floor", "is_winning_bid": True})
                    op["winning_bid_created"] = True
            got = client._execute("sor.lot", "read", [op["lot_id"]],
                                  fields=list(op["values"]))[0]
            mism = {}
            for k, want in op["values"].items():
                have = got.get(k)
                if isinstance(have, (list, tuple)) and len(have) == 2:
                    have = have[0]
                if isinstance(want, float):
                    ok = abs(float(have or 0) - want) < 0.005
                else:
                    ok = (have or "") == (want or "")
                if not ok:
                    mism[k] = {"wrote": want, "read_back": have}
            op["verified"] = not mism
            op["verify_mismatch"] = mism
            verified += not mism
            op["result"] = "written"
        except Exception as exc:                          # noqa: BLE001
            errors += 1
            op["result"] = "error"
            op["error"] = f"{type(exc).__name__}: {exc}"
            log.exception("lot import FAILED lot=%s", op["lot_number"])
    return {"summary": {"dry_run": dry_run, "planned": len(ops),
                        "written": written, "verified": verified,
                        "error": errors, "flags": flags()},
            "operations": ops}
