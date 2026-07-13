#!/usr/bin/env python3
"""
deVeres — reset the DEMO Odoo contacts + reconciliation session to the
pristine, unreconciled state, so the standard test run (sample export →
review → approve → push → verify) can be repeated identically.

What it does (demo database only — refuses unless ODOO_DB starts 'deveres_demo'):
  1. deletes partners created by pushes (ref BC-…) — they are not part of the
     seed, so the sample export's NEW client surfaces again,
  2. re-runs the synthetic seeder (upsert by ref → every fixture/generated
     partner back to canonical values; empty fixture fields are cleared),
  3. county correction pass: state_id is set/CLEARED exactly per the fixture
     (the seeder only ever sets it, so a pushed county would otherwise stick),
  4. re-applies the SOR Contact Type tagging (migrate_contact_types logic).

The reconciliation app's session/staging files are archived by the shell
wrapper around this script (they live outside Odoo).

Env: ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD.
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import xmlrpc.client
from pathlib import Path

URL = os.environ.get("ODOO_URL", "http://localhost:8071")
DB = os.environ.get("ODOO_DB", "deveres_demo")
USER = os.environ.get("ODOO_USERNAME", "admin")
PWD = os.environ.get("ODOO_PASSWORD", "admin")

BASE = Path(__file__).resolve().parent.parent
FIXTURE = BASE / "tests" / "fixtures" / "master_test_clients.csv"

if not DB.startswith("deveres_demo"):
    sys.exit(f"refusing: ODOO_DB={DB!r} is not the demo database")

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PWD, {})
if not uid:
    sys.exit("Odoo auth failed")
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")


def x(model, method, *args, **kw):
    return models.execute_kw(DB, uid, PWD, model, method, list(args), kw)


# 1. remove push-created partners (BC-… refs are never seeded)
bc = x("res.partner", "search", [["ref", "=like", "BC-%"]])
if bc:
    names = [p["name"] for p in x("res.partner", "read", bc, fields=["name"])]
    x("res.partner", "unlink", bc)
    print(f"deleted {len(bc)} push-created partner(s): {', '.join(names)}")
else:
    print("no push-created (BC-…) partners to delete")

# 2. reseed — upsert by ref restores every seeded partner's canonical values
print("reseeding synthetic contacts…")
r = subprocess.run([sys.executable, str(BASE / "scripts" / "seed_demo_odoo.py")],
                   capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
if r.returncode:
    sys.exit("seeder failed")

# 3. county correction: state_id exactly per fixture (clear when empty)
ie = x("res.country", "search", [["code", "=", "IE"]], limit=1)[0]
fixed = cleared = 0
with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
    for row in csv.DictReader(f):
        pid = x("res.partner", "search", [["ref", "=", row["clientRef"]]], limit=1)
        if not pid:
            continue
        county = (row["countyState"] or "").strip()
        want = None
        if county:
            ids = x("res.country.state", "search",
                    [["name", "=ilike", county], ["country_id", "=", ie]], limit=1)
            want = ids[0] if ids else None
        cur = x("res.partner", "read", pid, fields=["state_id"])[0]["state_id"]
        cur_id = cur[0] if cur else None
        if cur_id != want:
            x("res.partner", "write", pid, {"state_id": want or False})
            fixed += bool(want)
            cleared += not want
print(f"county pass: {fixed} set, {cleared} cleared to match the fixture")

# 4. re-apply SOR Contact Type tagging (idempotent)
r = subprocess.run([sys.executable, str(BASE / "scripts" / "migrate_contact_types.py"),
                    "--report", "output/contact-migration-report.md"],
                   capture_output=True, text=True)
tail = [l for l in r.stdout.splitlines() if "SOR Contact Type" in l]
print(tail[0] if tail else "SOR tagging rerun")

# summary of the records the demo revolves around
for ref in ("5003", "5010", "5011", "5012"):
    pid = x("res.partner", "search", [["ref", "=", ref]], limit=1)
    if pid:
        p = x("res.partner", "read", pid,
              fields=["name", "street", "city", "state_id", "zip", "email", "phone"])[0]
        print(f"  {ref} {p['name']}: street={p['street'] or '—'} city={p['city'] or '—'} "
              f"county={p['state_id'][1] if p['state_id'] else '—'} zip={p['zip'] or '—'}")
print("Odoo demo contacts restored to the pristine seeded state.")
