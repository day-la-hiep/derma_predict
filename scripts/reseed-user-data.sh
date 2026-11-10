#!/bin/sh
# Xoá dữ liệu người dùng (identity, consultation, clinical) rồi nạp lại seed demo của identity (V2__seed_demo.sql).
# Giữ nguyên schema, flyway_schema_history, database knowledge/ai, Qdrant, Neo4j, MinIO. Cần `make infra` và các service đã chạy Flyway ít nhất một lần.
# Dùng: ./scripts/reseed-user-data.sh [--yes]   (--yes bỏ bước hỏi xác nhận)
set -e
cd "$(dirname "$0")/.."
CONTAINER="${POSTGRES_CONTAINER:-derma-postgres}"
SEED=identity_service/src/main/resources/db/seed/V2__seed_demo.sql

if [ "$1" != "--yes" ]; then
  printf "Sẽ XOÁ toàn bộ dữ liệu trong database identity, consultation, clinical rồi nạp lại seed. Tiếp tục? [y/N] "
  read -r answer
  [ "$answer" = "y" ] || { echo "Đã huỷ."; exit 1; }
fi

# dừng sớm nếu database chưa được service tạo bảng (Flyway chưa chạy)
for db in identity consultation clinical; do
  docker exec "$CONTAINER" psql -U postgres -d "$db" -tAc "SELECT 1 FROM flyway_schema_history LIMIT 1" | grep -q 1 \
    || { echo "database $db chưa có flyway_schema_history: chạy service tương ứng một lần trước."; exit 1; }
done

for db in identity consultation clinical; do
  tables=$(docker exec "$CONTAINER" psql -U postgres -d "$db" -tAc \
    "SELECT string_agg(quote_ident(tablename), ',') FROM pg_tables WHERE schemaname='public' AND tablename <> 'flyway_schema_history'")
  echo "==> truncate $db: $tables"
  docker exec "$CONTAINER" psql -U postgres -d "$db" -v ON_ERROR_STOP=1 -c "TRUNCATE $tables RESTART IDENTITY CASCADE"
done

echo "==> nạp seed identity"
docker exec -i "$CONTAINER" psql -U postgres -d identity -v ON_ERROR_STOP=1 < "$SEED"
echo "Xong: user-1, doctor-1, admin-1 (mật khẩu 123456) + 4 hồ sơ bệnh nhân."
