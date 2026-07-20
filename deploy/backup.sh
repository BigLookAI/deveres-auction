#!/usr/bin/env bash
# deVeres — nightly Odoo DB backup on the AWS host.
# Dumps the client DB (custom format, TOC-verified) and optionally ships it to
# S3. Run via cron:  30 2 * * * /opt/deveres/deploy/backup.sh
set -euo pipefail

DB=${ODOO_DB:-odoo_deveres}
CONTAINER=${DB_CONTAINER:-deveres-db}
PGUSER=${PGUSER:-odoo}
BACKUP_DIR=${BACKUP_DIR:-/opt/deveres/backups}
RETENTION_DAYS=${RETENTION_DAYS:-14}
S3_BUCKET=${S3_BUCKET:-}          # e.g. s3://deveres-backups ; empty = local only
TS=$(date +%Y%m%d_%H%M%S)
OUT="${BACKUP_DIR}/${DB}_${TS}.dump"

mkdir -p "$BACKUP_DIR"
echo "[$(date '+%F %T')] dumping ${DB} -> $(basename "$OUT")"
docker exec "$CONTAINER" pg_dump -U "$PGUSER" -Fc "$DB" > "$OUT"

# integrity: a valid custom-format dump lists its TOC
docker exec -i "$CONTAINER" pg_restore --list < "$OUT" >/dev/null
echo "[$(date '+%F %T')] OK — $(du -sh "$OUT" | cut -f1), TOC verified"

# EBS snapshot of the odoo filestore volume is the companion for attachments;
# the DB dump above does not include /var/lib/odoo. See AWS-DEPLOYMENT.md §7.

if [ -n "$S3_BUCKET" ]; then
  aws s3 cp "$OUT" "${S3_BUCKET}/$(basename "$OUT")" --only-show-errors
  echo "[$(date '+%F %T')] uploaded to ${S3_BUCKET}"
fi

find "$BACKUP_DIR" -name '*.dump' -mtime +"$RETENTION_DAYS" -delete
echo "[$(date '+%F %T')] pruned dumps older than ${RETENTION_DAYS}d"
