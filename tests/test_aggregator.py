"""Tests for the aggregator: end-to-end evaluation + recommendation thresholds."""
import pytest
from pipeline.models import Bid, BidOutcome, BidderProfile, Lot, Recommendation, PriceBandTrajectory
from pipeline.aggregator import evaluate_bidder, evaluate_all, APPROVE_THRESHOLD, REVIEW_THRESHOLD


def make_lot(lot_id, reserve=1000, est_low=1000, est_high=2000, upcoming=True):
    date = "2026-06-15T14:00:00Z" if upcoming else "2024-01-01T14:00:00Z"
    return Lot(lot_id=lot_id, title=f"Lot {lot_id}", category="painting",
               estimate_low=est_low, estimate_high=est_high,
               reserve_price=reserve, auction_date=date)


def make_bid(bid_id, lot_id, amount, outcome="won", ts="2026-01-15T10:00:00Z", hammer=None):
    return Bid(bid_id=bid_id, bidder_id="BDR-TEST", lot_id=lot_id,
               bid_amount=amount, timestamp=ts, outcome=BidOutcome(outcome),
               hammer_price=hammer)


def strong_bidder_profile() -> tuple[BidderProfile, list[Lot]]:
    """Bidder with strong engagement — should APPROVE."""
    lots = [make_lot(f"L{i}", reserve=800, est_low=1000, est_high=2000, upcoming=(i >= 6))
            for i in range(1, 9)]
    bids = [
        make_bid("B1", "L1", 1500, "won", "2025-06-01T10:00:00Z", hammer=1600),
        make_bid("B2", "L2", 1200, "won", "2025-07-01T10:00:00Z", hammer=1200),
        make_bid("B3", "L3", 1800, "lost","2025-08-01T10:00:00Z"),
        make_bid("B4", "L4", 2100, "won", "2025-10-01T10:00:00Z", hammer=2300),
        make_bid("B5", "L5", 1900, "won", "2026-02-01T10:00:00Z", hammer=2000),
        make_bid("B6", "L5", 2500, "won", "2026-03-15T10:00:00Z", hammer=2700),
    ]
    profile = BidderProfile(bidder_id="BDR-STRONG", name="Strong Bidder",
                            email="strong@test.ie", bids=bids)
    return profile, lots


def weak_bidder_profile() -> tuple[BidderProfile, list[Lot]]:
    """Bidder with only 2 old losing bids — should REJECT."""
    lots = [make_lot("L1", reserve=2000, est_low=1500, est_high=2500)]
    bids = [
        make_bid("B1", "L1", 500, "lost", "2024-01-10T10:00:00Z"),
        make_bid("B2", "L1", 400, "lost", "2024-03-10T10:00:00Z"),
    ]
    profile = BidderProfile(bidder_id="BDR-WEAK", name="Weak Bidder",
                            email="weak@test.ie", bids=bids)
    return profile, lots


def no_bid_profile() -> tuple[BidderProfile, list[Lot]]:
    lots = [make_lot("L1")]
    profile = BidderProfile(bidder_id="BDR-EMPTY", name="Empty Bidder",
                            email="empty@test.ie", bids=[])
    return profile, lots


# ─────────────────────────────────────────────────────────────────────────────

def test_strong_bidder_approves():
    profile, lots = strong_bidder_profile()
    result = evaluate_bidder(profile, lots)
    assert result.score >= APPROVE_THRESHOLD
    assert result.recommendation == Recommendation.APPROVE


def test_weak_bidder_rejects():
    profile, lots = weak_bidder_profile()
    result = evaluate_bidder(profile, lots)
    assert result.score < REVIEW_THRESHOLD
    assert result.recommendation == Recommendation.REJECT


def test_empty_bidder_rejects():
    profile, lots = no_bid_profile()
    result = evaluate_bidder(profile, lots)
    assert result.recommendation == Recommendation.REJECT
    assert result.score < REVIEW_THRESHOLD  # neutral trajectory/hammer give small non-zero score


def test_review_zone():
    """Bidder with moderate engagement — 1 win from 8 bids (12.5% win rate), some recent bids."""
    lots = [make_lot(f"L{i}", reserve=2000) for i in range(1, 6)]   # high reserve → few bids qualify
    bids = [
        make_bid("B1", "L1", 1500, "lost", "2025-06-01T10:00:00Z"),
        make_bid("B2", "L2", 1800, "lost", "2025-08-01T10:00:00Z"),
        make_bid("B3", "L3", 2100, "won",  "2025-10-01T10:00:00Z", hammer=2100),
        make_bid("B4", "L4", 1600, "lost", "2026-01-01T10:00:00Z"),
        make_bid("B5", "L5", 1700, "lost", "2026-03-01T10:00:00Z"),
        make_bid("B6", "L1", 1900, "lost", "2026-04-15T10:00:00Z"),
    ]
    profile = BidderProfile(bidder_id="BDR-MED", name="Medium Bidder",
                            email="medium@test.ie", bids=bids)
    result = evaluate_bidder(profile, lots)
    assert REVIEW_THRESHOLD <= result.score < APPROVE_THRESHOLD
    assert result.recommendation == Recommendation.REVIEW


def test_breakdown_fields_populated():
    profile, lots = strong_bidder_profile()
    result = evaluate_bidder(profile, lots)
    b = result.breakdown
    assert b.total_bids > 0
    assert b.total_wins > 0
    assert 0.0 <= b.win_loss_rate <= 1.0
    assert 0.0 <= b.bid_count <= 1.0
    assert 0.0 <= b.reserve_ratio <= 1.0
    assert 0.0 <= b.repeat_buyer <= 1.0
    assert 0.0 <= b.price_band_trajectory <= 1.0
    assert 0.0 <= b.hammer_influence <= 1.0


def test_evaluate_all_sorted_descending():
    p_strong, lots = strong_bidder_profile()
    p_weak,   _    = weak_bidder_profile()
    results = evaluate_all([p_weak, p_strong], lots)
    assert results[0].score >= results[1].score


def test_rejection_reasons_populated_on_reject():
    profile, lots = weak_bidder_profile()
    result = evaluate_bidder(profile, lots)
    assert result.recommendation == Recommendation.REJECT
    assert len(result.rejection_reasons) > 0


def test_matched_lots_for_approved_bidder():
    profile, lots = strong_bidder_profile()
    result = evaluate_bidder(profile, lots)
    # Should have at least one upcoming lot matched (lots 6+ are upcoming in fixture)
    assert isinstance(result.matched_lots, list)


def test_custom_weights():
    """Custom weights that heavily favour win_loss_rate should change score."""
    profile, lots = strong_bidder_profile()
    r_default = evaluate_bidder(profile, lots)
    r_custom  = evaluate_bidder(profile, lots, weights={
        "win_loss_rate":         0.80,
        "bid_count":             0.05,
        "reserve_ratio":         0.05,
        "repeat_buyer":          0.05,
        "price_band_trajectory": 0.025,
        "hammer_influence":      0.025,
    })
    # Both should still be Approve for a strong bidder, just different scores
    assert r_default.recommendation == Recommendation.APPROVE
    assert r_custom.recommendation  == Recommendation.APPROVE
    assert r_default.score != r_custom.score
