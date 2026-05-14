"""Tests for all 6 scoring dimensions."""
import pytest
from pipeline.models import Bid, BidOutcome, Lot, PriceBandTrajectory
from pipeline.scorers import (
    score_win_loss,
    score_bid_count,
    score_reserve_ratio,
    score_repeat_buyer,
    score_price_band_trajectory,
    score_hammer_influence,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def make_bid(bid_id, lot_id, amount, outcome="won", ts="2026-01-15T10:00:00Z", hammer=None):
    return Bid(
        bid_id=bid_id, bidder_id="BDR-TEST", lot_id=lot_id,
        bid_amount=amount, timestamp=ts,
        outcome=BidOutcome(outcome),
        hammer_price=hammer,
    )

def make_lot(lot_id, reserve=1000, est_low=1000, est_high=2000, artist="Test Artist"):
    return Lot(
        lot_id=lot_id, title="Test Lot", category="painting",
        estimate_low=est_low, estimate_high=est_high,
        reserve_price=reserve, auction_date="2026-06-15T14:00:00Z",
        artist=artist,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 1 — Win/Loss Rate
# ─────────────────────────────────────────────────────────────────────────────

def test_win_loss_high():
    bids = [make_bid(f"B{i}", "L1", 1000, "won") for i in range(5)]
    assert score_win_loss(bids) == 1.0

def test_win_loss_medium():
    bids = [make_bid(f"B{i}", "L1", 1000, "won" if i < 3 else "lost") for i in range(10)]
    score = score_win_loss(bids)
    assert 0.5 <= score <= 1.0

def test_win_loss_low():
    bids = [make_bid("B1", "L1", 1000, "won")] + [make_bid(f"B{i}", "L1", 1000, "lost") for i in range(2, 15)]
    score = score_win_loss(bids)
    assert score < 0.5

def test_win_loss_no_bids():
    assert score_win_loss([]) == 0.0

def test_win_loss_insufficient_history_capped():
    bids = [make_bid(f"B{i}", "L1", 1000, "won") for i in range(4)]  # 4 bids, 100% win
    score = score_win_loss(bids)
    assert score <= 0.5  # capped for insufficient history

def test_win_loss_zero_wins():
    bids = [make_bid(f"B{i}", "L1", 1000, "lost") for i in range(10)]
    assert score_win_loss(bids) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 2 — Bid Count
# ─────────────────────────────────────────────────────────────────────────────

def test_bid_count_high():
    # 25 bids in last 3 months (weighted x1.5)
    bids = [make_bid(f"B{i}", "L1", 1000, ts="2026-04-01T10:00:00Z") for i in range(25)]
    assert score_bid_count(bids) == 1.0

def test_bid_count_none_recent():
    # All bids from 2 years ago — zero recent weighted bids
    bids = [make_bid(f"B{i}", "L1", 1000, ts="2024-01-01T10:00:00Z") for i in range(30)]
    assert score_bid_count(bids) == 0.0

def test_bid_count_empty():
    assert score_bid_count([]) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 3 — Reserve Ratio
# ─────────────────────────────────────────────────────────────────────────────

def test_reserve_ratio_all_above():
    lots_by_id = {"L1": make_lot("L1", reserve=500)}
    bids = [make_bid(f"B{i}", "L1", 800) for i in range(5)]
    assert score_reserve_ratio(bids, lots_by_id) == 1.0

def test_reserve_ratio_all_below():
    lots_by_id = {"L1": make_lot("L1", reserve=1000)}
    bids = [make_bid(f"B{i}", "L1", 400) for i in range(5)]
    assert score_reserve_ratio(bids, lots_by_id) == 0.0

def test_reserve_ratio_no_lot_data():
    # No lots in dict — returns neutral 0.5
    assert score_reserve_ratio([make_bid("B1", "UNKNOWN", 500)], {}) == 0.5

def test_reserve_ratio_empty():
    assert score_reserve_ratio([], {}) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 4 — Repeat Buyer
# ─────────────────────────────────────────────────────────────────────────────

def test_repeat_buyer_zero_wins():
    bids = [make_bid("B1", "L1", 1000, "lost")]
    assert score_repeat_buyer(bids) == 0.0

def test_repeat_buyer_one_win():
    bids = [make_bid("B1", "L1", 1000, "won")]
    assert score_repeat_buyer(bids) == 0.4

def test_repeat_buyer_two_wins():
    bids = [make_bid("B1", "L1", 1000, "won"), make_bid("B2", "L2", 2000, "won")]
    assert score_repeat_buyer(bids) == 0.6

def test_repeat_buyer_four_plus():
    bids = [make_bid(f"B{i}", f"L{i}", 1000, "won") for i in range(6)]
    assert score_repeat_buyer(bids) == 1.0

def test_repeat_buyer_same_lot_twice():
    # Same lot won twice — only counts as 1 distinct lot
    bids = [make_bid("B1", "L1", 1000, "won"), make_bid("B2", "L1", 1500, "won")]
    assert score_repeat_buyer(bids) == 0.4


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 5 — Price Band Trajectory
# ─────────────────────────────────────────────────────────────────────────────

def test_trajectory_up():
    bids = [
        make_bid("B1", "L1", 500,    ts="2025-01-01T10:00:00Z"),
        make_bid("B2", "L2", 2000,   ts="2025-06-01T10:00:00Z"),
        make_bid("B3", "L3", 8000,   ts="2025-10-01T10:00:00Z"),
        make_bid("B4", "L4", 25000,  ts="2026-01-01T10:00:00Z"),
        make_bid("B5", "L5", 80000,  ts="2026-04-01T10:00:00Z"),
    ]
    score, traj = score_price_band_trajectory(bids)
    assert traj == PriceBandTrajectory.UP
    assert score == 1.0

def test_trajectory_down():
    bids = [
        make_bid("B1", "L1", 80000, ts="2025-01-01T10:00:00Z"),
        make_bid("B2", "L2", 25000, ts="2025-06-01T10:00:00Z"),
        make_bid("B3", "L3", 8000,  ts="2025-10-01T10:00:00Z"),
        make_bid("B4", "L4", 2000,  ts="2026-01-01T10:00:00Z"),
        make_bid("B5", "L5", 500,   ts="2026-04-01T10:00:00Z"),
    ]
    score, traj = score_price_band_trajectory(bids)
    assert traj == PriceBandTrajectory.DOWN
    assert score == 0.2

def test_trajectory_insufficient():
    bids = [make_bid("B1", "L1", 1000)]
    score, traj = score_price_band_trajectory(bids)
    assert traj == PriceBandTrajectory.UNKNOWN
    assert score == 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 6 — Hammer Price Influence
# ─────────────────────────────────────────────────────────────────────────────

def test_hammer_influence_high():
    lots = {"L1": make_lot("L1", est_high=5000)}
    # Won at 7000 — 40% above estimate_high
    bids = [make_bid("B1", "L1", 7000, "won", hammer=7000)]
    assert score_hammer_influence(bids, lots) == 1.0

def test_hammer_influence_neutral():
    lots = {"L1": make_lot("L1", est_high=5000)}
    bids = [make_bid("B1", "L1", 4800, "won", hammer=4800)]
    assert score_hammer_influence(bids, lots) == 0.5

def test_hammer_influence_no_wins():
    lots = {"L1": make_lot("L1")}
    bids = [make_bid("B1", "L1", 500, "lost")]
    assert score_hammer_influence(bids, lots) == 0.5

def test_hammer_influence_empty():
    assert score_hammer_influence([], {}) == 0.5
