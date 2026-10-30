#!/bin/sh

set -eu
umask 077

STATE_DIR=${STATE_DIR:-/state}
BACKUP_DIR=${BACKUP_DIR:-/backups}
timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
temporary_archive="$BACKUP_DIR/.media-server-state-$timestamp.tar.gz.tmp"
final_archive="$BACKUP_DIR/media-server-state-$timestamp.tar.gz"

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

cleanup() {
    rm -f -- "$temporary_archive"
}

trap cleanup 0
trap 'exit 1' HUP INT TERM

if [ ! -d "$STATE_DIR" ]; then
    log "ERROR: state directory does not exist: $STATE_DIR"
    exit 1
fi

if [ ! -d "$BACKUP_DIR" ] || [ ! -w "$BACKUP_DIR" ]; then
    log "ERROR: backup directory is not writable: $BACKUP_DIR"
    exit 1
fi

if [ -e "$temporary_archive" ] || [ -e "$final_archive" ]; then
    log "ERROR: backup already exists for timestamp $timestamp"
    exit 1
fi

log "Creating backup archive $final_archive"
tar --create --gzip --file "$temporary_archive" --preserve-permissions --numeric-owner \
    --exclude='./downloads/usenet/incomplete' \
    --exclude='./downloads/torrent/incomplete' \
    --directory "$STATE_DIR" .
chmod 600 "$temporary_archive"

log "Verifying backup archive"
if ! tar --list --gzip --file "$temporary_archive" >/dev/null; then
    log "ERROR: archive integrity check failed"
    exit 1
fi

mv -- "$temporary_archive" "$final_archive"
log "Published verified backup $final_archive"

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'media-server-state-*.tar.gz' -printf '%f\n' |
    LC_ALL=C sort -r |
    awk 'NR > 4' |
    while IFS= read -r old_backup; do
        rm -- "$BACKUP_DIR/$old_backup"
        log "Removed old backup $old_backup"
    done
