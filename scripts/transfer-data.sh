#!/usr/bin/env bash
# Xuất / khôi phục dữ liệu 4 volume (postgres, minio, qdrant, neo4j) vào scripts/backup (đã gitignore).
#   scripts/transfer-data.sh export           # máy cũ, sau khi tắt stack
#   scripts/transfer-data.sh restore          # máy mới, sau khi copy ./backup sang, tắt stack
# Prod: VOL_PREFIX=derma-hospital-prod_ BACKUP_DIR=... scripts/transfer-data.sh export
# Xem docs/module/chuyen-du-lieu-sang-may-khac.md

set -euo pipefail
cd "$(dirname "$0")"  # scripts/

VOL_PREFIX="${VOL_PREFIX:-derma-hospital_derma-}"
BACKUP_DIR="$(realpath -m "${BACKUP_DIR:-./backup}")"
SERVICES=(postgres minio qdrant neo4j)

check_stopped() {
  local running
  running=$(docker ps --format '{{.Names}}' --filter "volume=${VOL_PREFIX}${1}_data" | tr '\n' ' ')
  [[ -z "$running" ]] || { echo "Container đang dùng volume ${VOL_PREFIX}${1}_data: $running— tắt stack trước (docker compose down, không -v)." >&2; exit 1; }
}

case "${1:-}" in
  export)
    mkdir -p "$BACKUP_DIR"
    for s in "${SERVICES[@]}"; do
      docker volume inspect "${VOL_PREFIX}${s}_data" >/dev/null || { echo "Không có volume ${VOL_PREFIX}${s}_data (sai VOL_PREFIX?)" >&2; exit 1; }
      check_stopped "$s"
    done
    for s in "${SERVICES[@]}"; do
      echo "==> export $s"
      docker run --rm -v "${VOL_PREFIX}${s}_data:/data:ro" -v "$BACKUP_DIR:/out" alpine \
        tar czf "/out/${s}.tar.gz" -C /data .
    done
    ls -lh "$BACKUP_DIR"
    ;;
  restore)
    for s in "${SERVICES[@]}"; do
      [[ -f "$BACKUP_DIR/${s}.tar.gz" ]] || { echo "Thiếu $BACKUP_DIR/${s}.tar.gz" >&2; exit 1; }
      docker volume create "${VOL_PREFIX}${s}_data" >/dev/null
      check_stopped "$s"
    done
    echo "!! Sẽ GHI ĐÈ toàn bộ dữ liệu trong volume ${SERVICES[*]} (prefix ${VOL_PREFIX})."
    read -r -p "Gõ 'yes' để tiếp tục: " ok
    [[ "$ok" == "yes" ]] || exit 1
    for s in "${SERVICES[@]}"; do
      echo "==> restore $s"
      docker run --rm -v "${VOL_PREFIX}${s}_data:/data" -v "$BACKUP_DIR:/in:ro" alpine \
        sh -c "find /data -mindepth 1 -delete && tar xzf /in/${s}.tar.gz -C /data"
    done
    echo "Xong. Bật lại: docker compose up -d (không chạy migrate/init-db)."
    ;;
  *)
    echo "Dùng: $0 export|restore" >&2; exit 1 ;;
esac
