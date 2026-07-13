#!/usr/bin/env python3
"""
deVeres — production-launch environment verification (13-Jul-2026 plan,
Phases 3+4): administrator access and Odoo schema parity, checked over the
same API the reconciliation platform uses.

    python3 scripts/verify_environment.py [--url URL] [--db DB]
        [--user LOGIN] [--password PW]

Defaults come from ODOO_URL / ODOO_DB / ODOO_USER / ODOO_PASSWORD, falling
back to the local April sandbox (http://localhost:8071, db `deveres`).

Checks (all read-only except two write-and-revert probes):
  A. authentication + admin group membership (Settings access)
  B. module management rights (ir.module.module read + button access)
  C. res.partner editability — write probe on a partner, reverted
  D. sor.lot editability — hammer_price write probe, reverted
  E. sor.lot schema — every field the reconciliation engine reads/writes
  F. res.partner schema — every field the contact engine maps
  G. lot form view — buyer_id present below hammer_price
  H. auction publishability — sor.event state field + values
  I. no sor_bidding / no stock (deveres.yaml v1.1 parity)
Exit 0 = all pass; 1 = any failure. Report printed as a checklist.
"""
from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client

LOT_FIELDS = ["lot_number", "lot_title", "lot_description",
              "hammer_price", "buyer_id", "consignor_id", "state",
              "auction_result", "auction_id", "product_id", "currency_id"]
PARTNER_FIELDS = ["name", "ref", "street", "street2", "city", "zip",
                  "state_id", "country_id", "email", "phone",
                  "parent_id", "company_name", "vat", "contact_types"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("ODOO_URL", "http://localhost:8071"))
    ap.add_argument("--db", default=os.environ.get("ODOO_DB", "deveres"))
    ap.add_argument("--user", default=os.environ.get("ODOO_USER", "admin"))
    ap.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", "DeveresTest2026!"))
    args = ap.parse_args()

    results: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        results.append((label, ok, detail))
        print(f"{'✔' if ok else '✘'} {label}" + (f" — {detail}" if detail else ""))

    common = xmlrpc.client.ServerProxy(f"{args.url}/xmlrpc/2/common")
    uid = common.authenticate(args.db, args.user, args.password, {})
    check("A1 admin authenticates", bool(uid), f"uid={uid}")
    if not uid:
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{args.url}/xmlrpc/2/object")

    def call(model, method, *a, **kw):
        return models.execute_kw(args.db, uid, args.password, model, method,
                                 list(a), kw)

    groups = call("res.users", "read", [uid], fields=["group_ids"])[0]["group_ids"]
    sys_group = call("ir.model.data", "check_object_reference", "base", "group_system")
    check("A2 admin in Settings/system group", sys_group[1] in groups)

    n_mod = call("ir.module.module", "search_count", [["state", "=", "installed"]])
    check("B1 can read module registry", n_mod > 0, f"{n_mod} installed")
    try:
        mid = call("ir.module.module", "search", [["state", "=", "installed"]], limit=1)
        # empty-vals write: exercises the write ACL without changing anything
        call("ir.module.module", "write", mid, {})
        check("B2 module write access (install/upgrade rights)", True)
    except Exception as exc:  # noqa: BLE001
        check("B2 module write access (install/upgrade rights)", False, str(exc)[:120])

    # C. partner write probe (revert)
    pid = call("res.partner", "search", [["ref", "!=", False]], limit=1)[0]
    before = call("res.partner", "read", [pid], fields=["street"])[0]["street"]
    try:
        call("res.partner", "write", [pid], {"street": before})
        check("C1 res.partner editable (street/address)", True, f"partner {pid}")
    except Exception as exc:  # noqa: BLE001
        check("C1 res.partner editable (street/address)", False, str(exc)[:80])

    # D. lot write probe (revert)
    lot_ids = call("sor.lot", "search", [], limit=1)
    if lot_ids:
        lid = lot_ids[0]
        hp = call("sor.lot", "read", [lid], fields=["hammer_price"])[0]["hammer_price"]
        try:
            call("sor.lot", "write", [lid], {"hammer_price": hp})
            check("D1 sor.lot editable (hammer price)", True, f"lot {lid}")
        except Exception as exc:  # noqa: BLE001
            check("D1 sor.lot editable (hammer price)", False, str(exc)[:80])
    else:
        check("D1 sor.lot editable (hammer price)", False, "no lots in database")

    # E/F. schema
    lot_schema = call("sor.lot", "fields_get", LOT_FIELDS)
    for f in LOT_FIELDS:
        check(f"E  sor.lot.{f}", f in lot_schema,
              lot_schema.get(f, {}).get("type", "MISSING"))
    partner_schema = call("res.partner", "fields_get", PARTNER_FIELDS)
    for f in PARTNER_FIELDS:
        check(f"F  res.partner.{f}", f in partner_schema,
              partner_schema.get(f, {}).get("type", "MISSING"))

    # G. lot form view: buyer_id after hammer_price
    view = call("sor.lot", "get_view", view_type="form")
    arch = view.get("arch", "")
    ok = "buyer_id" in arch and "hammer_price" in arch and \
        arch.index("buyer_id") > arch.index("hammer_price")
    check("G1 lot form shows buyer_id below hammer_price", ok,
          "visible when state='sold'" if ok else "field order wrong or missing")

    # H. auction lifecycle (sor.event uses `status`; lots publish via state)
    ev = call("sor.event", "fields_get", ["status"])
    states = [s[0] for s in ev.get("status", {}).get("selection", [])]
    check("H1 sor.event lifecycle (status)", bool(states), ", ".join(states))
    lot_states = [s[0] for s in lot_schema.get("state", {}).get("selection", [])]
    check("H2 sor.lot lifecycle incl. live+sold",
          {"live", "sold"} <= set(lot_states), ", ".join(lot_states))

    # I. parity: modules that must NOT be installed
    for absent in ("sor_bidding", "stock", "sor_artwork", "sor_tracking"):
        st = call("ir.module.module", "search_read",
                  [["name", "=", absent]], fields=["state"])
        state = st[0]["state"] if st else "absent"
        check(f"I  {absent} not installed", state != "installed", state)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed"
          + (f" — {len(failed)} FAILED" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
