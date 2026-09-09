#!/bin/sh
# Consistent SQLite snapshot + retention. Runs inside the `backup` sidecar.
set -eu

DB="${FAMILY_AGENT_DB_PATH:-/data/family.db}"
OUT_DIR="/data/backups"
KEEP_DAYS="${FAMILY_AGENT_BACKUP_KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$OUT_DIR"

if [ ! -f "$DB" ]; then
  echo "backup: no db at $DB yet, skipping"
  exit 0
fi

# .backup takes a read lock and produces a valid file even while the app is writing.
sqlite3 "$DB" ".backup '$OUT_DIR/family-$STAMP.db'"
gzip -f "$OUT_DIR/family-$STAMP.db"
echo "backup: wrote $OUT_DIR/family-$STAMP.db.gz"

# Retention
find "$OUT_DIR" -name 'family-*.db.gz' -type f -mtime "+$KEEP_DAYS" -delete

# Optional off-host copy: uncomment and provide rclone config / a mount.
# rclone copy "$OUT_DIR" "remote:family-agent-backups" --max-age 25h
