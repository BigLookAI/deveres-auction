#!/usr/bin/env python3
"""
deVeres — verify every important res.partner field is editable (6-Jul step 3).

For each required contact field this checks four things:
  1. exists     — the field is on the res.partner model (fields_get)
  2. writable   — a live ORM/API write round-trips (write + read-back) on a
                  disposable test partner, via XML-RPC as the ADMIN user
  3. demo-write — the same write succeeds as the PUBLIC DEMO user (the account
                  reviewers use on the shared link)
  4. in UI form — the field appears in the res.partner form view and is not
                  hard readonly there (get_view arch scan)

Root cause this guards against (found 6-Jul): Odoo 19 gives base.group_user
READ-ONLY access to res.partner — a demo login without Contact Creation
(base.group_partner_manager) sees an uneditable contact form. --fix-perms
grants that group to the demo user first.

Env: ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD (admin), plus
     DEMO_USER / DEMO_PASSWORD for the demo-account check (defaults below).
Usage: python3 scripts/verify_contact_fields.py [--fix-perms] [--report PATH]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import xmlrpc.client
from datetime import datetime, timezone
from pathlib import Path

URL = os.environ.get("ODOO_URL", "http://localhost:8071")
DB = os.environ.get("ODOO_DB", "deveres_demo")
ADMIN = os.environ.get("ODOO_USERNAME", "admin")
ADMIN_PW = os.environ.get("ODOO_PASSWORD", "admin")
DEMO = os.environ.get("DEMO_USER", "demo@deveres.ie")
DEMO_PW = os.environ.get("DEMO_PASSWORD", "DemoView2026!")

# field → (label, test value builder). Relational values are resolved live.
CHECK_FIELDS = [
    ("name",        "Name",           "Verify Fieldcheck"),
    ("email",       "Email",          "verify.fieldcheck@example.test"),
    ("phone",       "Phone",          "+353871234567"),
    ("mobile",      "Mobile",         "+353861234567"),        # absent in Odoo 19
    ("street",      "Street",         "10 Checklist Road"),
    ("street2",     "Street2",        "Unit V"),
    ("city",        "City / Town",    "Bray"),
    ("state_id",    "County / State", "__state__"),
    ("country_id",  "Country",        "__country__"),
    ("zip",         "Zip / Eircode",  "A98X999"),
    ("comment",     "Notes",          "Editability verification note."),
    ("category_id", "Tags",           "__tag__"),
]


class Rpc:
    def __init__(self, user: str, pwd: str):
        common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
        self.uid = common.authenticate(DB, user, pwd, {})
        self.pwd = pwd
        self.models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

    def x(self, model, method, *args, **kw):
        return self.models.execute_kw(DB, self.uid, self.pwd, model, method,
                                      list(args), kw)


def resolve_value(rpc: Rpc, field: str, template):
    if template == "__state__":
        ids = rpc.x("res.country.state", "search",
                    [["name", "=", "Wicklow"], ["country_id.code", "=", "IE"]], limit=1)
        return ids[0] if ids else None
    if template == "__country__":
        ids = rpc.x("res.country", "search", [["code", "=", "IE"]], limit=1)
        return ids[0] if ids else None
    if template == "__tag__":
        ids = rpc.x("res.partner.category", "search", [["name", "=", "Verified Demo"]], limit=1)
        tag = ids[0] if ids else rpc.x("res.partner.category", "create",
                                       {"name": "Verified Demo"})
        return [(6, 0, [tag])]
    return template


def norm(field: str, value):
    """Normalise a read-back value for comparison with what was written."""
    if isinstance(value, (list, tuple)):
        if field == "category_id":
            return sorted(value if value and isinstance(value[0], int)
                          else [v[0] if isinstance(v, (list, tuple)) else v for v in value])
        return value[0] if len(value) == 2 and isinstance(value[0], int) else value
    if field == "comment" and isinstance(value, str):
        return re.sub(r"<[^>]+>", "", value).strip()   # html field wraps in <p>
    return value


def write_roundtrip(rpc: Rpc, pid: int, field: str, value) -> tuple[bool, str]:
    try:
        rpc.x("res.partner", "write", [pid], {field: value})
        got = norm(field, rpc.x("res.partner", "read", [pid], fields=[field])[0][field])
        want = value
        if field == "category_id":
            want = sorted(value[0][2])
        elif field == "comment":
            pass  # normalised above
        ok = (got == want) or (field == "comment" and str(want) in str(got))
        return ok, "" if ok else f"wrote {want!r}, read back {got!r}"
    except xmlrpc.client.Fault as f:
        return False, f.faultString.strip().splitlines()[-1][:140]
    except Exception as exc:                              # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def view_status(admin: Rpc) -> dict[str, str]:
    """Is each field present (and not hard-readonly) in the partner form view?"""
    try:
        arch = admin.x("res.partner", "get_view", view_type="form")["arch"]
    except Exception:                                     # noqa: BLE001
        try:
            arch = admin.x("res.partner", "fields_view_get", view_type="form")["arch"]
        except Exception as exc:                          # noqa: BLE001
            return {f: f"view fetch failed: {exc}" for f, _, _ in CHECK_FIELDS}
    out = {}
    for field, _, _ in CHECK_FIELDS:
        m = re.search(rf'<field[^>]*name="{field}"[^>]*/?>', arch)
        if not m:
            out[field] = "not in form view"
        elif re.search(r'readonly="(?:1|True|true)"', m.group(0)):
            out[field] = "in view but readonly"
        else:
            out[field] = "visible + editable"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix-perms", action="store_true",
                    help="grant base.group_partner_manager to the demo user first")
    ap.add_argument("--report", default="output/field-editability-report.md")
    args = ap.parse_args()

    admin = Rpc(ADMIN, ADMIN_PW)
    if not admin.uid:
        sys.exit(f"admin auth failed on {DB} at {URL}")

    perm_note = ""
    if args.fix_perms:
        demo_uid = admin.x("res.users", "search", [["login", "=", DEMO]], limit=1)
        grp = admin.x("ir.model.data", "check_object_reference",
                      "base", "group_partner_manager")[1]
        if demo_uid:
            admin.x("res.users", "write", demo_uid, {"group_ids": [(4, grp)]})
            perm_note = (f"Granted Contact Creation (base.group_partner_manager) to "
                         f"{DEMO} — required because Odoo 19 gives plain internal "
                         f"users READ-ONLY access to contacts.")
            print(perm_note)

    demo = Rpc(DEMO, DEMO_PW)
    fields_meta = admin.x("res.partner", "fields_get",
                          [f for f, _, _ in CHECK_FIELDS],
                          attributes=["string", "readonly", "type"])
    views = view_status(admin)

    pid = admin.x("res.partner", "create",
                  {"name": "TEST Field Verification (disposable)"})
    rows, all_ok = [], True
    for field, label, template in CHECK_FIELDS:
        meta = fields_meta.get(field)
        if not meta:
            rows.append((label, field, "❌ absent", "—", "—", "—",
                         "field does not exist on res.partner (Odoo 19 dropped "
                         "res.partner.mobile — importer maps mobile→phone/comment)"
                         if field == "mobile" else "field not on model"))
            if field != "mobile":
                all_ok = False
            continue
        value = resolve_value(admin, field, template)
        if value is None:
            rows.append((label, field, "✅", "❌", "❌", views.get(field, "?"),
                         "test value could not be resolved"))
            all_ok = False
            continue
        ok_admin, err_a = write_roundtrip(admin, pid, field, value)
        ok_demo, err_d = write_roundtrip(demo, pid, field, value) if demo.uid \
            else (False, "demo auth failed")
        rows.append((label, field, "✅",
                     "✅" if ok_admin else f"❌ {err_a}",
                     "✅" if ok_demo else f"❌ {err_d}",
                     views.get(field, "?"), meta.get("string", "")))
        all_ok = all_ok and ok_admin and ok_demo
    admin.x("res.partner", "unlink", [pid])

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Contact Field Editability Checklist",
        "",
        f"- **When:** {ts}   ·   **Target:** {URL} db `{DB}`",
        f"- **Admin account:** {ADMIN} · **Demo account:** {DEMO}",
        f"- **Overall:** {'✅ every required field verified editable' if all_ok else '⚠ see failures below'}",
        "",
        *([f"- **Permission fix applied:** {perm_note}", ""] if perm_note else []),
        "| Field | Model field | Exists | ORM/API write (admin) | ORM/API write (demo user) | Form view | Note |",
        "|---|---|---|---|---|---|---|",
        *(f"| {r[0]} | `{r[1]}` | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} |"
          for r in rows),
        "",
        "Write test = live XML-RPC `write` + read-back comparison on a disposable",
        "test partner (deleted afterwards). 'Form view' = presence in the",
        "res.partner form arch without a hard readonly flag.",
        "",
    ]
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"report written: {report}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
