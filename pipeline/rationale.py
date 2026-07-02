"""
deVeres Auction — NLP Rationale Module
Generates human-readable explanations for bidder shortlisting decisions.

Architecture (from May 18 2026 meeting):
  - Primary LLM : Gemma4 (vLLM /generate endpoint on DGX)
  - Fallback     : Deterministic template generation
  - Pattern      : Bidder use case first (deterministic); artist sourcing uses same pattern

Hierarchy exposed to auctioneer:
  Layer 1 — Proposed bidder (existing list)
  Layer 2 — Natural language rationale (this module)
  Layer 3 — Expandable source data table (build_source_table)
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from .models import (
    Bid, BidOutcome, EvaluationResult, PriceBandTrajectory, Recommendation
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry-points
# ─────────────────────────────────────────────────────────────────────────────

def generate_rationale(
    result: EvaluationResult,
    artist_bids: list[Bid] | None = None,
    gemma4_url: str = "http://localhost:8000/generate",
) -> str:
    """
    Generate a natural language rationale explaining why this bidder was shortlisted.
    Tries Gemma4 first; falls back to deterministic template if LLM unavailable.
    """
    bids = artist_bids or []
    rationale = _try_llm_rationale(result, bids, gemma4_url)
    if rationale:
        return rationale
    return _template_rationale(result, bids)


def build_source_table(
    result: EvaluationResult,
    artist_bids: list[Bid],
    lots_by_id: dict,
) -> list[dict]:
    """
    Build the expandable 'See Sources' data table for a bidder.
    Returns only the bids relevant to the matched artists / lots.
    Ordered chronologically descending (most recent first).
    """
    rows = []
    for bid in sorted(artist_bids, key=lambda b: b.timestamp, reverse=True):
        lot = lots_by_id.get(bid.lot_id)
        lot_title    = lot.title  if lot and hasattr(lot, "title")  else bid.lot_id
        lot_artist   = lot.artist if lot and hasattr(lot, "artist") else ""
        estimate_str = (
            f"€{lot.estimate_low:,.0f}–€{lot.estimate_high:,.0f}"
            if lot and hasattr(lot, "estimate_low") else "N/A"
        )
        rows.append({
            "bid_id":       bid.bid_id,
            "lot_id":       bid.lot_id,
            "lot_title":    lot_title,
            "artist":       lot_artist,
            "bid_amount":   bid.bid_amount,
            "outcome":      bid.outcome.value,
            "hammer_price": bid.hammer_price,
            "timestamp":    bid.timestamp[:10] if bid.timestamp else "",
            "estimate":     estimate_str,
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# LLM-based generation (Gemma4)
# ─────────────────────────────────────────────────────────────────────────────

def _try_llm_rationale(
    result: EvaluationResult,
    artist_bids: list[Bid],
    gemma4_url: str,
) -> str | None:
    """POST to Gemma4 /generate endpoint. Returns None on any failure."""
    prompt = _build_prompt(result, artist_bids)
    try:
        resp = requests.post(
            gemma4_url,
            json={
                "prompt":      prompt,
                "max_tokens":  280,
                "temperature": 0.25,
                "stop":        ["\n\n", "Bidder:", "##"],
            },
            timeout=12,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Handle different vLLM response shapes
            text = (
                data.get("text") or
                data.get("generated_text") or
                data.get("response") or
                (data.get("choices") or [{}])[0].get("text", "")
            )
            text = text.strip()
            if len(text) > 60:
                return text
    except Exception as exc:
        logger.debug("Gemma4 rationale unavailable: %s", exc)
    return None


def _build_prompt(result: EvaluationResult, artist_bids: list[Bid]) -> str:
    b = result.breakdown
    wins   = [bd for bd in artist_bids if bd.outcome == BidOutcome.WON]
    bid_vals = [bd.bid_amount for bd in artist_bids]
    avg_bid  = sum(bid_vals) / len(bid_vals) if bid_vals else 0
    max_bid  = max(bid_vals)                 if bid_vals else 0
    lot_names = ", ".join(list({ml.title for ml in result.matched_lots})[:3]) or "N/A"
    raw_win_rate = (b.total_wins / b.total_bids * 100) if b.total_bids else 0.0
    top = result.per_lot_scores[0] if result.per_lot_scores else None
    top_lot = f"{top.title} by {top.artist} (lot score {top.score:.2f})" if top else "N/A"

    return (
        f"You are an expert art auction analyst.\n"
        f"Write a concise 2–3 sentence plain English rationale (no bullet points, no markdown) "
        f"explaining specifically why this bidder was shortlisted for the upcoming auction, "
        f"and reference their strongest matching lot.\n"
        f"Focus on concrete bidding behaviour that differentiates them.\n\n"
        f"Strongest lot match: {top_lot}\n"
        f"Bidder: {result.bidder_name}\n"
        f"Overall score: {result.score:.2f} ({result.recommendation.value})\n"
        f"Total bids: {b.total_bids} | Wins: {b.total_wins} | "
        f"Win rate: {raw_win_rate:.0f}%\n"
        f"Artist-specific bids: {len(artist_bids)} | Wins on matched artist: {len(wins)}\n"
        f"Average bid: €{avg_bid:,.0f} | Highest bid: €{max_bid:,.0f}\n"
        f"Price trajectory: {b.trajectory.value}\n"
        f"Bids above reserve: {b.bids_above_reserve}/{b.total_bids}\n"
        f"Matched upcoming lots: {lot_names}\n\n"
        f"Rationale:"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic template fallback
# ─────────────────────────────────────────────────────────────────────────────

def _template_rationale(result: EvaluationResult, artist_bids: list[Bid]) -> str:
    """
    Produces differentiated plain-English explanations from score dimensions.
    Two bidders with the same score but different profiles will receive
    distinct rationales — the core requirement from the May 18 meeting.
    """
    b    = result.breakdown
    name = result.bidder_name.split()[0]   # first name only for readability

    wins     = [bd for bd in artist_bids if bd.outcome == BidOutcome.WON]
    bid_vals = sorted([bd.bid_amount for bd in artist_bids], reverse=True)
    avg_bid  = sum(bid_vals) / len(bid_vals) if bid_vals else 0

    parts: list[str] = []

    # ── Opening: lead with the single most distinctive behaviour ─────────────
    if b.total_bids == 0:
        parts.append(
            f"{name} has no recorded bidding history, but their profile indicates "
            f"a price band alignment with upcoming lots."
        )
    elif b.total_wins == 0 and b.total_bids >= 5:
        # High-volume non-winner — drives competitive tension
        parts.append(
            f"{name} has placed {b.total_bids} bids without securing a lot, "
            f"suggesting persistent competitive engagement that raises hammer prices "
            f"even when they do not win."
        )
    elif b.total_wins >= 3 and b.win_loss_rate >= 0.5:
        # Strong consistent winner — use the RAW win rate for display, not the
        # normalised dimension score (which caps at 1.0 for any rate >= 40%).
        pct = int(round(100 * b.total_wins / b.total_bids)) if b.total_bids else 0
        parts.append(
            f"{name} has won {b.total_wins} of {b.total_bids} bids ({pct}% win rate), "
            f"demonstrating consistent acquisition intent and the financial commitment "
            f"to close on desired lots."
        )
    elif b.total_wins == 1 and bid_vals and bid_vals[0] >= 15000:
        # Selective high-value buyer
        parts.append(
            f"{name} has bid selectively, placing {b.total_bids} bid{'s' if b.total_bids > 1 else ''} "
            f"with a highest commitment of €{bid_vals[0]:,.0f}, "
            f"signalling a high-value collector who bids with conviction when interested."
        )
    elif b.total_wins >= 1 and avg_bid > 0:
        parts.append(
            f"{name} has secured {b.total_wins} lot{'s' if b.total_wins > 1 else ''} "
            f"from {b.total_bids} bids at an average bid of €{avg_bid:,.0f}, "
            f"showing focused acquisition behaviour aligned with this sale."
        )
    else:
        parts.append(
            f"{name} has been active with {b.total_bids} bid{'s' if b.total_bids > 1 else ''} "
            f"and {b.total_wins} win{'s' if b.total_wins > 1 else ''}, "
            f"with engagement patterns consistent with the upcoming catalogue."
        )

    # ── Middle: trajectory and reserve signals ────────────────────────────────
    if b.trajectory == PriceBandTrajectory.UP:
        parts.append(
            "Their price band trajectory is escalating, "
            "suggesting a growing collector increasing their ceiling — "
            "a desirable signal for consignors."
        )
    elif b.trajectory == PriceBandTrajectory.DOWN:
        parts.append(
            "Note: their price band trajectory shows a declining pattern, "
            "which may indicate tightening budget constraints."
        )
    elif b.reserve_ratio >= 0.80 and b.total_bids >= 3:
        parts.append(
            f"{b.bids_above_reserve} of their {b.total_bids} bids exceeded the reserve price, "
            "confirming serious acquisition intent rather than exploratory participation."
        )
    elif b.hammer_influence >= 0.8:
        parts.append(
            "When winning, they have historically driven hammer prices above estimate, "
            "making them a high-value participant for the sale room."
        )

    # ── Close: strongest specific lot match (most actionable for the auctioneer) ─
    if result.per_lot_scores:
        top = result.per_lot_scores[0]
        parts.append(
            f"Their strongest match in this sale is '{top.title}'"
            + (f" by {top.artist}" if top.artist else "")
            + f" (lot score {top.score:.2f}, {top.artist_bids} prior bid"
            + ("s" if top.artist_bids != 1 else "") + " on the artist)."
        )

    # ── Close: matched lots and artist context ────────────────────────────────
    if result.matched_lots:
        artists = list({ml.artist for ml in result.matched_lots if ml.artist})[:2]
        n_lots  = len(result.matched_lots)
        if artists:
            artist_str = " and ".join(artists)
            parts.append(
                f"Their bidding history on {artist_str} directly matches "
                f"{n_lots} upcoming lot{'s' if n_lots > 1 else ''} in this sale."
            )
    elif result.rejection_reasons:
        parts.append(
            "No direct artist overlap was found with upcoming lots; "
            "the shortlist is based on price band alignment."
        )

    # ── Provisional caveat ────────────────────────────────────────────────────
    if b.insufficient_history:
        parts.append(
            "Score is provisional due to limited bidding history — recommend manual review."
        )

    return " ".join(parts)
