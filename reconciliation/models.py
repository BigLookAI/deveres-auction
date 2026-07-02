"""
deVeres Auction — Reconciliation · Data models
================================================

Typed, serialisable dataclasses shared across the engine, API and exporters.
These form the clean intermediate data model that later feeds Odoo import.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from .states import RecordState, initial_state


class Classification(str, Enum):
    NEW              = "new"               # 🟢 no match → ADD
    RETAIN           = "retain"            # 🔵 match, only cosmetic diffs → KEEP EXISTING
    UPDATE           = "update"            # 🟠 match, meaningful new info → UPDATE RECORD
    POSSIBLE_DUPLICATE = "possible_duplicate"  # 🟣 uncertain → MANUAL REVIEW


class Recommendation(str, Enum):
    ADD           = "ADD"
    KEEP_EXISTING = "KEEP EXISTING"
    UPDATE_RECORD = "UPDATE RECORD"
    MANUAL_REVIEW = "MANUAL REVIEW"


class DiffStatus(str, Enum):
    EQUIVALENT   = "equivalent"    # same after normalisation (formatting only)
    CHANGED      = "changed"       # both present, meaningfully different
    NEW_INFO     = "new_info"      # master empty, incoming has a value
    MISSING      = "missing"       # incoming empty, master has a value
    UNCHANGED    = "unchanged"     # identical raw values


# Actions the reviewer can assign (drives the Odoo-ready output).
class Action(str, Enum):
    ADD           = "ADD"
    UPDATE        = "UPDATE"
    IGNORE        = "IGNORE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass
class FieldDiff:
    field:    str
    label:    str
    current:  str            # canonical/master value (source of truth)
    incoming: str            # value from the uploaded Blue Cubes export
    status:   DiffStatus
    significant: bool = False   # True only for meaningful changes/new info

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; return d


@dataclass
class ReconResult:
    # identity
    index:          int
    buyer_number:   str
    incoming_name:  str
    # classification
    classification: Classification
    recommendation: Recommendation
    confidence:     float                 # 0–1 match confidence
    matched_by:     list[str] = field(default_factory=list)  # e.g. ["email","phone"]
    # linkage to master
    master_ref:     Optional[str] = None
    master_name:    str = ""
    # detail
    changed_fields: list[str]      = field(default_factory=list)
    diffs:          list[FieldDiff] = field(default_factory=list)
    incoming:       dict = field(default_factory=dict)   # canonical incoming snapshot
    master:         dict = field(default_factory=dict)   # canonical master snapshot
    lots:           list[dict] = field(default_factory=list)  # this buyer's lots/bids
    # reviewer decision (defaults to the recommendation)
    action:         Action = Action.MANUAL_REVIEW
    # ── lifecycle state engine (2-Jul meeting) ────────────────────────────────
    state:          Optional[RecordState] = None   # set from classification at build time
    edits:          dict = field(default_factory=dict)   # reviewer field edits (staging-only)
    approved_values: dict = field(default_factory=dict)  # final values written to staging
    history:        list[dict] = field(default_factory=list)  # state-transition audit trail
    match_evidence: dict = field(default_factory=dict)   # per-field similarity breakdown
    review_reason:  str = ""                              # why NEEDS_REVIEW fired (rule name)

    def __post_init__(self):
        if self.state is None:
            self.state = initial_state(self.classification)

    def record_transition(self, to_state: RecordState, actor: str, note: str = "") -> None:
        """Append a history entry and move to `to_state` (validation is the
        caller's job via states.validate_transition)."""
        from datetime import datetime, timezone
        self.history.append({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "from": self.state.value if self.state else None,
            "to": to_state.value, "actor": actor, "note": note,
        })
        self.state = to_state

    def to_dict(self, full: bool = False) -> dict:
        base = {
            "index": self.index,
            "buyer_number": self.buyer_number,
            "incoming_name": self.incoming_name,
            "classification": self.classification.value,
            "recommendation": self.recommendation.value,
            "confidence": round(self.confidence, 4),
            "matched_by": self.matched_by,
            "master_ref": self.master_ref,
            "master_name": self.master_name,
            "changed_fields": self.changed_fields,
            "action": self.action.value,
            "state": self.state.value,
            "edited": bool(self.edits),
            "review_reason": self.review_reason,
        }
        if full:
            base["diffs"] = [d.to_dict() for d in self.diffs]
            base["incoming"] = self.incoming
            base["master"] = self.master
            base["lots"] = self.lots
            base["edits"] = self.edits
            base["approved_values"] = self.approved_values
            base["history"] = self.history
            base["match_evidence"] = self.match_evidence
        return base


def field_diff_from_dict(d: dict) -> "FieldDiff":
    return FieldDiff(field=d["field"], label=d["label"], current=d.get("current", ""),
                     incoming=d.get("incoming", ""), status=DiffStatus(d["status"]),
                     significant=bool(d.get("significant", False)))


def recon_result_from_dict(d: dict) -> "ReconResult":
    """Rebuild a full ReconResult from to_dict(full=True) output — used to restore
    a persisted reconciliation session across restarts/reloads."""
    return ReconResult(
        index=d["index"], buyer_number=d.get("buyer_number", ""),
        incoming_name=d.get("incoming_name", ""),
        classification=Classification(d["classification"]),
        recommendation=Recommendation(d["recommendation"]),
        confidence=float(d.get("confidence", 0.0)),
        matched_by=list(d.get("matched_by", [])),
        master_ref=d.get("master_ref"), master_name=d.get("master_name", ""),
        changed_fields=list(d.get("changed_fields", [])),
        diffs=[field_diff_from_dict(x) for x in d.get("diffs", [])],
        incoming=d.get("incoming", {}), master=d.get("master", {}),
        lots=d.get("lots", []),
        action=Action(d.get("action", "MANUAL_REVIEW")),
        # lifecycle fields — absent in pre-state-engine sessions, so default from
        # the classification (backwards compatible restore)
        state=RecordState(d["state"]) if d.get("state") else None,
        edits=d.get("edits", {}) or {},
        approved_values=d.get("approved_values", {}) or {},
        history=d.get("history", []) or [],
        match_evidence=d.get("match_evidence", {}) or {},
        review_reason=d.get("review_reason", ""),
    )


@dataclass
class ReconSummary:
    total:            int = 0
    new:              int = 0
    retain:           int = 0
    update:           int = 0
    manual_review:    int = 0
    ignored_diffs:    int = 0     # count of equivalent (formatting-only) field diffs
    avg_confidence:   float = 0.0
    master_records:   int = 0
    incoming_rows:    int = 0
    processing_ms:    float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["avg_confidence"] = round(self.avg_confidence, 4)
        d["processing_ms"] = round(self.processing_ms, 1)
        return d
