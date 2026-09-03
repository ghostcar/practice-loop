#!/bin/bash
# Automated production backup: PostgreSQL dump + uploads volume archive + off-site
# sync + retention. Designed for cron on the VPS (see RUNBOOK.md §5).
#
# Usage:
#   BACKUP_DIR=/opt/backups OFFSITE_DIR=/mnt/backup-remote scripts/backup_prod.sh
# Cron (daily 03:00 UTC, keep 14 days):
#   0 3 * * * BACKUP_DIR=/opt/backups scripts/backup_prod.sh >> /var/log/pl-backup.log 2>&1
#
# Env:
#   BACKUP_DIR       local backup dir (default /opt/backups)
#   RETENTION_DAYS   local/off-site retention (default 14)
#   OFFSITE_DIR      off-site target; when set, backups are rsync'd there (default: unset)
#   COMPOSE_DIR      project dir with docker-compose.yml (default: script's repo root)
#   NOTIFY_ON_ERROR  command template executed on failure, e.g.
#                    "curl -fsS -X POST -H 'Content-Type: text/plain' --data-binary @- %s"
#                    (placeholder %s is replaced by the message; default: unset)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
OFFSITE_DIR="${OFFSITE_DIR:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
STAMP="$(date +%Y%m%d_%H%M)"
NOTIFY_ON_ERROR="${NOTIFY_ON_ERROR:-}"

notify_error() {
  local msg="$1"
  echo "BACKUP_ERROR: $msg" >&2
  if [ -n "$NOTIFY_ON_ERROR" ]; then
    # shellcheck disable=SC2086  # template intentionally user-provided
    printf '%s' "$msg" | eval "$(printf "$NOTIFY_ON_ERROR" "'%s'")" >/dev/null 2>&1 || true
  fi
}
trap 'notify_error "backup failed at line $LINENO"' ERR

mkdir -p "$BACKUP_DIR"

echo "[$(date -Is)] pg_dump → $BACKUP_DIR/tracker_${STAMP}.sql.gz"
docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T db \
  pg_dump -U tracker -d tracker --no-owner \
  | gzip > "$BACKUP_DIR/tracker_${STAMP}.sql.gz"
[ -s "$BACKUP_DIR/tracker_${STAMP}.sql.gz" ] || { echo "pg_dump produced an empty file"; exit 1; }

echo "[$(date -Is)] uploads volume archive → $BACKUP_DIR/uploads_${STAMP}.tar.gz"
docker run --rm -v tracker_uploads:/src:ro -v "$BACKUP_DIR":/dst alpine \
  tar -czf "/dst/uploads_${STAMP}.tar.gz" -C /src .
[ -s "$BACKUP_DIR/uploads_${STAMP}.tar.gz" ] || { echo "uploads archive is empty"; exit 1; }

echo "[$(date -Is)] integrity check (gzip -t + dump header)"
gzip -t "$BACKUP_DIR/tracker_${STAMP}.sql.gz"
gzip -t "$BACKUP_DIR/uploads_${STAMP}.tar.gz"
# Dump-header check without a pipeline: `grep -q` closes the pipe early and gunzip
# dies with SIGPIPE(141), which `set -o pipefail` treats as a failure.
if ! gunzip -c "$BACKUP_DIR/tracker_${STAMP}.sql.gz" | sed -n '1,10p' | grep -qi "PostgreSQL database dump"; then
  echo "dump header missing — file is not a valid pg_dump"
  exit 1
fi

# Off-site sync (rsync over whatever mounts OFFSITE_DIR: NFS/CIFS/sshfs/second disk).
if [ -n "$OFFSITE_DIR" ]; then
  echo "[$(date -Is)] off-site rsync → $OFFSITE_DIR"
  mkdir -p "$OFFSITE_DIR"
  rsync -a --delete "$BACKUP_DIR/" "$OFFSITE_DIR/"
fi

# Retention (local + off-site).
find "$BACKUP_DIR" -name 'tracker_*.sql.gz'    -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'uploads_*.tar.gz'    -mtime +"$RETENTION_DAYS" -delete
if [ -n "$OFFSITE_DIR" ]; then
  find "$OFFSITE_DIR" -name 'tracker_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
  find "$OFFSITE_DIR" -name 'uploads_*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
fi

echo "[$(date -Is)] BACKUP_OK tracker_${STAMP} ($(du -h "$BACKUP_DIR/tracker_${STAMP}.sql.gz" | cut -f1), uploads $(du -h "$BACKUP_DIR/uploads_${STAMP}.tar.gz" | cut -f1))"
