#!/usr/bin/env python3
"""
deVeres — seed the PUBLIC-DEMO Odoo sandbox with SYNTHETIC contacts only.

Purpose (3-Jul-2026): let anyone test the Odoo-integrated reconciliation
prototype on the public link without exposing a single real client record.

Loads two things into a fresh Odoo database:
  1. tests/fixtures/master_test_clients.csv — the 13 hand-crafted synthetic
     masters that the downloadable sample export (/reconcile/sample-csv) is
     designed to match against (typos, format noise, review cases).
  2. ~200 generated synthetic partners (deterministic RNG, fake names,
     @example.test emails, valid-looking Irish addresses) so the fetched
     master has believable volume.

Idempotent: partners are resolved by ref before create (re-running updates
instead of duplicating).

Env (same variables the app uses):
  ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD
"""
from __future__ import annotations

import csv
import os
import random
import sys
import xmlrpc.client
from pathlib import Path

URL = os.environ.get("ODOO_URL", "http://localhost:8071")
DB = os.environ.get("ODOO_DB", "deveres_demo")
USER = os.environ.get("ODOO_USERNAME", "admin")
PWD = os.environ.get("ODOO_PASSWORD", "admin")

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "master_test_clients.csv"

FIRST = ["Aoife", "Brian", "Ciara", "Declan", "Eimear", "Fergal", "Grainne", "Hugh",
         "Iseult", "Jack", "Katie", "Liam", "Maeve", "Niall", "Orla", "Padraig",
         "Roisin", "Sean", "Tara", "Una", "Vera", "William", "Sinead", "Cathal"]
LAST = ["Samples", "O'Tester", "Mockley", "Fakeman", "Demoson", "Placeholder",
        "Testerton", "Dummigan", "Specimen", "Exampleton", "Mocklin", "Fauxberg",
        "Stubbs", "Fixture", "Prototype", "Sandboxe"]
STREETS = ["Harbour View", "Main Street", "Abbey Road", "Castle Drive", "Mill Lane",
           "Church Road", "Bridge Street", "Ocean Avenue", "Green Park", "Oak Crescent"]
TOWNS = [("Howth", "Dublin", "D13"), ("Naas", "Kildare", "W91"), ("Bray", "Wicklow", "A98"),
         ("Cork", "Cork", "T12"), ("Galway", "Galway", "H91"), ("Sligo", "Sligo", "F91"),
         ("Kilkenny", "Kilkenny", "R95"), ("Limerick", "Limerick", "V94")]


def connect():
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, PWD, {})
    if not uid:
        sys.exit(f"Authentication failed for {USER} on {DB} at {URL}")
    return uid, xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")


def upsert(models, uid, vals: dict) -> tuple[int, bool]:
    ids = models.execute_kw(DB, uid, PWD, "res.partner", "search",
                            [[["ref", "=", vals["ref"]]]], {"limit": 1})
    if ids:
        models.execute_kw(DB, uid, PWD, "res.partner", "write", [ids, vals])
        return ids[0], False
    return models.execute_kw(DB, uid, PWD, "res.partner", "create", [vals]), True


def state_id(models, uid, cache: dict, name: str, country_ie: int) -> int | None:
    if name not in cache:
        ids = models.execute_kw(DB, uid, PWD, "res.country.state", "search",
                                [[["name", "=ilike", name], ["country_id", "=", country_ie]]],
                                {"limit": 1})
        cache[name] = ids[0] if ids else None
    return cache[name]


def main() -> None:
    uid, models = connect()
    ie = models.execute_kw(DB, uid, PWD, "res.country", "search",
                           [[["code", "=", "IE"]]], {"limit": 1})[0]
    states: dict = {}
    created = updated = 0

    # 1) the hand-crafted fixture masters (the sample export matches these)
    with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = f"{row['firstName']} {row['lastName']}".strip() or row["companyName"]
            vals = {"name": name, "ref": row["clientRef"],
                    "email": row["email"] or False,
                    "phone": row["telNo"] or row["mobile"] or False,
                    "street": row["address1"] or False,
                    "street2": ", ".join(x for x in (row["address2"], row["address3"]) if x) or False,
                    "city": row["townCity"] or False, "zip": row["postalCode"] or False,
                    "country_id": ie,
                    "comment": "SYNTHETIC demo contact — fixture master (no real data)."}
            sid = state_id(models, uid, states, row["countyState"], ie) if row["countyState"] else None
            if sid:
                vals["state_id"] = sid
            _, was_new = upsert(models, uid, vals)
            created += was_new
            updated += (not was_new)

    # 2) generated volume — deterministic so re-runs are stable
    rng = random.Random(20260703)
    for i in range(200):
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        town, county, ecode = rng.choice(TOWNS)
        ref = str(6000 + i)
        vals = {"name": f"{fn} {ln}", "ref": ref,
                "email": f"{fn.lower()}.{ln.lower().replace(chr(39), '')}.{ref}@example.test",
                "phone": f"+3538{rng.randint(5, 7)}{rng.randint(1000000, 9999999)}",
                "street": f"{rng.randint(1, 120)} {rng.choice(STREETS)}",
                "city": town, "zip": f"{ecode}{rng.choice('ABCDEFHKNPRTVWXY')}"
                                     f"{rng.randint(100, 999)}",
                "country_id": ie,
                "comment": "SYNTHETIC demo contact — generated (no real data)."}
        sid = state_id(models, uid, states, county, ie)
        if sid:
            vals["state_id"] = sid
        _, was_new = upsert(models, uid, vals)
        created += was_new
        updated += (not was_new)

    total = models.execute_kw(DB, uid, PWD, "res.partner", "search_count", [[]])
    print(f"seeded: {created} created, {updated} updated — {total} partners in {DB}")


if __name__ == "__main__":
    main()
