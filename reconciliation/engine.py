"""
deVeres Auction — Reconciliation · Engine (service layer)
==========================================================

Orchestrates the pipeline: for each uploaded buyer, find the best canonical
match, classify it, and build a full ReconResult with a field-level diff report.
Returns the results plus an aggregate summary for the dashboard.
"""
from __future__ import annotations

import time

from .classify import classify, default_action
from .matching import MasterIndex
from .models import Classification, DiffStatus, ReconResult, ReconSummary
from .repository import MasterRepository


class ReconciliationEngine:
    def __init__(self, master: MasterRepository):
        self.master = master
        self.index: MasterIndex = master.index

    def reconcile_one(self, index: int, inc: dict) -> ReconResult:
        cand = self.index.best_match(inc)
        classification, recommendation, conf, matched_by, diffs, mas, review_reason = classify(inc, cand)
        # changed_fields means "fields that would change the master" — a NEW
        # client has no master, so its diffs (all vs empty) never count here.
        changed = [d.label for d in diffs if d.significant and d.status in
                   (DiffStatus.CHANGED, DiffStatus.NEW_INFO)] if mas else []
        name = f"{inc.get('first_name','')} {inc.get('last_name','')}".strip()
        master_name = f"{mas.get('first_name','')} {mas.get('last_name','')}".strip() if mas else ""
        evidence = self._evidence(cand) if cand and mas else {}
        return ReconResult(
            index=index,
            buyer_number=inc.get("buyer_number", ""),
            incoming_name=name,
            classification=classification,
            recommendation=recommendation,
            confidence=conf,
            matched_by=matched_by,
            master_ref=(mas.get("client_ref") if mas else None),
            master_name=master_name,
            changed_fields=changed,
            diffs=diffs,
            incoming={k: inc.get(k, "") for k in
                      ("first_name", "last_name", "email", "phone", "company",
                       "address1", "address2", "town", "county", "postcode", "country")},
            master=mas or {},
            lots=inc.get("lots", []),
            action=default_action(classification),
            match_evidence=evidence,
            review_reason=review_reason,
        )

    @staticmethod
    def _evidence(cand) -> dict:
        """Explainable-matching breakdown: for every compared field, its raw
        similarity, its weight, and its contribution to the final confidence.
        This is what the UI renders as 'Matched because: …'."""
        from .matching import WEIGHTS, STRONG_MATCH_FLOOR
        sims = cand.field_sims or {}
        present = {f: WEIGHTS[f] for f in sims if f in WEIGHTS}
        wsum = sum(present.values()) or 1.0
        fields = {
            f: {"similarity": round(sims[f], 4),
                "weight": present[f],
                "contribution": round(sims[f] * present[f] / wsum, 4),
                "exact": sims[f] >= 0.99}
            for f in present
        }
        weighted = round(sum(v["contribution"] for v in fields.values()), 4)
        floored = ("email" in cand.matched_by or "phone" in cand.matched_by) \
                  and weighted < STRONG_MATCH_FLOOR
        return {"fields": fields, "weighted_score": weighted,
                "matched_by": cand.matched_by,
                "strong_id_floor_applied": bool(floored),
                "final_confidence": cand.score,
                "note": ("Exact email/phone is decisive: confidence floored at "
                         f"{STRONG_MATCH_FLOOR:.0%}." if floored else "")}

    def run(self, incoming: list[dict]) -> tuple[list[ReconResult], ReconSummary]:
        t0 = time.perf_counter()
        results = [self.reconcile_one(i, inc) for i, inc in enumerate(incoming)]

        s = ReconSummary(total=len(results), master_records=len(self.master),
                         incoming_rows=len(incoming))
        conf_sum = 0.0
        for r in results:
            conf_sum += r.confidence
            if r.classification == Classification.NEW:              s.new += 1
            elif r.classification == Classification.RETAIN:         s.retain += 1
            elif r.classification == Classification.UPDATE:         s.update += 1
            elif r.classification == Classification.POSSIBLE_DUPLICATE: s.manual_review += 1
            s.ignored_diffs += sum(1 for d in r.diffs if d.status == DiffStatus.EQUIVALENT)
        s.avg_confidence = conf_sum / len(results) if results else 0.0
        s.processing_ms = (time.perf_counter() - t0) * 1000.0
        return results, s
