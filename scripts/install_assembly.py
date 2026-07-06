#!/usr/bin/env python3
"""
deVeres — install SOR modules into a dockerised Odoo from an Assembly YAML.

Implements the 6-Jul-2026 meeting step 1: "install every module listed in the
Assembly YAML" against the demo Odoo sandbox, then verify the result and emit
a module-installation report.

The Assembly YAML shape follows the SOR ASSEMBLY grammar (assembly/version/
target/install) with one extension: target.container names the docker
container running Odoo, and expect_auto lists the bridge modules that must
auto-install once the explicit set is present.

Usage (run on the host that owns the containers, e.g. the DGX):
    python3 scripts/install_assembly.py odoo-test/assemblies/deveres_demo.yaml
        [--dry-run]        plan only, no install
        [--report PATH]    write the markdown report here
                           (default: output/module-install-report.md)

Install order is delegated to Odoo's own dependency resolver (a single
`odoo -i m1,m2,…` invocation) — the manifests carry the dependency graph, so
a topological pre-sort would only duplicate what Odoo already does.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:                                       # pragma: no cover
    yaml = None


def load_assembly(path: Path) -> dict:
    if yaml is not None:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        # PyYAML-free fallback: the assembly grammar subset used here is flat
        # enough to parse by hand (target: mapping + two string lists).
        doc, section = {}, None
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            if not line.startswith(" ") and line.endswith(":"):
                section = line[:-1].strip()
                doc[section] = {} if section == "target" else []
            elif not line.startswith(" ") and ":" in line:
                k, v = line.split(":", 1)
                doc[k.strip()] = v.strip().strip('"')
                section = None
            elif line.strip().startswith("- ") and isinstance(doc.get(section), list):
                doc[section].append(line.strip()[2:].strip())
            elif ":" in line and isinstance(doc.get(section), dict):
                k, v = line.strip().split(":", 1)
                doc[section][k.strip()] = v.strip().strip('"')
    for key in ("assembly", "target", "install"):
        if key not in doc:
            sys.exit(f"Assembly file missing required field: {key}")
    return doc


def sh(cmd: list[str], input_text: str | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def module_states(db_container: str, db: str, modules: list[str]) -> dict[str, str]:
    names = ",".join(f"'{m}'" for m in modules)
    rc, out = sh(["docker", "exec", db_container, "psql", "-U", "odoo", "-d", db,
                  "-tAc", f"SELECT name,state FROM ir_module_module WHERE name IN ({names})"])
    states = {}
    if rc == 0:
        for line in out.splitlines():
            if "|" in line:
                name, state = line.strip().split("|", 1)
                states[name] = state
    return states


def all_sor_states(db_container: str, db: str) -> dict[str, str]:
    rc, out = sh(["docker", "exec", db_container, "psql", "-U", "odoo", "-d", db, "-tAc",
                  "SELECT name,state FROM ir_module_module WHERE name LIKE 'sor_%' ORDER BY name"])
    return {l.split("|")[0]: l.split("|")[1] for l in out.splitlines() if "|" in l} if rc == 0 else {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("assembly")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db-container", default="deveres-odoo-test-db")
    ap.add_argument("--report", default="output/module-install-report.md")
    args = ap.parse_args()

    doc = load_assembly(Path(args.assembly))
    target = doc["target"]
    container, db = target.get("container", "deveres-odoo-test"), target["db"]
    install = list(doc["install"])
    expect_auto = list(doc.get("expect_auto") or [])

    print(f"assembly: {doc['assembly']} v{doc.get('version', '?')}")
    print(f"target:   container={container} db={db}")
    print(f"install:  {', '.join(install)}")

    before = all_sor_states(args.db_container, db)
    print(f"\nbefore: {sum(1 for s in before.values() if s == 'installed')} sor_* modules installed")

    if args.dry_run:
        print("\n--dry-run: stopping before install. Odoo will resolve the order itself.")
        return

    # One invocation; Odoo's resolver handles ordering + base deps
    # (contacts/product/stock/mail) + auto_install bridges.
    t0 = time.perf_counter()
    cmd = ["docker", "exec", container, "odoo", "-c", "/etc/odoo/odoo.conf",
           "-d", db, "-i", ",".join(install), "--stop-after-init", "--no-http"]
    print(f"\nrunning: {' '.join(cmd)}")
    rc, out = sh(cmd)
    dur = time.perf_counter() - t0

    errors = [l for l in out.splitlines() if re.search(r"\b(ERROR|CRITICAL)\b", l)]
    warn_dep = [l for l in out.splitlines()
                if "WARNING" in l and re.search(r"depend|unmet|missing|uninstallable", l, re.I)]

    # restart so the serving process reloads the registry with the new modules
    print("restarting the Odoo container to reload the registry…")
    sh(["docker", "restart", container])

    after = all_sor_states(args.db_container, db)
    inst = {m: s for m, s in after.items() if s == "installed"}
    missing = [m for m in install if after.get(m) != "installed"]
    missing_auto = [m for m in expect_auto if after.get(m) != "installed"]
    leftover = {m: s for m, s in after.items() if s in ("to install", "to upgrade", "to remove")}

    # base-stack modules the assembly pulled in
    base_now = module_states(args.db_container, db,
                             ["contacts", "product", "stock", "mail", "account"])

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ok = not missing and not leftover and rc == 0
    lines = [
        f"# Module Installation Report — assembly `{doc['assembly']}`",
        "",
        f"- **When:** {ts}",
        f"- **Target:** container `{container}`, database `{db}`",
        f"- **Assembly file:** `{args.assembly}`",
        f"- **Install duration:** {dur:.0f}s · odoo exit code {rc}",
        f"- **Result:** {'✅ SUCCESS' if ok else '❌ INCOMPLETE — see below'}",
        "",
        "## Explicit modules (from the Assembly `install:` list)",
        "",
        "| Module | Before | After |",
        "|---|---|---|",
        *(f"| {m} | {before.get(m, '—')} | {after.get(m, 'ABSENT')} |" for m in install),
        "",
        "## Auto-installed bridge modules",
        "",
        "| Module | Before | After |",
        "|---|---|---|",
        *(f"| {m} | {before.get(m, '—')} | {after.get(m, 'ABSENT')} |" for m in expect_auto),
        "",
        "## Base Odoo modules pulled in as dependencies",
        "",
        "| Module | State |",
        "|---|---|",
        *(f"| {m} | {s} |" for m, s in sorted(base_now.items())),
        "",
        f"## All sor_* modules now installed ({len(inst)})",
        "",
        ", ".join(sorted(inst)) or "(none)",
        "",
        "## Issues",
        "",
    ]
    if missing:
        lines.append(f"- ❌ NOT installed from the explicit list: {', '.join(missing)}")
    if missing_auto:
        lines.append(f"- ⚠ expected bridges that did not auto-install: {', '.join(missing_auto)}")
    if leftover:
        lines.append(f"- ⚠ modules left in a pending state: {json.dumps(leftover)}")
    if warn_dep:
        lines.append("- ⚠ dependency warnings from the install log:")
        lines += [f"  - `{l.strip()[:200]}`" for l in warn_dep[:20]]
    if errors:
        lines.append(f"- ❌ ERROR lines in the install log ({len(errors)} — first 20):")
        lines += [f"  - `{l.strip()[:200]}`" for l in errors[:20]]
    if not (missing or missing_auto or leftover or warn_dep or errors):
        lines.append("- none — clean install, no dependency warnings.")

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nreport written: {report}")
    print("\n".join(lines[:14]))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
