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
        classification, recommendation, conf, matched_by, diffs, mas = classify(inc, cand)
        changed = [d.label for d in diffs if d.significant and d.status in
                   (DiffStatus.CHANGED, DiffStatus.NEW_INFO)]
        name = f"{inc.get('first_name','')} {inc.get('last_name','')}".strip()
        master_name = f"{mas.get('first_name','')} {mas.get('last_name','')}".strip() if mas else ""
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
        )

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
