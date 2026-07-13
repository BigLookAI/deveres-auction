#!/usr/bin/env bash
# deVeres — full production-launch simulation (13-Jul-2026 plan, Phase 22).
#
# Rebuilds the entire environment from nothing and runs the complete
# reconciliation workflow against the REAL April database + Blue Cubes CSV:
#
#   1. addons  = latest SOR modules, exactly the deveres.yaml v1.1 assembly set
#   2. restore = April backup into a FRESH postgres+odoo (volumes destroyed)
#   3. upgrade + assembly install + Inventory removal
#   4. verify  = 38 admin/schema/parity checks
#   5. contacts: upload → approve → ONE push → refresh → re-upload → converged
#   6. lots:     reconcile → push (hammer+buyer+sold) → verify → idempotent
#
#   ./scripts/launch_simulation.sh ~/Downloads/odoo_deveres_april_test_*.zip
#
# Requires: docker (colima), python3 with fastapi/uvicorn/requests, the local
# recon app NOT running on :8013 (the script starts its own).
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_ZIP=${1:?usage: launch_simulation.sh /path/to/odoo_backup.zip}
CSV=${2:-"Design-April 2026.csv"}
PORT=${RECON_PORT:-8013}
AUTH="admin@deveres.ie:Admin2026!"
step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

step "1/6 addons — assembly-driven sync (deveres_april.yaml)"
./odoo-test/sync_addons.sh odoo-test/assemblies/deveres_april.yaml

step "2/6 clean restore — fresh volumes + April backup"
(cd odoo-test && docker compose down -v && ./restore.sh "$BACKUP_ZIP")

step "3/6 upgrade to latest module code + assembly install + drop Inventory"
UPG_LOG=$(docker exec deveres-odoo-test odoo -c /etc/odoo/odoo.conf -d deveres \
  -u sor_technical_menu,sor_contact_roles,sor_business_model,sor_events,sor_lotting,sor_auction_documents,sor_accounting,sor_buyer_invoice,sor_business_model_non_commercial,sor_events_auction,sor_commercial_auction_house,sor_lotting_contact_roles,sor_buyer_invoice_auction_house,sor_buyer_invoice_contact_roles \
  --stop-after-init --no-http 2>&1)
if printf '%s' "$UPG_LOG" | grep -qE "\b(ERROR|CRITICAL)\b"; then
  printf '%s\n' "$UPG_LOG" | grep -E "\b(ERROR|CRITICAL)\b" | head -5
  echo "module upgrade reported errors"; exit 1
fi
echo "module upgrade clean"
python3 scripts/install_assembly.py odoo-test/assemblies/deveres_april.yaml \
  --report output/module-install-report-launch.md >/dev/null
docker exec -i deveres-odoo-test odoo shell -c /etc/odoo/odoo.conf -d deveres --no-http <<'PY' 2>/dev/null | grep MARK || true
m = env['ir.module.module'].search([('name','=','stock')])
if m.state == 'installed':
    m.button_immediate_uninstall(); env.cr.commit()
print("MARK stock:", m.state)
PY
docker restart deveres-odoo-test >/dev/null && sleep 8

step "4/6 API key + 38 environment checks"
KEY=$(docker exec -i deveres-odoo-test odoo shell -c /etc/odoo/odoo.conf -d deveres --no-http 2>/dev/null <<'PY' | grep '^MARKKEY' | awk '{print $2}'
key = env['res.users.apikeys'].with_user(env['res.users'].browse(2))._generate('rpc', 'deveres-launch-sim', None)
env.cr.commit(); print("MARKKEY", key)
PY
)
[ -n "$KEY" ] || { echo "API key generation failed"; exit 1; }
python3 scripts/verify_environment.py

step "5/6 contacts — one-pass convergence on the real CSV"
kill "$(lsof -ti :$PORT)" 2>/dev/null || true; sleep 1
env ODOO_URL=http://localhost:8071 ODOO_DB=deveres ODOO_USERNAME=admin \
    ODOO_PASSWORD="$KEY" RECON_ALLOW_ODOO_WRITE=1 RECON_MASTER_SOURCE=odoo \
    RECON_LOTS_ENABLE_BUYER=1 RECON_LOTS_ENABLE_SOLD=1 \
    python3 -m uvicorn recon_app:app --port "$PORT" >/tmp/launch-sim-app.log 2>&1 &
APP=$!; trap 'kill $APP 2>/dev/null || true' EXIT; sleep 5
J() { curl -sf -u "$AUTH" "$@"; }
J -F "file=@$CSV" "http://localhost:$PORT/reconcile/upload" | python3 -c "
import json,sys; s=json.load(sys.stdin)['summary']
print('upload:', s); assert s['total'] > 0"
J -H 'Content-Type: application/json' -d '{"action":"UPDATE","status":"update"}' \
  "http://localhost:$PORT/reconcile/decide" >/dev/null
J -H 'Content-Type: application/json' -d '{"dry_run":false}' \
  "http://localhost:$PORT/reconcile/odoo-import" | python3 -c "
import json,sys; s=json.load(sys.stdin)['summary']
print('push:', s); assert s['error'] == 0 and s['verified'] == s['write'] + s['create']"
J -X POST "http://localhost:$PORT/reconcile/master/reload" >/dev/null
J -F "file=@$CSV" "http://localhost:$PORT/reconcile/upload" | python3 -c "
import json,sys; s=json.load(sys.stdin)['summary']
print('re-upload:', s)
assert s['update'] == 0 and s['new'] == 0, 'NOT converged in one pass'
print('CONVERGED IN ONE PASS ✓ (remaining manual reviews: %d)' % s['manual_review'])"

step "6/6 lots — hammer + buyer + sold, verified and idempotent"
J "http://localhost:$PORT/reconcile/auction/results" | python3 -c "
import json,sys; s=json.load(sys.stdin)['summary']
print('lots:', s); assert s['ready'] > 0 and s['conflict'] == 0"
J -H 'Content-Type: application/json' -d '{"dry_run":false}' \
  "http://localhost:$PORT/reconcile/auction/push" | python3 -c "
import json,sys; d=json.load(sys.stdin); s=d['summary']
print('lot push:', s); assert s['error'] == 0 and s['verified'] == s['written']"
J "http://localhost:$PORT/reconcile/auction/results" | python3 -c "
import json,sys; s=json.load(sys.stdin)['summary']
print('re-check:', s); assert s['ready'] == 0 and s['already_imported'] > 0
print('LOTS IDEMPOTENT ✓')"

printf '\n\033[1m✓ LAUNCH SIMULATION PASSED\033[0m — clean environment, real data, one-pass workflow.\n'
