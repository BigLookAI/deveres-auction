"""
Deviours Auction — Reconciliation · Export service
===================================================

Serialises reconciliation results to the formats the reviewer needs and to a
clean Odoo-ready intermediate model. Keeping this separate means new output
targets (Odoo importer, PDF) plug in without touching the engine.
"""
from __future__ import annotations

import csv
import io
import json

from .models import DiffStatus, ReconResult, ReconSummary

FLAT_COLUMNS = [
    "buyer_number", "incoming_name", "classification", "recommendation",
    "confidence", "matched_by", "master_ref", "master_name",
    "changed_fields", "action",
]


def to_rows(results: list[ReconResult]) -> list[dict]:
    rows = []
    for r in results:
        rows.append({
            "buyer_number": r.buyer_number,
            "incoming_name": r.incoming_name,
            "classification": r.classification.value,
            "recommendation": r.recommendation.value,
            "confidence": round(r.confidence, 3),
            "matched_by": "|".join(r.matched_by),
            "master_ref": r.master_ref or "",
            "master_name": r.master_name,
            "changed_fields": "|".join(r.changed_fields),
            "action": r.action.value,
        })
    return rows


def to_csv(results: list[ReconResult]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FLAT_COLUMNS)
    w.writeheader()
    for row in to_rows(results):
        w.writerow(row)
    return buf.getvalue()


def to_json(results: list[ReconResult], summary: ReconSummary) -> str:
    return json.dumps({
        "summary": summary.to_dict(),
        "results": [r.to_dict(full=True) for r in results],
    }, indent=2, ensure_ascii=False)


def odoo_intermediate(results: list[ReconResult]) -> list[dict]:
    """Clean intermediate model, ready to feed a future Odoo importer.

    Each entry states the action, the canonical record (source of truth), the
    incoming record, and the difference report — so the importer needs no
    reconciliation logic of its own.
    """
    out = []
    for r in results:
        out.append({
            "action": r.action.value,                 # ADD | UPDATE | IGNORE | MANUAL_REVIEW
            "confidence": round(r.confidence, 3),
            "matched_by": r.matched_by,
            "canonical_record": r.master or None,      # None for NEW
            "canonical_ref": r.master_ref,
            "incoming_record": r.incoming,
            "buyer_number": r.buyer_number,
            "difference_report": [
                {"field": d.field, "current": d.current, "incoming": d.incoming,
                 "status": d.status.value, "significant": d.significant}
                for d in r.diffs if d.status != DiffStatus.UNCHANGED
            ],
            "lots": r.lots,
        })
    return out
