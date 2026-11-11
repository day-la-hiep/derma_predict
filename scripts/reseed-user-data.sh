#!/bin/sh
# Xoá dữ liệu người dùng rồi nạp lại seed demo:
#   - Postgres: toàn bộ bảng của database identity, consultation, clinical
#   - Qdrant:   mọi điểm trong collection ca bệnh đã chốt (derma_finalize_reports)
#   - Neo4j:    node hành trình bệnh nhân (Patient, ConsultationSession, ClinicalFact, SuspectedCondition, Advice, PatientImage)
#   - Postgres ai: checkpoint hội thoại và bộ nhớ bệnh nhân của agent (schema langgraph)
#   - MinIO:    ảnh đính kèm tin nhắn (bucket derma-attachments)
# Sau khi dọn sạch, nạp lại:
#   - identity:      tài khoản + 4 hồ sơ (identity_service/.../db/seed/V2__seed_demo.sql, là migration Flyway nên không sửa nội dung)
#   - consultation:  scripts/seed/consultation.sql  (hội thoại AI, tin nhắn, kênh theo dõi sau khám)
#   - clinical:      scripts/seed/clinical.sql      (đợt bệnh, giả thuyết, dữ kiện, lịch hẹn đủ trạng thái, lần khám, báo cáo kết luận)
#   - Qdrant + Neo4j: gọi POST /internal/cases/reindex của knowledge để dựng từ báo cáo kết luận mẫu (cần knowledge đang chạy và key embedding)
# Giữ nguyên schema, flyway_schema_history, database knowledge, chunk sách trong Qdrant, đồ thị sách/DermO trong Neo4j, bucket sách (derma-documents, derma-books).
# Cần `make infra` và các service đã chạy Flyway ít nhất một lần.
# Dùng: ./scripts/reseed-user-data.sh [--yes]   (--yes bỏ bước hỏi xác nhận)
# Biến môi trường (có mặc định): POSTGRES_CONTAINER, NEO4J_CONTAINER, NEO4J_USER, NEO4J_PASSWORD, QDRANT_URL, QDRANT_API_KEY (mặc định đọc từ knowledge_service/.env), QDRANT_FINALIZE_REPORT_COLLECTION, MINIO_ENDPOINT/MINIO_ACCESS_KEY/MINIO_SECRET_KEY/MINIO_BUCKET, KNOWLEDGE_URL, INTERNAL_API_KEY (mặc định đọc từ knowledge_service/.env).
set -e
cd "$(dirname "$0")/.."
CONTAINER="${POSTGRES_CONTAINER:-derma-postgres}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-derma-neo4j}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-derma12345}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_COLLECTION="${QDRANT_FINALIZE_REPORT_COLLECTION:-derma_finalize_reports}"
SEED=identity_service/src/main/resources/db/seed/V2__seed_demo.sql

# key Qdrant nằm trong .env của knowledge (đã gitignore); không in ra màn hình
if [ -z "${QDRANT_API_KEY+x}" ] && [ -f knowledge_service/.env ]; then
  QDRANT_API_KEY=$(grep -E '^QDRANT_API_KEY=' knowledge_service/.env | cut -d= -f2- | tr -d "\"'" || true)
fi

if [ "$1" != "--yes" ]; then
  printf "Sẽ XOÁ toàn bộ dữ liệu người dùng: database identity/consultation/clinical, bộ nhớ và checkpoint của agent (database ai), ca bệnh trong Qdrant (%s), đồ thị bệnh nhân trong Neo4j, ảnh đính kèm trong MinIO; rồi nạp lại seed. Tiếp tục? [y/N] " "$QDRANT_COLLECTION"
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

echo "==> nạp seed consultation"
docker exec -i "$CONTAINER" psql -U postgres -d consultation -v ON_ERROR_STOP=1 < scripts/seed/consultation.sql
echo "==> nạp seed clinical"
docker exec -i "$CONTAINER" psql -U postgres -d clinical -v ON_ERROR_STOP=1 < scripts/seed/clinical.sql

# Qdrant: xoá điểm, giữ collection và index. Bộ lọc luôn đúng vì mọi điểm đều có case_id khác "__none__".
echo "==> Qdrant: xoá điểm trong $QDRANT_COLLECTION"
status=$(curl -s -o /tmp/reseed-qdrant.out -w '%{http_code}' -X POST "$QDRANT_URL/collections/$QDRANT_COLLECTION/points/delete?wait=true" \
  -H "api-key: ${QDRANT_API_KEY:-}" -H 'content-type: application/json' \
  -d '{"filter":{"must_not":[{"key":"case_id","match":{"value":"__none__"}}]}}')
if [ "$status" != "200" ]; then
  echo "Qdrant trả HTTP $status: $(cat /tmp/reseed-qdrant.out)" >&2
  exit 1
fi

# Neo4j: chỉ các label của hành trình bệnh nhân; đồ thị sách (Entity) và DermoTerm không đụng tới
echo "==> Neo4j: xoá node hành trình bệnh nhân"
docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
  "MATCH (n) WHERE any(l IN labels(n) WHERE l IN ['Patient','ConsultationSession','ClinicalFact','SuspectedCondition','Advice','PatientImage']) DETACH DELETE n"

# agent: checkpoint theo hội thoại và bộ nhớ theo bệnh nhân; giữ bảng *_migrations để service không chạy lại migration
echo "==> Postgres ai: xoá checkpoint và bộ nhớ agent"
docker exec "$CONTAINER" psql -U postgres -d ai -v ON_ERROR_STOP=1 -c \
  "TRUNCATE langgraph.checkpoint_blobs, langgraph.checkpoint_writes, langgraph.checkpoints, langgraph.store"

# MinIO: chỉ bucket ảnh đính kèm, xoá bằng S3 API (object nằm dạng thư mục xl.meta nên không rm tay được); bucket sách không đụng tới
echo "==> MinIO: xoá ảnh đính kèm trong ${MINIO_BUCKET:-derma-attachments}"
MINIO_BUCKET="${MINIO_BUCKET:-derma-attachments}" knowledge_service/.venv/bin/python -c '
import os
from minio import Minio
from minio.deleteobjects import DeleteObject

client = Minio(os.environ.get("MINIO_ENDPOINT", "localhost:9000"), os.environ.get("MINIO_ACCESS_KEY", "minio"), os.environ.get("MINIO_SECRET_KEY", "minio123"), secure=False)
bucket = os.environ["MINIO_BUCKET"]
names = [DeleteObject(o.object_name) for o in client.list_objects(bucket, recursive=True)]
errors = list(client.remove_objects(bucket, names))
if errors:
    raise SystemExit(f"MinIO không xoá được {len(errors)} đối tượng: {errors[0]}")
print(f"đã xoá {len(names)} ảnh")
'

# dựng lại Qdrant (embedding) + Neo4j từ báo cáo kết luận vừa nạp; knowledge chưa chạy thì chỉ nhắc, không coi là lỗi của việc reset
KNOWLEDGE_URL="${KNOWLEDGE_URL:-http://localhost:3054}"
if [ -z "${INTERNAL_API_KEY+x}" ] && [ -f knowledge_service/.env ]; then
  INTERNAL_API_KEY=$(grep -E '^INTERNAL_API_KEY=' knowledge_service/.env | cut -d= -f2- | tr -d "\"'" || true)
fi
echo "==> knowledge: reindex ca bệnh mẫu vào Qdrant + Neo4j"
if curl -sf -m 5 -o /dev/null "$KNOWLEDGE_URL/docs" || curl -sf -m 5 -o /dev/null "$KNOWLEDGE_URL/openapi.json"; then
  if curl -sS -m 600 -X POST "$KNOWLEDGE_URL/internal/cases/reindex" -H "X-Internal-Key: ${INTERNAL_API_KEY:-derma-internal-key-change-in-production}"; then
    echo
  else
    echo "Reindex lỗi: chạy lại bằng 'make reindex-cases' khi knowledge sẵn sàng." >&2
  fi
else
  echo "knowledge ($KNOWLEDGE_URL) chưa chạy: chạy 'make reindex-cases' sau khi bật knowledge để có ca bệnh trong Qdrant và Neo4j." >&2
fi

echo "Xong: user-1, doctor-1, admin-1 (mật khẩu 123456), 4 hồ sơ bệnh nhân và dữ liệu mẫu (7 hội thoại AI, 8 đợt bệnh, 6 lịch hẹn ở mọi trạng thái, 3 báo cáo kết luận, 4 kênh theo dõi)."
