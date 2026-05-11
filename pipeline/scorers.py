"""
Deviours Auction — Deterministic Scoring Engine
Six independent scoring dimensions, each returning a normalised 0–1 float.
All logic is binary/deterministic — no LLM involved at this layer.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from collections import defaultdict

from .models import Bid, BidOutcome, BidderProfile, PriceBandTrajectory


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(ts: str) -> datetime:
    """Parse ISO 8601 timestamp to UTC-aware datetime."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _months_ago(months: int) -> datetime:
    now = datetime.now(timezone.utc)
    year  = now.year - (months // 12)
    month = now.month - (months % 12)
    if month <= 0:
        month += 12
        year  -= 1
    return now.replace(year=year, month=month)


def _price_band(amount: float) -> int:
    """Map EUR amount to an integer band (higher = more expensive)."""
    thresholds = [500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000, 100_000]
    for i, t in enumerate(thresholds):
        if amount < t:
            return i
    return len(thresholds)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 1 — Win / Loss Rate
# ─────────────────────────────────────────────────────────────────────────────

def score_win_loss(bids: list[Bid]) -> float:
    """
    Fraction of bids that resulted in a win.
    High:   > 40% win rate → 1.0
    Medium: 20–40%         → linear 0.5–1.0
    Low:    < 20%          → linear 0–0.5
    Insufficient history (< 5 bids): capped at 0.5.
    """
    if not bids:
        return 0.0
    wins  = sum(1 for b in bids if b.outcome == BidOutcome.WON)
    total = len(bids)
    rate  = wins / total

    if rate >= 0.40:
        score = 1.0
    elif rate >= 0.20:
        score = 0.5 + (rate - 0.20) / (0.40 - 0.20) * 0.5
    else:
        score = rate / 0.20 * 0.5

    if total < 5:
        score = min(score, 0.5)   # insufficient history flag
    return round(score, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 2 — Bid Count / Engagement
# ─────────────────────────────────────────────────────────────────────────────

def score_bid_count(bids: list[Bid]) -> float:
    """
    Total bids in last 12 months, with recent 3-month bids weighted ×1.5.
    High:   ≥ 20 weighted bids → 1.0
    Medium: 5–20               → linear 0.5–1.0
    Low:    < 5                → linear 0–0.5
    """
    cutoff_12m = _months_ago(12)
    cutoff_3m  = _months_ago(3)

    weighted = 0.0
    for b in bids:
        ts = _parse_ts(b.timestamp)
        if ts >= cutoff_12m:
            weighted += 1.5 if ts >= cutoff_3m else 1.0

    if weighted >= 20:
        score = 1.0
    elif weighted >= 5:
        score = 0.5 + (weighted - 5) / (20 - 5) * 0.5
    else:
        score = weighted / 5 * 0.5
    return round(score, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 3 — Reserve Ratio (serious intent)
# ─────────────────────────────────────────────────────────────────────────────

def score_reserve_ratio(bids: list[Bid], lots_by_id: dict) -> float:
    """
    Fraction of bids where bid_amount ≥ reserve_price of the lot.
    Signals genuine intent vs. exploratory / shill bidding.
    """
    if not bids:
        return 0.0
    qualifying = 0
    total_with_reserve = 0
    for b in bids:
        lot = lots_by_id.get(b.lot_id)
        if lot is None:
            continue
        total_with_reserve += 1
        if b.bid_amount >= lot.reserve_price:
            qualifying += 1
    if total_with_reserve == 0:
        return 0.5   # no reserve data available — neutral
    return round(qualifying / total_with_reserve, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 4 — Repeat Buyer
# ─────────────────────────────────────────────────────────────────────────────

def score_repeat_buyer(bids: list[Bid]) -> float:
    """
    Distinct lots won.  First-time bidder (0 wins) → 0.0.
    1 win → 0.4, 2 wins → 0.6, 3 wins → 0.8, 4+ wins → 1.0.
    """
    distinct_wins = len({b.lot_id for b in bids if b.outcome == BidOutcome.WON})
    mapping = {0: 0.0, 1: 0.4, 2: 0.6, 3: 0.8}
    return mapping.get(distinct_wins, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 5 — Price Band Trajectory
# ─────────────────────────────────────────────────────────────────────────────

def score_price_band_trajectory(bids: list[Bid]) -> tuple[float, PriceBandTrajectory]:
    """
    Track bidder's price bands chronologically.
    UP (escalating) → 1.0  — growing collector, desirable
    ECLECTIC        → 0.5  — opportunistic, neutral
    DOWN            → 0.2  — budget-constrained, flag for caution
    UNKNOWN         → 0.5  — insufficient data
    Returns (score, trajectory_label).
    """
    if len(bids) < 3:
        return 0.5, PriceBandTrajectory.UNKNOWN

    sorted_bids = sorted(bids, key=lambda b: _parse_ts(b.timestamp))
    bands = [_price_band(b.bid_amount) for b in sorted_bids]

    # Simple linear regression slope on band indices
    n = len(bands)
    x_mean = (n - 1) / 2
    y_mean = sum(bands) / n
    numerator   = sum((i - x_mean) * (bands[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0.5, PriceBandTrajectory.ECLECTIC

    slope = numerator / denominator
    std_dev = math.sqrt(sum((b - y_mean) ** 2 for b in bands) / n) if n > 1 else 0

    # High variance → eclectic regardless of slope
    if std_dev > 2.5:
        return 0.5, PriceBandTrajectory.ECLECTIC
    elif slope > 0.15:
        return 1.0, PriceBandTrajectory.UP
    elif slope < -0.15:
        return 0.2, PriceBandTrajectory.DOWN
    else:
        return 0.5, PriceBandTrajectory.ECLECTIC


# ─────────────────────────────────────────────────────────────────────────────
# Dimension 6 — Hammer Price Influence
# ─────────────────────────────────────────────────────────────────────────────

def score_hammer_influence(bids: list[Bid], lots_by_id: dict) -> float:
    """
    When bidder WON, how far above the estimate was the hammer price?
    High influence (> +20% above estimate_high) → 1.0
    Neutral (within estimate band)              → 0.5
    Low (near reserve only)                     → 0.2
    Returns 0.5 if no wins or no lot data.
    """
    won_bids = [b for b in bids if b.outcome == BidOutcome.WON]
    if not won_bids:
        return 0.5   # no wins — neutral, not penalised

    influences = []
    for b in won_bids:
        lot = lots_by_id.get(b.lot_id)
        if lot is None:
            continue
        hammer = b.hammer_price or b.bid_amount
        estimate_high = lot.estimate_high
        if estimate_high <= 0:
            continue
        ratio = (hammer - estimate_high) / estimate_high   # negative = below estimate
        influences.append(ratio)

    if not influences:
        return 0.5

    avg = sum(influences) / len(influences)
    if avg > 0.20:
        return 1.0
    elif avg >= -0.10:
        return 0.5
    else:
        return 0.2
