"""Tests for the aggregator: end-to-end evaluation + recommendation thresholds."""
import pytest
from datetime import datetime, timedelta, timezone
from pipeline.models import Bid, BidOutcome, BidderProfile, Lot, Recommendation, PriceBandTrajectory
from pipeline.aggregator import (
    evaluate_bidder, evaluate_all, APPROVE_THRESHOLD, REVIEW_THRESHOLD,
    build_artist_index, build_upcoming_artist_map, get_bidder_artists,
)


def make_lot(lot_id, reserve=1000, est_low=1000, est_high=2000, upcoming=True, artist="Aoife Ní Fhaoláin"):
    # dynamic future date — fixtures must never rot as the calendar advances
    future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT14:00:00Z")
    date = future if upcoming else "2024-01-01T14:00:00Z"
    return Lot(lot_id=lot_id, title=f"Lot {lot_id}", category="painting",
               estimate_low=est_low, estimate_high=est_high,
               reserve_price=reserve, auction_date=date, artist=artist)


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


# ─────────────────────────────────────────────────────────────────────────────
# Artist index and per-lot scoring tests
# ─────────────────────────────────────────────────────────────────────────────

def test_build_artist_index():
    lots = [
        make_lot("P001", upcoming=False, artist="Alice Burke"),
        make_lot("P002", upcoming=False, artist="Bob Ó Murchú"),
        make_lot("P003", upcoming=False, artist=""),  # no artist
    ]
    idx = build_artist_index(lots)
    assert idx["P001"] == "Alice Burke"
    assert idx["P002"] == "Bob Ó Murchú"
    assert "P003" not in idx  # empty artist excluded


def test_build_upcoming_artist_map():
    lots = [
        make_lot("U001", upcoming=True, artist="Alice Burke"),
        make_lot("U002", upcoming=True, artist="Alice Burke"),
        make_lot("U003", upcoming=True, artist="Bob Ó Murchú"),
    ]
    art_map = build_upcoming_artist_map(lots)
    assert len(art_map["Alice Burke"]) == 2
    assert len(art_map["Bob Ó Murchú"]) == 1


def test_get_bidder_artists():
    bids = [
        Bid(bid_id="B1", bidder_id="BDR-T", lot_id="P001",
            bid_amount=1000, timestamp="2025-01-01T10:00:00Z",
            outcome=BidOutcome.WON, hammer_price=1100),
        Bid(bid_id="B2", bidder_id="BDR-T", lot_id="P002",
            bid_amount=1200, timestamp="2025-06-01T10:00:00Z",
            outcome=BidOutcome.LOST, hammer_price=None),
        Bid(bid_id="B3", bidder_id="BDR-T", lot_id="P999",  # not in index
            bid_amount=500, timestamp="2025-09-01T10:00:00Z",
            outcome=BidOutcome.LOST, hammer_price=None),
    ]
    artist_index = {"P001": "Alice Burke", "P002": "Alice Burke"}
    by_artist = get_bidder_artists(bids, artist_index)
    assert "Alice Burke" in by_artist
    assert len(by_artist["Alice Burke"]) == 2
    assert "P999" not in str(by_artist)  # unknown lot excluded


def test_per_lot_scores_populated_with_past_lots():
    """Bidder with past bids on same artist as upcoming lot gets per_lot_scores."""
    past_lots = [
        make_lot("P001", upcoming=False, artist="Alice Burke", reserve=800, est_low=1000, est_high=2000),
        make_lot("P002", upcoming=False, artist="Alice Burke", reserve=900, est_low=1200, est_high=2200),
    ]
    upcoming = [
        make_lot("U001", upcoming=True, artist="Alice Burke", reserve=1000, est_low=1500, est_high=3000),
    ]
    bids = [
        Bid(bid_id="B1", bidder_id="BDR-T", lot_id="P001",
            bid_amount=1500, timestamp="2025-06-01T10:00:00Z",
            outcome=BidOutcome.WON, hammer_price=1600),
        Bid(bid_id="B2", bidder_id="BDR-T", lot_id="P002",
            bid_amount=1800, timestamp="2025-09-01T10:00:00Z",
            outcome=BidOutcome.WON, hammer_price=1900),
    ]
    profile = BidderProfile(bidder_id="BDR-T", name="Test Bidder",
                            email="t@test.ie", bids=bids)
    result = evaluate_bidder(profile, upcoming, past_lots=past_lots)
    assert len(result.per_lot_scores) == 1
    ls = result.per_lot_scores[0]
    assert ls.lot_id == "U001"
    assert ls.artist == "Alice Burke"
    assert 0.0 <= ls.score <= 1.0
    assert ls.recommendation in (Recommendation.APPROVE, Recommendation.REVIEW, Recommendation.REJECT)


def test_no_artist_overlap_gets_no_match():
    """Bidder whose past lots have a different artist than upcoming gets no per_lot_scores."""
    past_lots = [
        make_lot("P001", upcoming=False, artist="Different Artist"),
    ]
    upcoming = [
        make_lot("U001", upcoming=True, artist="Alice Burke"),
    ]
    bids = [
        Bid(bid_id="B1", bidder_id="BDR-T", lot_id="P001",
            bid_amount=1000, timestamp="2025-01-01T10:00:00Z",
            outcome=BidOutcome.WON, hammer_price=1100),
    ]
    profile = BidderProfile(bidder_id="BDR-T", name="Test Bidder",
                            email="t@test.ie", bids=bids)
    result = evaluate_bidder(profile, upcoming, past_lots=past_lots)
    assert len(result.per_lot_scores) == 0
    assert len(result.matched_lots) == 0


def test_evaluate_all_with_past_lots():
    """evaluate_all passes past_lots to each evaluate_bidder call."""
    past_lots = [make_lot("P001", upcoming=False, artist="Aoife Ní Fhaoláin")]
    upcoming  = [make_lot("U001", upcoming=True,  artist="Aoife Ní Fhaoláin")]
    bids = [
        Bid(bid_id="B1", bidder_id="BDR-T", lot_id="P001",
            bid_amount=1500, timestamp="2026-01-01T10:00:00Z",
            outcome=BidOutcome.WON, hammer_price=1600),
        Bid(bid_id="B2", bidder_id="BDR-T", lot_id="P001",
            bid_amount=1200, timestamp="2025-08-01T10:00:00Z",
            outcome=BidOutcome.WON, hammer_price=1250),
    ]
    profile = BidderProfile(bidder_id="BDR-T", name="Test", email="t@t.ie", bids=bids)
    results = evaluate_all([profile], upcoming, past_lots=past_lots)
    assert len(results) == 1
    assert len(results[0].per_lot_scores) == 1
