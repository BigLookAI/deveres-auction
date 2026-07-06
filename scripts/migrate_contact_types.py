#!/usr/bin/env python3
"""
deVeres — migrate synthetic demo contacts to Contact Type = Contact.

6-Jul-2026 meeting step 2: every synthetic contact in the demo Odoo must be a
person contact ("Contact Type = Contact", NOT Company) with address type
'contact'. This script:

  1. reports the before counts (company_type / type distribution),
  2. sets is_company=False + type='contact' on every synthetic partner that
     is not one (companies that exist by design — e.g. the Odoo company
     record itself, or partners that are a parent company — are untouched),
  3. verifies the partner-model structure the client asked about:
     individual contact / parent company / child contact / address hierarchy,
     by creating a disposable TEST company + child and checking that the
     child's address follows the parent (then deleting both),
  4. writes a validation report with before/after counts.

Idempotent — re-running finds nothing left to migrate.

Env: ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD (same as the app).
Usage: python3 scripts/migrate_contact_types.py [--report PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client
from datetime import datetime, timezone
from pathlib import Path

URL = os.environ.get("ODOO_URL", "http://localhost:8071")
DB = os.environ.get("ODOO_DB", "deveres_demo")
USER = os.environ.get("ODOO_USERNAME", "admin")
PWD = os.environ.get("ODOO_PASSWORD", "admin")


def connect():
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, PWD, {})
    if not uid:
        sys.exit(f"Authentication failed for {USER} on {DB} at {URL}")
    return uid, xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")


def x(models, uid, model, method, *args, **kw):
    return models.execute_kw(DB, uid, PWD, model, method, list(args), kw)


def counts(models, uid) -> dict:
    out = {}
    for label, domain in (
        ("total_active", []),
        ("companies", [["is_company", "=", True]]),
        ("individuals", [["is_company", "=", False]]),
        ("type_contact", [["type", "=", "contact"]]),
        ("type_other", [["type", "!=", "contact"]]),
        ("with_parent", [["parent_id", "!=", False]]),
    ):
        out[label] = x(models, uid, "res.partner", "search_count", domain)
    return out


def verify_hierarchy(models, uid) -> list[str]:
    """Create a disposable parent company + child contact, verify the partner
    model behaves correctly (individual / parent / child / address sync),
    then remove both. Returns human-readable check results."""
    checks = []
    company_id = child_id = None
    try:
        company_id = x(models, uid, "res.partner", "create", {
            "name": "TEST Hierarchy Co (disposable)", "is_company": True,
            "street": "1 Verification Quay", "city": "Dublin", "zip": "D01TEST"})
        c = x(models, uid, "res.partner", "read", [company_id],
              fields=["is_company", "type", "street"])[0]
        checks.append(("Parent company record (is_company=True)", c["is_company"] is True))

        child_id = x(models, uid, "res.partner", "create", {
            "name": "TEST Child Contact (disposable)", "is_company": False,
            "parent_id": company_id, "type": "contact"})
        ch = x(models, uid, "res.partner", "read", [child_id],
               fields=["is_company", "type", "parent_id", "street", "commercial_partner_id"])[0]
        checks.append(("Child contact record (is_company=False, type=contact)",
                       ch["is_company"] is False and ch["type"] == "contact"))
        checks.append(("Child linked to parent company",
                       bool(ch["parent_id"]) and ch["parent_id"][0] == company_id))
        checks.append(("Address hierarchy: child type=contact inherits parent street",
                       (ch.get("street") or "") == "1 Verification Quay"))
        checks.append(("commercial_partner resolves to the parent company",
                       bool(ch.get("commercial_partner_id"))
                       and ch["commercial_partner_id"][0] == company_id))

        indiv_id = x(models, uid, "res.partner", "create", {
            "name": "TEST Individual (disposable)", "is_company": False,
            "street": "2 Solo Street", "city": "Cork"})
        iv = x(models, uid, "res.partner", "read", [indiv_id],
               fields=["is_company", "type", "street"])[0]
        checks.append(("Standalone individual keeps its own address",
                       iv["is_company"] is False and iv["street"] == "2 Solo Street"))
        x(models, uid, "res.partner", "unlink", [indiv_id])
    except Exception as exc:                              # noqa: BLE001
        checks.append((f"hierarchy verification aborted: {exc}", False))
    finally:
        for pid in (child_id, company_id):
            if pid:
                try:
                    x(models, uid, "res.partner", "unlink", [pid])
                except Exception:                          # noqa: BLE001
                    pass
    return [f"- {'✅' if ok else '❌'} {label}" for label, ok in checks]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", default="output/contact-migration-report.md")
    args = ap.parse_args()

    uid, models = connect()
    before = counts(models, uid)
    print(f"before: {before}")

    # Synthetic contacts = partners that must be person contacts. Excluded by
    # design: the Odoo company record (linked from res.company) and any partner
    # that other contacts use as their parent (a real parent company).
    company_partner_ids = [c["partner_id"][0] for c in
                           x(models, uid, "res.company", "search_read", [],
                             fields=["partner_id"])]
    parent_ids = {p["parent_id"][0] for p in
                  x(models, uid, "res.partner", "search_read",
                    [["parent_id", "!=", False]], fields=["parent_id"])}
    keep_company = set(company_partner_ids) | parent_ids

    wrong_company = x(models, uid, "res.partner", "search",
                      [["is_company", "=", True], ["id", "not in", sorted(keep_company)]])
    wrong_type = x(models, uid, "res.partner", "search",
                   [["type", "!=", "contact"], ["id", "not in", sorted(keep_company)]])

    migrated = {"is_company": len(wrong_company), "type": len(wrong_type)}
    if not args.dry_run:
        if wrong_company:
            x(models, uid, "res.partner", "write", wrong_company,
              {"is_company": False, "company_type": "person"})
        if wrong_type:
            x(models, uid, "res.partner", "write", wrong_type, {"type": "contact"})

    after = counts(models, uid)
    hierarchy = verify_hierarchy(models, uid)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    lines = [
        "# Contact-Type Migration & Validation Report",
        "",
        f"- **When:** {ts}   ·   **Target:** {URL} db `{DB}`",
        f"- **Mode:** {'DRY-RUN (no writes)' if args.dry_run else 'live'}",
        "",
        "## Rule applied",
        "",
        "Every synthetic partner ⇒ `Contact Type = Contact` (`is_company=False`,"
        " `company_type='person'`) and address `type='contact'`.",
        "Excluded by design: the res.company partner record"
        f" ({len(company_partner_ids)}) and genuine parent companies"
        f" ({len(parent_ids - set(company_partner_ids))}).",
        "",
        "## Before / after counts",
        "",
        "| Measure | Before | After |",
        "|---|---|---|",
        *(f"| {k} | {before[k]} | {after[k]} |" for k in before),
        "",
        f"**Migrated:** {migrated['is_company']} partner(s) Company→Contact, "
        f"{migrated['type']} partner(s) address-type→contact.",
        "",
        "## Partner-model structure checks (disposable test records)",
        "",
        *hierarchy,
        "",
    ]
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"report written: {report}")


if __name__ == "__main__":
    main()
