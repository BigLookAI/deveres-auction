"""
Deviours Auction — Aggregator
Combines 6 scoring dimensions into a final score and Approve/Review/Reject recommendation.
Matches bidders to upcoming lots based on artist history (v2 — artist-based matching).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from .models import (
    Bid, BidOutcome, BidderProfile, EvaluationResult,
    Lot, LotScore, MatchedLot, PriceBandTrajectory, Recommendation, ScoreBreakdown
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


# ─────────────────────────────────────────────────────────────────────────────
# Artist index builders
# ─────────────────────────────────────────────────────────────────────────────

def build_artist_index(past_lots: list[Lot]) -> dict[str, str]:
    """
    Build a mapping from lot_id → artist from the past lots list.
    Used to annotate historical bids with the artist of each lot.
    """
    return {lot.lot_id: lot.artist for lot in past_lots if lot.artist}


def build_upcoming_artist_map(upcoming_lots: list[Lot]) -> dict[str, list[Lot]]:
    """
    Build a mapping from artist → list[Lot] for upcoming lots.
    Bidders matched to an artist will be evaluated against all lots by that artist.
    """
    result: dict[str, list[Lot]] = defaultdict(list)
    for lot in upcoming_lots:
        if lot.artist:
            result[lot.artist].append(lot)
    return dict(result)


def get_bidder_artists(bids: list[Bid], artist_index: dict[str, str]) -> dict[str, list[Bid]]:
    """
    Group a bidder's historical bids by artist.
    Returns {artist: [bids on that artist's lots]}.
    Only includes artists where the lot_id is found in artist_index.
    """
    by_artist: dict[str, list[Bid]] = defaultdict(list)
    for bid in bids:
        artist = artist_index.get(bid.lot_id)
        if artist:
            by_artist[artist].append(bid)
    return dict(by_artist)


# ─────────────────────────────────────────────────────────────────────────────
# Per-lot scoring
# ─────────────────────────────────────────────────────────────────────────────

def _score_breakdown_for_bids(
    bids: list[Bid],
    lots_by_id: dict[str, Lot],
    weights: dict[str, float],
) -> tuple[ScoreBreakdown, float]:
    """Compute all 6 dimensions and weighted total for a given set of bids."""
    d1 = score_win_loss(bids)
    d2 = score_bid_count(bids)
    d3 = score_reserve_ratio(bids, lots_by_id)
    d4 = score_repeat_buyer(bids)
    d5_score, trajectory = score_price_band_trajectory(bids)
    d6 = score_hammer_influence(bids, lots_by_id)

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
    score = breakdown.weighted_total(weights)
    score = round(min(max(score, 0.0), 1.0), 4)
    return breakdown, score


def _recommendation_for_score(score: float) -> Recommendation:
    if score >= APPROVE_THRESHOLD:
        return Recommendation.APPROVE
    elif score >= REVIEW_THRESHOLD:
        return Recommendation.REVIEW
    return Recommendation.REJECT


def score_per_lot(
    upcoming_lot: Lot,
    artist_bids:  list[Bid],
    lots_by_id:   dict[str, Lot],
    weights:      dict[str, float],
) -> LotScore:
    """
    Compute a score and per-lot recommendation for a single upcoming lot,
    based on the bidder's historical bids on that lot's artist only.
    This is the primary decision unit: "should we invite this bidder for this lot?"
    """
    breakdown, score = _score_breakdown_for_bids(artist_bids, lots_by_id, weights)
    return LotScore(
        lot_id         = upcoming_lot.lot_id,
        title          = upcoming_lot.title,
        artist         = upcoming_lot.artist,
        category       = upcoming_lot.category,
        estimate_low   = upcoming_lot.estimate_low,
        estimate_high  = upcoming_lot.estimate_high,
        auction_date   = upcoming_lot.auction_date,
        score          = score,
        recommendation = _recommendation_for_score(score),
        breakdown      = breakdown,
        artist_bids    = len(artist_bids),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_bidder(
    profile:      BidderProfile,
    all_lots:     list[Lot],
    weights:      dict[str, float] | None = None,
    past_lots:    list[Lot] | None = None,
) -> EvaluationResult:
    """
    Run all 6 scoring dimensions for one bidder and produce an EvaluationResult.

    When past_lots is provided, per-lot artist-based scoring is computed:
      - Each upcoming lot is scored using the bidder's bids on that artist's past lots
      - The overall score is the average of per-lot scores (or overall score if no matches)

    Args:
        profile:    BidderProfile with .bids populated
        all_lots:   List of upcoming lots (for reserve/estimate lookups and matching)
        weights:    Optional custom dimension weights (must sum to ~1.0)
        past_lots:  Historical past lots for artist index construction
    """
    bids = profile.bids
    w = weights or DEFAULT_WEIGHTS

    # Build lookup dicts
    upcoming = [lot for lot in all_lots if _is_upcoming(lot.auction_date)]
    all_lots_by_id = {lot.lot_id: lot for lot in all_lots}

    # Incorporate past lots into the lookup so reserve/estimate scoring works
    if past_lots:
        for lot in past_lots:
            all_lots_by_id[lot.lot_id] = lot

    # ── Overall score (across all bids) ──────────────────────────────────────
    overall_breakdown, overall_score = _score_breakdown_for_bids(bids, all_lots_by_id, w)

    # ── Per-lot artist-based scoring ─────────────────────────────────────────
    per_lot_scores: list[LotScore] = []
    matched_lots:   list[MatchedLot] = []

    if past_lots and upcoming:
        artist_index      = build_artist_index(past_lots)
        upcoming_art_map  = build_upcoming_artist_map(upcoming)
        bidder_by_artist  = get_bidder_artists(bids, artist_index)

        for artist, artist_bids in bidder_by_artist.items():
            upcoming_by_artist = upcoming_art_map.get(artist, [])
            for lot in upcoming_by_artist:
                lot_score = score_per_lot(lot, artist_bids, all_lots_by_id, w)
                per_lot_scores.append(lot_score)
                matched_lots.append(MatchedLot(
                    lot_id        = lot.lot_id,
                    title         = lot.title,
                    artist        = lot.artist,
                    category      = lot.category,
                    estimate_low  = lot.estimate_low,
                    estimate_high = lot.estimate_high,
                    auction_date  = lot.auction_date,
                    match_reason  = f"artist match: {artist} ({len(artist_bids)} past bids)",
                ))

        # Sort per-lot scores descending
        per_lot_scores.sort(key=lambda s: s.score, reverse=True)
        matched_lots.sort(key=lambda m: m.lot_id)

        # Overall score = BEST per-lot score (not average).
        # Rationale: the invitation question is "is there at least one lot worth
        # inviting this bidder for?" — not "how do they score on average across
        # all matched lots". A bidder who scores 0.85 for one artist and 0.30
        # for another should be APPROVED (for the first lot), not averaged to REVIEW.
        if per_lot_scores:
            overall_score = per_lot_scores[0].score  # already sorted descending
    else:
        # Fallback: price-band matching when no past_lots provided
        matched_lots = _match_lots_price_band(bids, upcoming)

    # ── Recommendation (derived from best per-lot score) ─────────────────────
    recommendation = _recommendation_for_score(overall_score)

    # ── Rejection reasons ─────────────────────────────────────────────────────
    rejection_reasons: list[str] = []
    if overall_score < APPROVE_THRESHOLD:
        b = overall_breakdown
        if overall_breakdown.win_loss_rate < 0.3:
            rejection_reasons.append(f"Low win rate ({b.total_wins}/{b.total_bids} lots won)")
        if overall_breakdown.bid_count < 0.3:
            rejection_reasons.append("Low bidding activity in last 12 months")
        if overall_breakdown.reserve_ratio < 0.3:
            rejection_reasons.append("Bids rarely meet reserve price — exploratory pattern")
        if overall_breakdown.insufficient_history:
            rejection_reasons.append("Insufficient bidding history (< 5 bids)")
        if overall_breakdown.trajectory == PriceBandTrajectory.DOWN:
            rejection_reasons.append("Declining price band trajectory — budget-constrained signal")
        if not per_lot_scores and past_lots is not None:
            rejection_reasons.append("No artist overlap with upcoming lots")

    return EvaluationResult(
        bidder_id         = profile.bidder_id,
        bidder_name       = profile.name,
        bidder_email      = profile.email,
        score             = overall_score,
        recommendation    = recommendation,
        breakdown         = overall_breakdown,
        matched_lots      = matched_lots,
        per_lot_scores    = per_lot_scores,
        rejection_reasons = rejection_reasons,
    )


def evaluate_all(
    profiles:   list[BidderProfile],
    all_lots:   list[Lot],
    weights:    dict[str, float] | None = None,
    past_lots:  list[Lot] | None = None,
) -> list[EvaluationResult]:
    """Evaluate all bidder profiles and return sorted by score descending."""
    results = [evaluate_bidder(p, all_lots, weights, past_lots) for p in profiles]
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


def _match_lots_price_band(bids: list[Bid], upcoming: list[Lot]) -> list[MatchedLot]:
    """
    Fallback lot matching by price band overlap (used when past_lots not available).
    """
    if not bids or not upcoming:
        return []

    bid_min_band, bid_max_band = _bidder_price_bands(bids)
    won_amounts = [b.bid_amount for b in bids if b.outcome == BidOutcome.WON]
    all_amounts = [b.bid_amount for b in bids]
    avg_amount  = sum(all_amounts) / len(all_amounts) if all_amounts else 0
    avg_win     = sum(won_amounts) / len(won_amounts) if won_amounts else avg_amount

    matched: list[MatchedLot] = []
    for lot in upcoming:
        lot_band_low  = _price_band(lot.estimate_low)
        lot_band_high = _price_band(lot.estimate_high)
        if not (lot_band_low <= bid_max_band and lot_band_high >= bid_min_band):
            continue
        if lot.estimate_low <= avg_win <= lot.estimate_high * 1.5:
            reason = f"estimate €{lot.estimate_low:,.0f}–€{lot.estimate_high:,.0f} aligns with avg win €{avg_win:,.0f}"
        else:
            reason = f"price band overlap (bidder range: band {bid_min_band}–{bid_max_band})"
        matched.append(MatchedLot(
            lot_id        = lot.lot_id,
            title         = lot.title,
            artist        = lot.artist,
            category      = lot.category,
            estimate_low  = lot.estimate_low,
            estimate_high = lot.estimate_high,
            auction_date  = lot.auction_date,
            match_reason  = reason,
        ))
        if len(matched) >= 5:
            break
    return matched
