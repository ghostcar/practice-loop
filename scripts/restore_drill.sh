#!/bin/bash
# Restore drill (RUNBOOK.md §5): restore the newest production backup into a
# throwaway database, verify schema/row counts, then drop it.
#
# Usage:
#   scripts/restore_drill.sh                      # newest backup in BACKUP_DIR
#   BACKUP_FILE=/opt/backups/tracker_20260903_0300.sql.gz scripts/restore_drill.sh
#
# Env:
#   BACKUP_DIR      where backups live (default /opt/backups)
#   DRILL_DB        throwaway DB name (default tracker_restore_drill)
#   COMPOSE_DIR     project dir with docker-compose.yml (default: script's repo root)
#   KEEP_DRILL_DB   set to 1 to keep the drill DB for manual inspection (default: drop)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/backups}"
BACKUP_FILE="${BACKUP_FILE:-}"
DRILL_DB="${DRILL_DB:-tracker_restore_drill}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
KEEP_DRILL_DB="${KEEP_DRILL_DB:-0}"
DC="docker compose -f $COMPOSE_DIR/docker-compose.yml"

if [ -z "$BACKUP_FILE" ]; then
  BACKUP_FILE=$(ls -t "$BACKUP_DIR"/tracker_*.sql.gz 2>/dev/null | head -n 1 || true)
fi
[ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ] || { echo "no backup file found in $BACKUP_DIR"; exit 1; }
echo "[$(date -Is)] drill source: $BACKUP_FILE"

# Clean any leftover drill DB, then restore.
$DC exec -T db psql -U tracker -d postgres -c "DROP DATABASE IF EXISTS \"$DRILL_DB\";" >/dev/null
echo "[$(date -Is)] restoring into $DRILL_DB ..."
$DC exec -T db psql -U tracker -d postgres -c "CREATE DATABASE \"$DRILL_DB\";" >/dev/null
if gunzip -c "$BACKUP_FILE" | $DC exec -T db psql -U tracker -d "$DRILL_DB" -v ON_ERROR_STOP=1 -q; then
  RESTORE_OK=1
else
  RESTORE_OK=0
fi

if [ "$RESTORE_OK" -eq 1 ]; then
  echo "[$(date -Is)] verification:"
  $DC exec -T db psql -U tracker -d "$DRILL_DB" -t -A -c "
    SELECT 'tables=' || count(*) FROM information_schema.tables WHERE table_schema='public';"
  $DC exec -T db psql -U tracker -d "$DRILL_DB" -t -A -c "SELECT 'users=' || count(*) FROM users;"
  $DC exec -T db psql -U tracker -d "$DRILL_DB" -t -A -c "SELECT 'alembic=' || version_num FROM alembic_version;"
  echo "DRILL_OK ($DRILL_DB restored from $(basename "$BACKUP_FILE"))"
else
  echo "DRILL_FAILED: psql exited non-zero ($DRILL_DB may be partially restored)"
fi

if [ "$KEEP_DRILL_DB" != "1" ]; then
  $DC exec -T db psql -U tracker -d postgres -c "DROP DATABASE IF EXISTS \"$DRILL_DB\";" >/dev/null
  echo "[$(date -Is)] drill DB dropped"
fi
[ "$RESTORE_OK" -eq 1 ]
