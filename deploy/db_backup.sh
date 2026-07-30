#!/usr/bin/env bash
# db_backup.sh — production DB safety for Murder Bot / Easybot.
# pg_dumps the murderbot Postgres to a timestamped gzip, keeps the last N, prunes older.
# Run from cron/systemd-timer on the VM, or as a compose sidecar. Local-safe too.
#
# Usage:
#   ./deploy/db_backup.sh              # dump local db 'murderbot'
#   DB_DSN="host=postgres ..." ./deploy/db_backup.sh   # dump a container/remote db
#   BACKUP_DIR=/var/backups/murderbot KEEP=14 ./deploy/db_backup.sh
set -euo pipefail

DB_NAME="${POSTGRES_DB:-murderbot}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/.murderbot/backups}"
KEEP="${KEEP:-14}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/murderbot_${TS}.sql.gz"

mkdir -p "$BACKUP_DIR"

# On the VM the DB lives in the 'postgres' compose service — dump via that container so
# pg_dump ALWAYS matches the server version (set COMPOSE_FILE to enable this mode).
if [ -n "${COMPOSE_FILE:-}" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        pg_dump -U "${POSTGRES_USER:-murderbot}" "$DB_NAME" | gzip > "$OUT"
elif [ -n "${DB_DSN:-}" ]; then
    pg_dump "$DB_DSN" | gzip > "$OUT"
elif [ -n "${POSTGRES_USER:-}" ] && [ -n "${POSTGRES_HOST:-}" ]; then
    PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" "$DB_NAME" | gzip > "$OUT"
else
    pg_dump "$DB_NAME" | gzip > "$OUT"
fi

size="$(du -h "$OUT" | cut -f1)"
echo "[backup] wrote $OUT ($size)"

# rotate: keep the newest $KEEP, delete the rest
ls -1t "${BACKUP_DIR}"/murderbot_*.sql.gz 2>/dev/null | tail -n +"$((KEEP+1))" | while read -r old; do
    rm -f "$old" && echo "[backup] pruned $(basename "$old")"
done

echo "[backup] $(ls -1 "${BACKUP_DIR}"/murderbot_*.sql.gz 2>/dev/null | wc -l | tr -d ' ') backups retained in $BACKUP_DIR"
