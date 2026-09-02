#!/usr/bin/env bash
# Nightly backup drill helper (ROADMAP E9).
# Usage: MOSS_PG_URL=... ./deploy/backup.sh /var/backups/mossvoice
set -euo pipefail
DEST="${1:?backup directory}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$DEST/$STAMP"
if [[ -z "${MOSS_PG_URL:-}" ]]; then
  echo "MOSS_PG_URL required" >&2
  exit 1
fi
pg_dump "$MOSS_PG_URL" | gzip > "$DEST/$STAMP/pg.sql.gz"
echo "wrote $DEST/$STAMP/pg.sql.gz"
# MinIO versioning should be enabled on the bucket; this only snapshots metadata.
if command -v mc >/dev/null 2>&1 && [[ -n "${MOSS_S3_BUCKET:-}" ]]; then
  mc mirror --overwrite "local/${MOSS_S3_BUCKET}" "$DEST/$STAMP/objects" || true
fi
echo "OK $STAMP"
