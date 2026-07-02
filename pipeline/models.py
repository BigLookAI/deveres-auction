"""
deVeres Auction — Data Models
Core dataclasses for the bidder evaluation pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class BidOutcome(str, Enum):
    WON  = "won"
    LOST = "lost"


class PriceBandTrajectory(str, Enum):
    UP       = "up"        # escalating price bands over time
    DOWN     = "down"      # de-escalating
    ECLECTIC = "eclectic"  # varied, no clear trend
    UNKNOWN  = "unknown"   # insufficient data


class Recommendation(str, Enum):
    APPROVE = "approve"  # score >= 0.70
    REVIEW  = "review"   # 0.40 <= score < 0.70
    REJECT  = "reject"   # score < 0.40


@dataclass
class Lot:
    lot_id:         str
    title:          str
    category:       str                # e.g. "painting", "sculpture", "print"
    estimate_low:   float              # EUR
    estimate_high:  float              # EUR
    reserve_price:  float              # EUR
    auction_date:   str                # ISO 8601 date string
    description:    str = ""
    artist:         str = ""           # Artist name — used for per-lot matching


@dataclass
class Bid:
    bid_id:     str
    bidder_id:  str
    lot_id:     str
    bid_amount: float                  # EUR
    timestamp:  str                    # ISO 8601
    outcome:    BidOutcome = BidOutcome.LOST
    hammer_price: Optional[float] = None   # set if this bid won the lot


@dataclass
class BidderProfile:
    bidder_id:   str
    name:        str
    email:       str
    bids:        list[Bid] = field(default_factory=list)
    # Populated by Odoo client
    country:     str = ""
    phone:       str = ""


@dataclass
class ScoreBreakdown:
    win_loss_rate:        float   # 0–1
    bid_count:            float   # 0–1
    reserve_ratio:        float   # 0–1  (bids above reserve / total bids)
    repeat_buyer:         float   # 0–1
    price_band_trajectory: float  # 0–1
    hammer_influence:     float   # 0–1

    # Metadata for transparency
    total_bids:           int  = 0
    total_wins:           int  = 0
    bids_above_reserve:   int  = 0
    distinct_lots_won:    int  = 0
    trajectory:           PriceBandTrajectory = PriceBandTrajectory.UNKNOWN
    insufficient_history: bool = False   # < 5 bids

    def weighted_total(self, weights: dict[str, float] | None = None) -> float:
        """Return weighted aggregate score. Default weights sum to 1.0."""
        w = weights or {
            "win_loss_rate":         0.25,
            "bid_count":             0.20,
            "reserve_ratio":         0.20,
            "repeat_buyer":          0.15,
            "price_band_trajectory": 0.10,
            "hammer_influence":      0.10,
        }
        return (
            self.win_loss_rate        * w.get("win_loss_rate",         0.25) +
            self.bid_count            * w.get("bid_count",             0.20) +
            self.reserve_ratio        * w.get("reserve_ratio",         0.20) +
            self.repeat_buyer         * w.get("repeat_buyer",          0.15) +
            self.price_band_trajectory* w.get("price_band_trajectory", 0.10) +
            self.hammer_influence     * w.get("hammer_influence",       0.10)
        )


@dataclass
class MatchedLot:
    lot_id:       str
    title:        str
    artist:       str
    category:     str
    estimate_low: float
    estimate_high: float
    auction_date: str
    match_reason: str    # e.g. "artist match", "price band match"


@dataclass
class LotScore:
    """Per-lot score for a bidder — computed against artist-specific bid history."""
    lot_id:        str
    title:         str
    artist:        str
    category:      str
    estimate_low:  float
    estimate_high: float
    auction_date:  str
    score:         float           # weighted score for this specific lot
    breakdown:     ScoreBreakdown  # dimension scores computed from artist-specific bids
    artist_bids:   int = 0         # number of past bids on this artist's lots


@dataclass
class EvaluationResult:
    bidder_id:      str
    bidder_name:    str
    bidder_email:   str
    score:          float
    recommendation: Recommendation
    breakdown:      ScoreBreakdown
    matched_lots:   list[MatchedLot] = field(default_factory=list)
    per_lot_scores: list[LotScore]   = field(default_factory=list)
    rejection_reasons: list[str]     = field(default_factory=list)
    evaluated_at:   str              = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    rationale:      str              = ""
    source_bids:    list             = field(default_factory=list)
