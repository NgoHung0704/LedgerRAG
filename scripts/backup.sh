#!/usr/bin/env bash
# LedgerRAG backup — Postgres (parsed truth + records), Qdrant (vectors),
# MinIO (crop images + originals). Everything the platform holds; run it on a
# schedule (cron) and copy the output off-box.
#
#   bash scripts/backup.sh [OUT_DIR]     # default ./backups
#
# Postgres is dumped logically (consistent). Qdrant and MinIO are snapshotted
# from their volumes via a throwaway container, so no client tools are needed
# on the host. Restore instructions are printed at the end.

set -euo pipefail

OUT_DIR="${1:-./backups}"
TS="$(date +%Y%m%d-%H%M%S)"
DEST="$OUT_DIR/$TS"
mkdir -p "$DEST"

# volume names are <project>_<volume>; default compose project = dir name
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}"
vol() { echo "${PROJECT}_$1"; }

echo "→ backing up to $DEST"

echo "  · postgres (pg_dump)"
docker compose exec -T postgres pg_dump -U ledgerrag ledgerrag \
  | gzip > "$DEST/postgres.sql.gz"

tar_volume() {  # <volume> <outfile>
  local v; v="$(vol "$1")"
  if docker volume inspect "$v" >/dev/null 2>&1; then
    docker run --rm -v "$v":/data:ro -v "$(cd "$DEST" && pwd)":/backup alpine \
      tar czf "/backup/$2" -C /data .
    echo "  · $1 → $2"
  else
    echo "  ! volume $v not found — skipped"
  fi
}

tar_volume qdrant_data qdrant.tgz
tar_volume minio_data  minio.tgz

# a checksum manifest so a restore can verify integrity
( cd "$DEST" && sha256sum ./* > SHA256SUMS )
echo "→ done. $(du -sh "$DEST" | cut -f1) in $DEST"

cat <<EOF

Restore (into a STOPPED stack, empty volumes):
  gunzip -c "$DEST/postgres.sql.gz" | docker compose exec -T postgres \\
    psql -U ledgerrag -d ledgerrag
  docker run --rm -v ${PROJECT}_qdrant_data:/data -v "$(cd "$DEST" && pwd)":/b \\
    alpine sh -c 'rm -rf /data/* && tar xzf /b/qdrant.tgz -C /data'
  docker run --rm -v ${PROJECT}_minio_data:/data -v "$(cd "$DEST" && pwd)":/b \\
    alpine sh -c 'rm -rf /data/* && tar xzf /b/minio.tgz -C /data'
EOF
