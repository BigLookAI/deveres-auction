"""
Deviours Auction — Aggregator
Combines 6 scoring dimensions into a final score and Approve/Review/Reject recommendation.
Matches bidder to upcoming lots based on price band and category preferences.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from .models import (
    Bid, BidOutcome, BidderProfile, EvaluationResult,
    Lot, MatchedLot, PriceBandTrajectory, Recommendation, ScoreBreakdown
)
from .scorers import (
    _price_band, _parse_ts,
    score_win_loss,
    score_bid_count,
    score_reserve_ratio,
    score_repeat_buyer,
    score_price_band_trajectory,
    score_hammer_influence,
)

# Thresholds
APPROVE_THRESHOLD = 0.70
REVIEW_THRESHOLD  = 0.40

# Default dimension weights (sum = 1.0)
DEFAULT_WEIGHTS = {
    "win_loss_rate":         0.25,
    "bid_count":             0.20,
    "reserve_ratio":         0.20,
    "repeat_buyer":          0.15,
    "price_band_trajectory": 0.10,
    "hammer_influence":      0.10,
}


def evaluate_bidder(
    profile:      BidderProfile,
    all_lots:     list[Lot],
    weights:      dict[str, float] | None = None,
) -> EvaluationResult:
    """
    Run all 6 scoring dimensions for one bidder and produce an EvaluationResult.

    Args:
        profile:   BidderProfile with .bids populated
        all_lots:  List of all lots (historical + upcoming) for reserve/estimate lookups
        weights:   Optional custom dimension weights (must sum to ~1.0)
    """
    bids = profile.bids
    lots_by_id = {lot.lot_id: lot for lot in all_lots}
    w = weights or DEFAULT_WEIGHTS

    # ── Score each dimension ──────────────────────────────────────────────────
    d1 = score_win_loss(bids)
    d2 = score_bid_count(bids)
    d3 = score_reserve_ratio(bids, lots_by_id)
    d4 = score_repeat_buyer(bids)
    d5_score, trajectory = score_price_band_trajectory(bids)
    d6 = score_hammer_influence(bids, lots_by_id)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    breakdown = ScoreBreakdown(
        win_loss_rate         = d1,
        bid_count             = d2,
        reserve_ratio         = d3,
        repeat_buyer          = d4,
        price_band_trajectory = d5_score,
        hammer_influence      = d6,
        total_bids            = len(bids),
        total_wins            = sum(1 for b in bids if b.outcome == BidOutcome.WON),
        bids_above_reserve    = sum(
            1 for b in bids
            if lots_by_id.get(b.lot_id) and b.bid_amount >= lots_by_id[b.lot_id].reserve_price
        ),
        distinct_lots_won     = len({b.lot_id for b in bids if b.outcome == BidOutcome.WON}),
        trajectory            = trajectory,
        insufficient_history  = len(bids) < 5,
    )

    final_score = breakdown.weighted_total(w)
    final_score = round(min(max(final_score, 0.0), 1.0), 4)

    # ── Recommendation ────────────────────────────────────────────────────────
    if final_score >= APPROVE_THRESHOLD:
        recommendation = Recommendation.APPROVE
    elif final_score >= REVIEW_THRESHOLD:
        recommendation = Recommendation.REVIEW
    else:
        recommendation = Recommendation.REJECT

    # ── Rejection reasons ─────────────────────────────────────────────────────
    rejection_reasons: list[str] = []
    if final_score < APPROVE_THRESHOLD:
        if d1 < 0.3:
            rejection_reasons.append(f"Low win rate ({breakdown.total_wins}/{breakdown.total_bids} lots won)")
        if d2 < 0.3:
            rejection_reasons.append("Low bidding activity in last 12 months")
        if d3 < 0.3:
            rejection_reasons.append("Bids rarely meet reserve price — exploratory pattern")
        if breakdown.insufficient_history:
            rejection_reasons.append("Insufficient bidding history (< 5 bids)")
        if trajectory == PriceBandTrajectory.DOWN:
            rejection_reasons.append("Declining price band trajectory — budget-constrained signal")

    # ── Match upcoming lots ────────────────────────────────────────────────────
    upcoming = [lot for lot in all_lots if _is_upcoming(lot.auction_date)]
    matched = _match_lots(bids, upcoming)

    return EvaluationResult(
        bidder_id         = profile.bidder_id,
        bidder_name       = profile.name,
        bidder_email      = profile.email,
        score             = final_score,
        recommendation    = recommendation,
        breakdown         = breakdown,
        matched_lots      = matched,
        rejection_reasons = rejection_reasons,
    )


def evaluate_all(
    profiles:  list[BidderProfile],
    all_lots:  list[Lot],
    weights:   dict[str, float] | None = None,
) -> list[EvaluationResult]:
    """Evaluate all bidder profiles and return sorted by score descending."""
    results = [evaluate_bidder(p, all_lots, weights) for p in profiles]
    results.sort(key=lambda r: r.score, reverse=True)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_upcoming(auction_date: str) -> bool:
    try:
        dt = datetime.fromisoformat(auction_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    except ValueError:
        return False


def _bidder_preferred_categories(bids: list[Bid], lots_by_id: dict) -> dict[str, int]:
    """Count category appearances across all bids (won + lost)."""
    counts: dict[str, int] = defaultdict(int)
    for b in bids:
        lot = lots_by_id.get(b.lot_id)
        if lot:
            counts[lot.category] += 1
    return dict(counts)


def _bidder_price_bands(bids: list[Bid]) -> tuple[int, int]:
    """Return (min_band, max_band) seen across all bids."""
    if not bids:
        return 0, 0
    bands = [_price_band(b.bid_amount) for b in bids]
    return min(bands), max(bands)


def _match_lots(bids: list[Bid], upcoming: list[Lot]) -> list[MatchedLot]:
    """
    Find upcoming lots that match the bidder's historical preferences.
    Matching criteria:
      1. Lot category appears in bidder's historical bids
      2. Lot estimate band overlaps with bidder's historical price band range
    """
    if not bids or not upcoming:
        return []

    # Build historical preferences from bids (without lot reference — use bid amounts)
    bid_min_band, bid_max_band = _bidder_price_bands(bids)

    # Rough category preference: look at won bids first
    won_amounts = [b.bid_amount for b in bids if b.outcome == BidOutcome.WON]
    all_amounts = [b.bid_amount for b in bids]
    avg_amount  = sum(all_amounts) / len(all_amounts) if all_amounts else 0
    avg_win     = sum(won_amounts) / len(won_amounts) if won_amounts else avg_amount

    matched: list[MatchedLot] = []
    for lot in upcoming:
        lot_band_low  = _price_band(lot.estimate_low)
        lot_band_high = _price_band(lot.estimate_high)

        # Check price band overlap
        price_match = (
            lot_band_low <= bid_max_band and lot_band_high >= bid_min_band
        )
        if not price_match:
            continue

        # Build match reason
        reasons = []
        if lot.estimate_low <= avg_win <= lot.estimate_high * 1.5:
            reasons.append(f"estimate €{lot.estimate_low:,.0f}–€{lot.estimate_high:,.0f} aligns with avg win €{avg_win:,.0f}")
        else:
            reasons.append(f"price band overlap (bidder range: band {bid_min_band}–{bid_max_band})")

        matched.append(MatchedLot(
            lot_id        = lot.lot_id,
            title         = lot.title,
            category      = lot.category,
            estimate_low  = lot.estimate_low,
            estimate_high = lot.estimate_high,
            auction_date  = lot.auction_date,
            match_reason  = "; ".join(reasons),
        ))
        if len(matched) >= 5:
            break

    return matched
