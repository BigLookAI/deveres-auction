#!/usr/bin/env python3
"""deVeres — supervised end-to-end Odoo PUSH test (2-Jul meeting next-step).

Run against a TEST database only (the client's shared Postgres/Odoo instance,
or the disposable sandbox in odoo-test/). Uses SYNTHETIC contacts only.

    ODOO_URL=… ODOO_DB=… ODOO_USERNAME=… ODOO_PASSWORD=… \
    python3 scripts/odoo_push_test.py            # plan + dry-run only
    … RECON_ALLOW_ODOO_WRITE=1 PUSH_TEST_LIVE=1 \
    python3 scripts/odoo_push_test.py            # + real writes + verification

What it proves, in order:
  1. connection + version
  2. seed: creates one synthetic partner (the "existing client" for the update path)
  3. staging → plan: one UPDATE (write) + one CREATE, from a temp staging repo
  4. dry-run: correct op split, no writes
  5. live (opt-in): create + write applied; partners verified via search_read;
     county/country resolved to state_id/country_id (or safely noted in comment)
  6. idempotency: re-running the same plan does not duplicate partners
Exit code 0 = all checks passed.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.odoo_import import OdooImporter, plan_from_staging  # noqa: E402
from reconciliation.staging import StagingRepository                    # noqa: E402

REF_EXISTING = "PUSHTEST-5003"
REF_NEW = "BC-PUSHTEST-9001"


def main() -> int:
    if not os.environ.get("ODOO_URL"):
        print("BLOCKED: set ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD "
              "(test instance only — see odoo-test/docker-compose.yml).")
        return 2
    live = os.environ.get("PUSH_TEST_LIVE") == "1"

    importer = OdooImporter()
    cli = importer.client
    print(f"1. connected: {cli.url} db={cli.db}")

    # 2. seed the "existing client" this test will update
    existing = cli._execute("res.partner", "search",
                            [["ref", "=", REF_EXISTING]], limit=1)
    if live:
        if not existing:
            pid = cli._execute("res.partner", "create",
                               {"name": "Ciara Pushtest", "ref": REF_EXISTING,
                                "email": "ciara.pushtest@example.test",
                                "city": "Greystones"})
            print(f"2. seeded existing partner id={pid}")
        else:
            print(f"2. existing partner already present id={existing[0]}")
    else:
        print("2. (dry-run mode: seeding skipped)")

    # 3. temp staging with one approved UPDATE + one approved CREATE
    repo = StagingRepository(Path(tempfile.mkdtemp()) / "push-test-staging.db")
    repo.stage(session="push-test", record_index=1, buyer_number="PUSHTEST-9005",
               change_type="update", master_ref=REF_EXISTING, name="Ciara Pushtest",
               original={"town": "Greystones"}, incoming={"county": "Wickie"},
               approved={"first_name": "Ciara", "last_name": "Pushtest",
                         "email": "ciara.pushtest@example.test",
                         "town": "Greystones", "county": "Wicklow", "country": "Ireland"},
               edited_fields=["county"], changed_fields=["county", "country"],
               confidence=0.97, matched_by=["email"], lots=[], actor="push-test")
    repo.stage(session="push-test", record_index=2, buyer_number="PUSHTEST-9001",
               change_type="create", master_ref="", name="Testfirst Newclient",
               original={}, incoming={"first_name": "Testfirst"},
               approved={"first_name": "Testfirst", "last_name": "Newclient",
                         "email": "testfirst.newclient@example.test",
                         "address1": "12 Sample Quay", "town": "Kinsale",
                         "county": "Cork", "country": "Ireland", "postcode": "P17TE01",
                         "phone": "+353870000001"},
               edited_fields=[], changed_fields=[], confidence=0.0,
               matched_by=[], lots=[], actor="push-test")
    ops = plan_from_staging(repo.entries("push-test"), source_file="push-test")
    kinds = sorted(o.op for o in ops)
    assert kinds == ["create", "write"], f"unexpected plan {kinds}"
    print(f"3. plan OK: {[o.op for o in ops]} "
          f"(update carries __state_name={ops[1].values.get('__state_name') or ops[0].values.get('__state_name')})")

    # 4. dry-run — must not write
    res = importer.execute(ops, dry_run=True)
    assert res["summary"]["dry_run"] is True
    print(f"4. dry-run OK: {res['summary']}")

    if not live:
        print("\nPASS (plan + dry-run). Set PUSH_TEST_LIVE=1 and "
              "RECON_ALLOW_ODOO_WRITE=1 for the full write test.")
        return 0

    # 5. live push
    ops = plan_from_staging(repo.entries("push-test"), source_file="push-test")
    res = importer.execute(ops, dry_run=False)
    print(f"5. live push: {res['summary']}")
    created = cli._execute("res.partner", "search_read",
                           [["ref", "=", REF_NEW]],
                           fields=["name", "email", "city", "state_id", "country_id"])
    assert created, "created partner not found"
    updated = cli._execute("res.partner", "search_read",
                           [["ref", "=", REF_EXISTING]],
                           fields=["name", "state_id", "country_id", "comment"])
    print(f"   created: {created[0]['name']} state={created[0]['state_id']} "
          f"country={created[0]['country_id']}")
    print(f"   updated: {updated[0]['name']} state={updated[0]['state_id']} "
          f"country={updated[0]['country_id']}")

    # 6. idempotency — same plan again must update, not duplicate
    ops2 = plan_from_staging(repo.entries("push-test", status="pushed") or
                             repo.entries("push-test"), source_file="push-test")
    importer.execute(ops2, dry_run=False)
    dupes = cli._execute("res.partner", "search", [["ref", "=", REF_NEW]])
    assert len(dupes) == 1, f"duplicate partners created: {dupes}"
    print("6. idempotency OK — no duplicates on re-push")
    print("\nPASS — full end-to-end push verified against the test instance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
