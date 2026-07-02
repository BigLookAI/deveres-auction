"""
deVeres Auction — Reconciliation · Odoo importer
==================================================

Consumes the Odoo-ready intermediate model (`export.odoo_intermediate`) and
applies the approved actions to Odoo `res.partner` via XML-RPC.

Safety model (this writes to the System of Record, so it is layered):
  1. `plan()`      — pure function, no connection: what WOULD happen.
  2. `execute(dry_run=True)`  — connects to Odoo READ-ONLY: verifies the
     connection, resolves existing partners, reports the exact operations.
  3. `execute(dry_run=False)` — performs writes, and ONLY if the environment
     variable RECON_ALLOW_ODOO_WRITE=1 is set. Otherwise it refuses.

Mapping (canonical → res.partner):
  name        ← "first_name last_name" (or company when no person name)
  email       ← email          phone  ← phone         mobile ← mobile
  street      ← address1       street2 ← address2
  city        ← town           zip    ← postcode
  ref         ← canonical client_ref (existing) / "BC-<buyer_number>" (new)
  comment     ← audit note (source file + reconciliation decision)
Only SIGNIFICANT changed/new fields are written on UPDATE — the canonical
record is never bulldozed. High-value flag: buyers whose winning bids total
over €10,000 get an ID-verification note (payments rule: debit card, bank
transfer, cheque or bank draft; ID required over €10,000).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("reconcile.odoo")

ID_CHECK_THRESHOLD_EUR = 10_000.0

# canonical field → res.partner field
PARTNER_FIELD_MAP = {
    "email":    "email",
    "phone":    "phone",
    "mobile":   "mobile",
    "address1": "street",
    "address2": "street2",
    "town":     "city",
    "postcode": "zip",
}


def _full_name(rec: dict) -> str:
    name = f"{rec.get('first_name', '')} {rec.get('last_name', '')}".strip()
    return name or rec.get("company", "") or "Unknown contact"


def _lots_total(entry: dict) -> float:
    total = 0.0
    for lot in entry.get("lots", []) or []:
        try:
            total += float(str(lot.get("winning_bid", "0")).replace(",", "") or 0)
        except ValueError:
            pass
    return total


@dataclass
class ImportOp:
    op:        str            # "create" | "write" | "skip"
    reason:    str
    ref:       str            # canonical ref or BC-<buyer_number>
    name:      str
    values:    dict = field(default_factory=dict)
    id_check:  bool = False   # winning bids total > €10,000 → verify ID
    partner_id: int | None = None

    def to_dict(self) -> dict:
        return {"op": self.op, "reason": self.reason, "ref": self.ref, "name": self.name,
                "values": self.values, "id_check_required": self.id_check,
                "partner_id": self.partner_id}


def plan_from_staging(entries: list[dict], source_file: str = "") -> list[ImportOp]:
    """Build the Odoo operations from STAGING entries — the official payload
    (2-Jul meeting). Only status='ready' rows are given to this function.

    change_type is explicit and unambiguous:
      'update' → ImportOp('write')  — only the approved changed/edited fields
      'create' → ImportOp('create') — the full approved record
    Approved values (which already include any manual edits) are the source;
    the incoming snapshot is never written directly.
    """
    ops: list[ImportOp] = []
    for e in entries:
        approved = e.get("approved") or {}
        changed  = list(dict.fromkeys((e.get("changed_fields") or []) +
                                      (e.get("edited_fields") or [])))
        high_value = _lots_total({"lots": e.get("lots") or []}) > ID_CHECK_THRESHOLD_EUR
        note = (f"Reconciled from Blue Cubes export {source_file or e.get('session','(upload)')} "
                f"— staged {e.get('change_type')} approved by {e.get('approved_by','?')} "
                f"at {e.get('approved_at','?')}.")
        if high_value:
            note += " HIGH VALUE: winning bids exceed EUR 10,000 — verify buyer ID before payment."

        if e.get("change_type") == "create":
            values = {"name": _full_name(approved),
                      "ref": f"BC-{e.get('buyer_number', '')}", "comment": note}
            for cf, pf in PARTNER_FIELD_MAP.items():
                if approved.get(cf):
                    values[pf] = approved[cf]
            ops.append(ImportOp("create", "approved new client (staged)", values["ref"],
                                values["name"], values, high_value))
        else:  # update
            values = {}
            for cf in changed:
                pf = PARTNER_FIELD_MAP.get(cf)
                if pf and approved.get(cf):
                    values[pf] = approved[cf]
            ref = str(e.get("master_ref") or "")
            if values:
                if high_value:
                    values["comment"] = note
                ops.append(ImportOp("write", "approved update (staged)", ref,
                                    e.get("name") or _full_name(approved), values, high_value))
            else:
                ops.append(ImportOp("skip", "staged update has no Odoo-mappable field changes",
                                    ref, e.get("name") or _full_name(approved), {}, high_value))
    return ops


def plan(intermediate: list[dict], source_file: str = "") -> list[ImportOp]:
    """Turn the intermediate model into concrete operations. Pure — no Odoo."""
    ops: list[ImportOp] = []
    for entry in intermediate:
        action = entry.get("action", "")
        inc = entry.get("incoming_record", {}) or {}
        canonical = entry.get("canonical_record") or {}
        high_value = _lots_total(entry) > ID_CHECK_THRESHOLD_EUR
        note = f"Reconciled from Blue Cubes export {source_file or '(upload)'} — action {action}."
        if high_value:
            note += " HIGH VALUE: winning bids exceed EUR 10,000 — verify buyer ID before payment."

        if action == "ADD":
            values = {"name": _full_name(inc), "ref": f"BC-{entry.get('buyer_number', '')}",
                      "comment": note}
            for cf, pf in PARTNER_FIELD_MAP.items():
                if inc.get(cf):
                    values[pf] = inc[cf]
            ops.append(ImportOp("create", "new client from export", values["ref"],
                                values["name"], values, high_value))
        elif action == "UPDATE":
            # write ONLY the significant changed/new fields from the diff report
            values = {}
            for d in entry.get("difference_report", []):
                if d.get("significant") and d.get("status") in ("changed", "new_info"):
                    pf = PARTNER_FIELD_MAP.get(d["field"])
                    if pf and d.get("incoming"):
                        values[pf] = d["incoming"]
            ref = str(entry.get("canonical_ref") or "")
            if values:
                if high_value:
                    values["comment"] = note
                ops.append(ImportOp("write", "approved update to existing client", ref,
                                    _full_name(canonical or inc), values, high_value))
            else:
                ops.append(ImportOp("skip", "update approved but no mappable field changes",
                                    ref, _full_name(canonical or inc), {}, high_value))
        elif action in ("IGNORE", "MANUAL_REVIEW"):
            ops.append(ImportOp("skip", f"action {action.lower()} — not imported",
                                str(entry.get("canonical_ref") or f"BC-{entry.get('buyer_number','')}"),
                                _full_name(canonical or inc), {}, high_value))
    return ops


class OdooImporter:
    """Applies ImportOps to res.partner. Resolves existing partners by `ref`
    first, then by exact email. Idempotent: re-running a plan re-resolves and
    writes the same values (no duplicate creates thanks to ref lookup)."""

    def __init__(self, client=None):
        if client is None:
            from pipeline.odoo_client import OdooClient   # reuses env config
            client = OdooClient()
        self.client = client

    # thin wrappers so tests can stub .client
    def _search_partner(self, domain: list) -> list[int]:
        return self.client._execute("res.partner", "search", domain, limit=2)

    def _resolve(self, op: ImportOp) -> int | None:
        ids = self._search_partner([[["ref", "=", op.ref]]]) if op.ref else []
        if not ids and op.values.get("email"):
            ids = self._search_partner([[["email", "=ilike", op.values["email"]]]])
        return ids[0] if ids else None

    def execute(self, ops: list[ImportOp], dry_run: bool = True) -> dict:
        if not dry_run and os.environ.get("RECON_ALLOW_ODOO_WRITE") != "1":
            raise PermissionError(
                "Refusing live Odoo write: set RECON_ALLOW_ODOO_WRITE=1 to enable. "
                "Run with dry_run=true to preview.")
        created = written = skipped = 0
        results = []
        for op in ops:
            if op.op == "skip":
                skipped += 1; results.append(op.to_dict()); continue
            partner_id = self._resolve(op)
            op.partner_id = partner_id
            if op.op == "create" and partner_id:
                # already exists (previous import) → idempotent write instead
                op.op, op.reason = "write", "already imported previously — updating"
            if dry_run:
                results.append(op.to_dict())
                created += 1 if op.op == "create" else 0
                written += 1 if op.op == "write" else 0
                continue
            if op.op == "create":
                op.partner_id = self.client._execute("res.partner", "create", op.values)
                created += 1
            elif op.op == "write" and partner_id:
                self.client._execute("res.partner", "write", [partner_id], op.values)
                written += 1
            else:
                skipped += 1
            results.append(op.to_dict())
        summary = {"dry_run": dry_run, "create": created, "write": written,
                   "skip": skipped, "total": len(ops),
                   "id_checks_required": sum(1 for o in ops if o.id_check)}
        log.info("odoo import (%s): %s", "dry-run" if dry_run else "LIVE", summary)
        return {"summary": summary, "operations": results}
