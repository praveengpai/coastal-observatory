#!/bin/sh
# Nightly encrypted database backup. Run from the host's cron:
#   30 1 * * * /opt/observatory/deploy/backup.sh >> /var/log/observatory-backup.log 2>&1
# Needs BACKUP_DIR and a GPG recipient key (BACKUP_GPG_RECIPIENT) agreed with NIO IT.
set -eu
cd "$(dirname "$0")/.."
BACKUP_DIR=${BACKUP_DIR:-/var/backups/observatory}
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "$BACKUP_DIR"
docker compose exec -T db pg_dump -U observatory -Fc observatory \
  | gpg --batch --yes --encrypt --recipient "${BACKUP_GPG_RECIPIENT:?set BACKUP_GPG_RECIPIENT}" \
  > "$BACKUP_DIR/observatory-$STAMP.dump.gpg"
find "$BACKUP_DIR" -name 'observatory-*.dump.gpg' -mtime +30 -delete
echo "$STAMP backup ok"
