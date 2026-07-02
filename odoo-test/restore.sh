#!/usr/bin/env bash
# Restore the deVeres April-test Odoo backup into the local sandbox.
#
#   ./restore.sh /path/to/odoo_deveres_april_test_*.zip
#
# Idempotent: re-running drops and recreates the database. Steps:
#   1. extract the Odoo backup zip (dump.sql + filestore + manifest)
#   2. start postgres, drop/create the target db, restore the SQL dump
#   3. NEUTRALIZE the copy (real client data, local sandbox):
#        - disable every outgoing mail server and scheduled job
#        - re-point web.base.url, regenerate database.uuid (no IAP collisions)
#        - reset the admin password to a local-only value
#   4. install the sor_db_compat overlay (version-drift fields — see its manifest)
#   5. start Odoo, copy the filestore into the data volume
set -euo pipefail
cd "$(dirname "$0")"

BACKUP_ZIP=${1:?usage: restore.sh /path/to/odoo_backup.zip}
DB=deveres
ADMIN_PASSWORD=${DEVERES_TEST_ADMIN_PASSWORD:-DeveresTest2026!}
PSQL="docker exec -i deveres-odoo-test-db psql -U odoo -v ON_ERROR_STOP=1"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
echo "→ Extracting $(basename "$BACKUP_ZIP")"
unzip -q "$BACKUP_ZIP" -d "$WORK"
[ -f "$WORK/dump.sql" ] || { echo "No dump.sql in backup"; exit 1; }

echo "→ Starting postgres"
docker compose up -d --wait db

echo "→ Recreating database '$DB'"
docker compose stop odoo >/dev/null 2>&1 || true
$PSQL -d postgres -c "DROP DATABASE IF EXISTS $DB" >/dev/null
$PSQL -d postgres -c "CREATE DATABASE $DB OWNER odoo" >/dev/null

echo "→ Restoring SQL dump ($(du -h "$WORK/dump.sql" | cut -f1))"
$PSQL -q -d $DB < "$WORK/dump.sql" >/dev/null

echo "→ Neutralizing the copy (mail off, crons off, fresh uuid, local base url)"
$PSQL -d $DB <<'SQL' >/dev/null
UPDATE ir_mail_server SET active = false;
UPDATE ir_cron SET active = false;
UPDATE ir_config_parameter SET value = 'http://localhost:8071' WHERE key = 'web.base.url';
UPDATE ir_config_parameter SET value = md5(random()::text) WHERE key = 'database.uuid';
SQL

echo "→ Resetting admin password"
HASH=$(docker compose run --rm --no-deps -T odoo python3 -c \
  "from passlib.context import CryptContext; import sys; print(CryptContext(schemes=['pbkdf2_sha512']).hash(sys.argv[1]))" \
  "$ADMIN_PASSWORD" | tr -d '\r')
$PSQL -d $DB -c "UPDATE res_users SET password = '$HASH' WHERE login = 'admin'" >/dev/null

echo "→ Syncing schema (columns for code-defined stored fields missing in the dump)"
docker compose run --rm -T --entrypoint python3 odoo - <<'PYEOF' 2>&1 | grep -E "schema-added|schema sync" || true
import odoo
from odoo.modules.registry import Registry
odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf'])
reg = Registry('deveres')
with reg.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    todo = []
    for name in list(reg.models):
        model = env[name]
        if model._abstract or not model._auto:
            continue
        cr.execute("SELECT column_name FROM information_schema.columns "
                   "WHERE table_name=%s", (model._table,))
        existing = {r[0] for r in cr.fetchall()}
        missing = [f.name for f in model._fields.values()
                   if f.store and f.column_type and f.name not in existing]
        if missing:
            todo.append((name, missing))
            print("schema-added:", name, missing)
    if todo:
        reg.init_models(cr, [n for n, _ in todo], {'module': 'base'}, install=False)
    cr.commit()
print("schema sync complete:", len(todo), "model(s)")
PYEOF

echo "→ Starting Odoo + copying filestore"
docker compose up -d --wait odoo
if [ -d "$WORK/filestore" ]; then
  docker exec -u root deveres-odoo-test mkdir -p /var/lib/odoo/filestore
  docker cp "$WORK/filestore/." "deveres-odoo-test:/var/lib/odoo/filestore/$DB/"
  docker exec -u root deveres-odoo-test chown -R odoo:odoo /var/lib/odoo/filestore
  docker compose restart odoo >/dev/null
fi

echo "✓ Done — http://localhost:8071  (db: $DB, admin / $ADMIN_PASSWORD)"
