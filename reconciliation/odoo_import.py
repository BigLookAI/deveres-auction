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
# NOTE: Odoo 19 removed res.partner.mobile (merged into phone) — verified via
# fields_get on the restored April-test instance. A canonical mobile therefore
# maps to phone when phone is empty, and is appended to the comment otherwise
# (see _apply_mobile) so the number is never silently dropped.
PARTNER_FIELD_MAP = {
    "email":    "email",
    "phone":    "phone",
    "address1": "street",
    "address2": "street2",
    "town":     "city",
    "postcode": "zip",
}

# Fields that map to res.partner RELATIONS and need a name→id lookup at execute
# time (county → state_id, country → country_id). Default convention pending
# Fintan's confirmation; unresolved names fall back into the comment, never lost.
LOOKUP_FIELD_MAP = {
    "county":  "__state_name",     # resolved to res.partner.state_id
    "country": "__country_name",   # resolved to res.partner.country_id
}


def _full_name(rec: dict) -> str:
    name = f"{rec.get('first_name', '')} {rec.get('last_name', '')}".strip()
    return name or rec.get("company", "") or "Unknown contact"


def _apply_mobile(values: dict, mobile: str) -> None:
    """Odoo 19 has no res.partner.mobile: use it as the phone when none is
    set, otherwise keep it audit-visible in the comment."""
    if not mobile:
        return
    if not values.get("phone"):
        values["phone"] = mobile
    elif mobile != values["phone"]:
        values["comment"] = (values.get("comment", "")
                             + f" Mobile (no Odoo field): {mobile}.").strip()


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
    # post-push verification (6-Jul meeting: "every push must be visible inside
    # Odoo") — after a live write the partner is read back and compared.
    verified:  bool | None = None      # None = not applicable (dry-run/skip)
    verify_mismatch: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"op": self.op, "reason": self.reason, "ref": self.ref, "name": self.name,
                "values": self.values, "id_check_required": self.id_check,
                "partner_id": self.partner_id, "verified": self.verified,
                "verify_mismatch": self.verify_mismatch}


def plan_from_staging(entries: list[dict], source_file: str = "",
                      schema=None) -> list[ImportOp]:
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
        # ── payload validation: a bad staging row becomes an explicit skip, it
        # never reaches Odoo and never silently disappears ─────────────────────
        problems = []
        if not any(approved.get(f) for f in ("first_name", "last_name", "company")):
            problems.append("no name (first/last/company all empty)")
        if e.get("change_type") == "create" and not e.get("buyer_number"):
            problems.append("create without a buyer number (ref would collide)")
        if e.get("change_type") == "update" and not e.get("master_ref"):
            problems.append("update without a master ref")
        # Phase 4 P3 belt-and-braces: even if an invalid dropdown value slips
        # into staging (legacy rows), it must not reach Odoo — explicit skip.
        if schema is not None:
            from .validation import validate_incoming, blocking_issues
            bad = blocking_issues(validate_incoming(
                {k: approved.get(k, "") for k in ("county", "country")}, schema))
            for i in bad:
                problems.append(f"invalid {i.label} \u201c{i.value}\u201d — correct or "
                                f"clear it before pushing"
                                + (f" (suggested: {', '.join(i.suggestions)})"
                                   if i.suggestions else ""))
        if problems:
            ops.append(ImportOp("skip", "VALIDATION: " + "; ".join(problems),
                                str(e.get("master_ref") or f"BC-{e.get('buyer_number','')}"),
                                e.get("name") or _full_name(approved), {}, False))
            log.warning("odoo import plan: staging row %s/%s rejected: %s",
                        e.get("session"), e.get("record_index"), "; ".join(problems))
            continue
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
            _apply_mobile(values, approved.get("mobile", ""))
            for cf, pseudo in LOOKUP_FIELD_MAP.items():
                if approved.get(cf):
                    values[pseudo] = approved[cf]
            ops.append(ImportOp("create", "approved new client (staged)", values["ref"],
                                values["name"], values, high_value))
        else:  # update
            values = {}
            for cf in changed:
                pf = PARTNER_FIELD_MAP.get(cf)
                if pf and approved.get(cf):
                    values[pf] = approved[cf]
                pseudo = LOOKUP_FIELD_MAP.get(cf)
                if pseudo and approved.get(cf):
                    values[pseudo] = approved[cf]   # resolved to an id at execute time
            if "mobile" in changed:
                _apply_mobile(values, approved.get("mobile", ""))
            # Any address-family change writes the WHOLE approved address
            # block (street, street2, city, zip, state, country). Pre-clean
            # masters hold town/county/postcode inside a concatenated street2;
            # writing only the individually-changed fields leaves records
            # half-normalised (street2 keeps the blob, city/state stay empty —
            # Eileen Costelloe #81012, 14-Jul screenshots). Approved values
            # are the operator-reviewed truth: land them field-for-field, in
            # one pass. Empty approved fields are never written (no deletes).
            _ADDR_FAMILY = ("address1", "address2", "town", "county",
                            "postcode", "country")
            if set(_ADDR_FAMILY) & set(changed):
                for cf in _ADDR_FAMILY:
                    if not approved.get(cf):
                        continue
                    pf, pseudo = PARTNER_FIELD_MAP.get(cf), LOOKUP_FIELD_MAP.get(cf)
                    if pf and pf not in values:
                        values[pf] = approved[cf]
                    if pseudo and pseudo not in values:
                        values[pseudo] = approved[cf]
                # Approved Address 2 is EMPTY and the master's street2 blob is
                # fully redundant vs the dedicated fields being written →
                # CLEAR it (never clears unique information: any token not
                # covered keeps the field untouched).
                if not approved.get("address2") and "street2" not in values:
                    from .classify import street2_redundant
                    mas2 = ((e.get("original") or {}).get("address2") or "").strip()
                    if mas2 and street2_redundant(mas2, approved):
                        values["street2"] = False
            # Any remaining field with no mapping at all (currently: company) is
            # surfaced in the op reason — never silently dropped.
            unmapped = {cf: approved.get(cf, "") for cf in changed
                        if cf not in PARTNER_FIELD_MAP and cf not in LOOKUP_FIELD_MAP
                        and cf != "mobile" and approved.get(cf)}
            ref = str(e.get("master_ref") or "")
            # Odoo-sourced master → we know the exact partner id already; the
            # importer writes by id instead of re-searching ref/email.
            pid = (e.get("original") or {}).get("odoo_id")
            if values:
                if high_value:
                    values["comment"] = note
                reason = "approved update (staged)"
                if unmapped:
                    reason += (" — NOTE unmapped field changes not written: "
                               + ", ".join(f"{k}={v}" for k, v in unmapped.items()))
                ops.append(ImportOp("write", reason, ref,
                                    e.get("name") or _full_name(approved), values, high_value,
                                    partner_id=int(pid) if pid else None))
            else:
                reason = "staged update has no Odoo-mappable field changes"
                if unmapped:
                    reason += (" (unmapped: "
                               + ", ".join(f"{k}={v}" for k, v in unmapped.items()) + ")")
                ops.append(ImportOp("skip", reason,
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
            _apply_mobile(values, inc.get("mobile", ""))
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
                    elif d["field"] == "mobile" and d.get("incoming"):
                        _apply_mobile(values, d["incoming"])
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
        # execute_kw positional args are [domain]; _execute(*args) adds that
        # wrapping itself, so the domain is passed here WITHOUT extra nesting.
        return self.client._execute("res.partner", "search", domain, limit=2)

    def _resolve(self, op: ImportOp) -> int | None:
        # 1. Exact database id (master fetched from Odoo) — verified, not
        #    trusted blindly: the partner may have been deleted since the fetch.
        if op.partner_id:
            if self._search_partner([["id", "=", op.partner_id]]):
                return op.partner_id
            log.warning("odoo import: staged partner_id=%s no longer exists — "
                        "falling back to ref/email resolution", op.partner_id)
        # 2. "ODOO-<id>" is our synthetic ref for partners without one.
        if op.ref.startswith("ODOO-") and op.ref[5:].isdigit():
            ids = self._search_partner([["id", "=", int(op.ref[5:])]])
            if ids:
                return ids[0]
        ids = self._search_partner([["ref", "=", op.ref]]) if op.ref else []
        if not ids and op.values.get("email"):
            ids = self._search_partner([["email", "=ilike", op.values["email"]]])
        return ids[0] if ids else None

    @staticmethod
    def _state_name_candidates(name: str) -> list[str]:
        """Lookup candidates for a Blue Cubes county value, in priority order:
        the raw value, then with the Irish 'Co./County' prefix stripped, then
        known aliases. Odoo stores 'Wicklow', the exports say 'Co. Wicklow'."""
        import re
        name = name.strip().rstrip(".,;")   # 'Cork.' must match Odoo's 'Cork'
        cands = [name]
        # 'Co. Wicklow', 'County Dublin', and the no-space 'CO.DUBLIN' the
        # real April export contains — but never bare 'Co…' words like Cork
        stripped = re.sub(r"^\s*(co\.\s*|co\s+|county\s+)", "", name, flags=re.I).strip()
        if stripped and stripped.lower() != name.lower():
            cands.append(stripped)
        # Dublin postal districts ('Dublin 8', 'DUBLIN 6', 'Dublin 6W') are
        # city sub-zones, not counties — the county is Dublin
        for cand in list(cands):
            if re.match(r"^dublin\s*\d+\s*w?$", cand, flags=re.I):
                cands.append("Dublin")
                break
        aliases = {"n. ireland": "Northern Ireland", "n ireland": "Northern Ireland"}
        for cand in list(cands):
            alias = aliases.get(cand.lower())
            if alias and alias not in cands:
                cands.append(alias)
        return cands

    def _resolve_lookups(self, op: ImportOp) -> None:
        """Turn the __country_name/__state_name pseudo-fields into country_id /
        state_id via name lookup. An unresolved name is appended to the comment
        (audit-visible) rather than dropped or guessed."""
        country_name = op.values.pop("__country_name", None)
        state_name = op.values.pop("__state_name", None)
        unresolved = []
        country_id = None
        if country_name:
            domain = [["name", "=ilike", country_name]]
            if len(country_name) == 2:                  # 'IE' / 'GB' style codes
                domain = ["|", ["name", "=ilike", country_name],
                          ["code", "=ilike", country_name]]
            ids = self.client._execute("res.country", "search", domain, limit=1)
            if ids:
                country_id = ids[0]
                op.values["country_id"] = country_id
            else:
                unresolved.append(f"country={country_name}")
        if state_name:
            ids = []
            for cand in self._state_name_candidates(state_name):
                domain = [["name", "=ilike", cand]]
                if country_id:
                    domain.append(["country_id", "=", country_id])
                ids = self.client._execute("res.country.state", "search", domain, limit=1)
                if ids:
                    break
            if ids:
                op.values["state_id"] = ids[0]
            else:
                unresolved.append(f"county/state={state_name}")
        if unresolved:
            extra = "Unresolved location values (set manually): " + ", ".join(unresolved)
            op.values["comment"] = (op.values.get("comment", "") + " " + extra).strip()

    def _tag_contact_type(self, partner_id: int | None) -> None:
        """Newly created clients get the SOR Contact Type 'Contact' so they
        appear in the SOR Contacts views (which filter on contact_types).
        Best-effort: silently skipped on an Odoo without the SOR modules."""
        if not partner_id:
            return
        try:
            ct = self.client._execute("sor.contact.type", "search",
                                      [["code", "=", "contact"]], limit=1)
            if ct:
                self.client._execute("res.partner", "write", [partner_id],
                                     {"contact_types": [[4, ct[0]]]})
        except Exception:                                 # noqa: BLE001
            log.debug("sor contact-type tagging skipped for partner %s", partner_id)

    def _verify(self, op: ImportOp) -> None:
        """Read the partner back from Odoo and confirm every written scalar
        field actually landed (the 6-Jul 'Verify Update' step). comment is
        excluded (Odoo wraps it in HTML); relational writes compare by id."""
        fields = [f for f in op.values if f != "comment" and not f.startswith("__")]
        if not fields or not op.partner_id:
            op.verified = bool(op.partner_id)
            return
        try:
            got = self.client._execute("res.partner", "read", [op.partner_id],
                                       fields=fields)[0]
        except Exception as exc:                          # noqa: BLE001
            op.verified = False
            op.verify_mismatch = {"_readback": f"{type(exc).__name__}: {exc}"}
            return
        mismatch = {}
        for f in fields:
            want, have = op.values[f], got.get(f)
            if isinstance(have, (list, tuple)) and len(have) == 2:
                have = have[0]                            # many2one → id
            if (have or "") != (want or ""):
                mismatch[f] = {"wrote": want, "read_back": have}
        op.verified = not mismatch
        op.verify_mismatch = mismatch

    def execute(self, ops: list[ImportOp], dry_run: bool = True) -> dict:
        """Apply the plan. One failing operation never aborts the batch: it is
        reported as op='error' with the exception message and the rest proceed
        (each op is independent, and creates are idempotent by ref on re-push).
        Every operation is logged with its ref, values written and duration."""
        if not dry_run and os.environ.get("RECON_ALLOW_ODOO_WRITE") != "1":
            raise PermissionError(
                "Refusing live Odoo write: set RECON_ALLOW_ODOO_WRITE=1 to enable. "
                "Run with dry_run=true to preview.")
        import time as _time
        created = written = skipped = errors = 0
        results = []
        for op in ops:
            t0 = _time.perf_counter()
            if op.op == "skip":
                skipped += 1
                results.append(op.to_dict())
                log.info("odoo import skip ref=%s: %s", op.ref, op.reason)
                continue
            try:
                partner_id = self._resolve(op)
                op.partner_id = partner_id
                if op.op == "create" and partner_id:
                    # already exists (previous import) → idempotent write instead
                    op.op, op.reason = "write", "already imported previously — updating"
                if not dry_run:
                    self._resolve_lookups(op)  # county/country name → state_id/country_id
                if dry_run:
                    created += 1 if op.op == "create" else 0
                    written += 1 if op.op == "write" else 0
                elif op.op == "create":
                    op.partner_id = self.client._execute("res.partner", "create", op.values)
                    created += 1
                    self._tag_contact_type(op.partner_id)
                    self._verify(op)
                elif op.op == "write" and partner_id:
                    self.client._execute("res.partner", "write", [partner_id], op.values)
                    written += 1
                    self._verify(op)
                else:
                    op.op, op.reason = "skip", (op.reason +
                        " — no matching partner found by ref or email; nothing written")
                    skipped += 1
                log.info("odoo import %s%s ref=%s partner_id=%s fields=%s in %.0fms",
                         op.op, " (dry-run)" if dry_run else "", op.ref, op.partner_id,
                         sorted(k for k in op.values if not k.startswith("__")),
                         (_time.perf_counter() - t0) * 1000)
            except Exception as exc:                     # noqa: BLE001 — per-op isolation
                errors += 1
                op.op, op.reason = "error", f"{type(exc).__name__}: {exc}"
                log.exception("odoo import FAILED ref=%s name=%s", op.ref, op.name)
            results.append(op.to_dict())
        summary = {"dry_run": dry_run, "create": created, "write": written,
                   "skip": skipped, "error": errors, "total": len(ops),
                   "verified": sum(1 for o in ops if o.verified),
                   "verify_failed": sum(1 for o in ops if o.verified is False),
                   "id_checks_required": sum(1 for o in ops if o.id_check)}
        log.info("odoo import (%s): %s", "dry-run" if dry_run else "LIVE", summary)
        return {"summary": summary, "operations": results}
