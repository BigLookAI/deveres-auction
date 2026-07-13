#!/usr/bin/env bash
# Sync sor_* addons from a local BL-Odoo-System-of-Record checkout into this
# sandbox's addons mount, DRIVEN BY AN ASSEMBLY YAML: only the modules named
# in `install:` + `expect_auto:` are copied. This mirrors how the client
# deployment ships a compiled assembly — auto_install modules that are not
# part of the assembly (e.g. sor_bidding) must not be present on the addons
# path at all, otherwise Odoo pulls them in on the next registry update.
#
#   ./sync_addons.sh assemblies/deveres_april.yaml [path-to-SOR-repo]
set -euo pipefail

ASSEMBLY=${1:?usage: sync_addons.sh <assembly.yaml> [sor-repo-path]}
ASSEMBLY="$(cd "$(dirname "$ASSEMBLY")" && pwd)/$(basename "$ASSEMBLY")"
SOR_REPO=${2:-"$HOME/Documents/Cimelium/BL-Odoo-System-of-Record"}
cd "$(dirname "$0")"
[ -d "$SOR_REPO/addons" ] || { echo "No addons/ in $SOR_REPO"; exit 1; }

MODULES=$(python3 - "$ASSEMBLY" <<'PY'
import sys, re
mods, section = [], None
for raw in open(sys.argv[1], encoding="utf-8"):
    line = raw.split("#", 1)[0].rstrip()
    if not line.strip():
        continue
    if not line.startswith(" ") and line.endswith(":"):
        section = line[:-1].strip()
    elif line.strip().startswith("- ") and section in ("install", "expect_auto"):
        mods.append(line.strip()[2:].strip())
print("\n".join(mods))
PY
)
[ -n "$MODULES" ] || { echo "No modules parsed from $ASSEMBLY"; exit 1; }

echo "→ Removing existing sor_* modules from ./addons"
find ./addons -maxdepth 1 -type d -name 'sor_*' -exec rm -rf {} +

echo "→ Copying assembly modules from $SOR_REPO ($(git -C "$SOR_REPO" rev-parse --short HEAD))"
for m in $MODULES; do
  [ -d "$SOR_REPO/addons/$m" ] || { echo "  ✗ $m missing in SOR repo"; exit 1; }
  rsync -a --exclude '__pycache__' "$SOR_REPO/addons/$m/" "./addons/$m/"
  echo "  ✓ $m"
done

{
  echo "# Provenance"
  echo ""
  echo "Modules synced from BL-Odoo-System-of-Record @ $(git -C "$SOR_REPO" rev-parse HEAD)"
  echo "per assembly $(basename "$ASSEMBLY") on $(date -u +%Y-%m-%dT%H:%M:%SZ) by sync_addons.sh."
  echo "Only assembly modules are present BY DESIGN (auto_install containment)."
} > ./addons/README.md

echo "✓ $(echo "$MODULES" | wc -l | tr -d ' ') modules synced"
