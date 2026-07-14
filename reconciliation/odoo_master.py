"""
deVeres Auction — Reconciliation · Odoo master source
=======================================================

Fetches the canonical client list FROM Odoo `res.partner` (3-Jul-2026 meeting:
"instead of reconciling with the client spreadsheet, you're now reconciling
with the Odoo contact list via the API"). The result is the same canonical
record shape `MasterRepository` builds from All Clients.csv, so the matching /
classification / staging / push pipeline is completely unchanged — only the
source of truth moves from a static file to the live system of record.

Mapping (res.partner → canonical):
  ref        → client_ref   (fallback "ODOO-<id>" for the few partners w/o ref)
  name       → first_name + last_name (person) / company (is_company)
  email      → email        phone → phone      (Odoo 19 has no mobile field)
  street     → address1     street2 → address2
  city       → town         zip → postcode
  state_id   → county       country_id → country   (display names)
  id         → odoo_id      (carried through staging so the importer can write
                             by database id — exact, no ref/email re-search)

Name splitting is heuristic (first token → first_name, rest → last_name) but
SAFE: matching normalises names to order-independent token sets and the diff
report compares the combined name, so the split never changes an outcome.
"""
from __future__ import annotations

import logging
import re
import time

log = logging.getLogger("reconcile.odoo")

PARTNER_FETCH_FIELDS = [
    "id", "name", "ref", "email", "phone", "street", "street2",
    "city", "zip", "state_id", "country_id", "is_company", "comment",
]

FETCH_BATCH = 1000


def _rel_name(value) -> str:
    """Odoo many2one values arrive as [id, "Display Name"] or False."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return str(value[1])
    return ""


def _text(value) -> str:
    """Odoo empty scalar fields arrive as False, never None/""."""
    return str(value).strip() if value else ""


def partner_to_canonical(p: dict) -> dict:
    """Map one res.partner read() dict onto the canonical contact schema."""
    name = _text(p.get("name"))
    if p.get("is_company"):
        first, last, company = "", "", name
    else:
        parts = name.split(None, 1)
        first = parts[0] if parts else ""
        last = parts[1] if len(parts) > 1 else ""
        company = ""
    return {
        "client_ref": _text(p.get("ref")) or f"ODOO-{p['id']}",
        "odoo_id":    int(p["id"]),
        "title":      "",
        "first_name": first,
        "last_name":  last,
        "company":    company,
        "email":      _text(p.get("email")),
        "phone":      _text(p.get("phone")),
        "mobile":     "",                       # no res.partner.mobile in Odoo 19
        "address1":   _text(p.get("street")),
        "address2":   _text(p.get("street2")),
        "address3":   "",
        "town":       _text(p.get("city")),
        "county":     _rel_name(p.get("state_id")),
        "country":    _rel_name(p.get("country_id")),
        "postcode":   _text(p.get("zip")),
        # The importer records counties it could NOT map to a res.country.state
        # (e.g. Northern Irish counties — base Odoo ships no GB states) in the
        # partner comment. Surface that marker so classification knows the
        # county has already been handled as far as Odoo allows — otherwise
        # the same record re-flags as an update on every upload, forever.
        "_unresolved_county": _unresolved_county(p.get("comment")),
    }


_UNRESOLVED_COUNTY_RE = re.compile(r"county/state=([^,<]+)")


def _unresolved_county(comment) -> str:
    m = _UNRESOLVED_COUNTY_RE.search(str(comment or ""))
    return m.group(1).strip() if m else ""


def fetch_partners(client=None, batch: int = FETCH_BATCH) -> list[dict]:
    """Fetch every active partner as canonical records, in id-ordered batches
    (stable pagination even if partners are created mid-fetch)."""
    if client is None:
        from pipeline.odoo_client import OdooClient   # env-configured
        client = OdooClient()
    records: list[dict] = []
    offset = 0
    t0 = time.perf_counter()
    while True:
        rows = client._execute(
            "res.partner", "search_read", [],
            fields=PARTNER_FETCH_FIELDS, offset=offset, limit=batch, order="id")
        records.extend(partner_to_canonical(r) for r in rows)
        offset += len(rows)
        if len(rows) < batch:
            break
    log.info("odoo master fetch: %d partners in %.0fms (%d batches of %d)",
             len(records), (time.perf_counter() - t0) * 1000,
             (offset + batch - 1) // batch if offset else 0, batch)
    return records
