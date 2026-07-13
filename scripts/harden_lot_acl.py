#!/usr/bin/env python3
"""
deVeres — production ACL hardening for auction lots (technical-debt item).

The SOR modules grant every internal user full CRUD on sor.lot/sor.bid. Fine
for a synthetic demo; wrong for production. This script:

  1. creates an "Auction / Manager" group (idempotent, by name),
  2. replaces the sor.lot + sor.bid write/create/unlink ACLs so plain internal
     users are READ-ONLY and only Auction Managers (and the integration user)
     can write,
  3. adds the named users to the group.

NOT run automatically anywhere — production only, run deliberately:
    python3 scripts/harden_lot_acl.py --apply user1@host user2@host
Without --apply it reports what it would change (dry-run).

Env: ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD (admin).
"""
from __future__ import annotations

import argparse
import os
import sys
import xmlrpc.client

URL = os.environ.get("ODOO_URL", "http://localhost:8071")
DB = os.environ.get("ODOO_DB", "")
USER = os.environ.get("ODOO_USERNAME", "admin")
PWD = os.environ.get("ODOO_PASSWORD", "")

GROUP_NAME = "Auction / Manager"
MODELS = ("sor.lot", "sor.bid")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("logins", nargs="*", help="user logins to add to the manager group")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry-run)")
    args = ap.parse_args()

    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, PWD, {})
    if not uid:
        sys.exit(f"Odoo auth failed ({USER} on {DB})")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

    def x(model, method, *a, **kw):
        return models.execute_kw(DB, uid, PWD, model, method, list(a), kw)

    print(f"target: {URL} db={DB} · mode: {'APPLY' if args.apply else 'dry-run'}")

    grp = x("res.groups", "search", [["name", "=", GROUP_NAME]], limit=1)
    if grp:
        grp_id = grp[0]
        print(f"group exists: {GROUP_NAME} (id {grp_id})")
    elif args.apply:
        grp_id = x("res.groups", "create", {"name": GROUP_NAME})
        print(f"group created: {GROUP_NAME} (id {grp_id})")
    else:
        grp_id = None
        print(f"would create group: {GROUP_NAME}")

    for model in MODELS:
        acls = x("ir.model.access", "search_read",
                 [["model_id.model", "=", model]],
                 fields=["name", "group_id", "perm_read", "perm_write",
                         "perm_create", "perm_unlink"])
        for a in acls:
            if a["perm_write"] or a["perm_create"] or a["perm_unlink"]:
                print(f"  {model}: ACL '{a['name']}' "
                      f"({(a['group_id'] or [None, 'GLOBAL'])[1]}) → read-only")
                if args.apply:
                    x("ir.model.access", "write", [a["id"]],
                      {"perm_write": False, "perm_create": False, "perm_unlink": False})
        print(f"  {model}: manager ACL (write/create/unlink for {GROUP_NAME})")
        if args.apply and grp_id:
            model_id = x("ir.model", "search", [["model", "=", model]], limit=1)[0]
            if not x("ir.model.access", "search",
                     [["model_id", "=", model_id], ["group_id", "=", grp_id]], limit=1):
                x("ir.model.access", "create", {
                    "name": f"{model.replace('.', '_')}_auction_manager",
                    "model_id": model_id, "group_id": grp_id,
                    "perm_read": True, "perm_write": True,
                    "perm_create": True, "perm_unlink": False})

    for login in args.logins:
        u = x("res.users", "search", [["login", "=", login]], limit=1)
        if not u:
            print(f"  user not found: {login}")
            continue
        print(f"  add to {GROUP_NAME}: {login}")
        if args.apply and grp_id:
            x("res.users", "write", u, {"group_ids": [(4, grp_id)]})

    print("done." if args.apply else "dry-run complete — re-run with --apply to write.")


if __name__ == "__main__":
    main()
