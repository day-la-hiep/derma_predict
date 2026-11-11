#!/bin/sh
# Tạo 5 database của các service trong container Postgres đang chạy; chạy lại nhiều lần không sao, không đụng database có sẵn (derma_hospital_db).
set -e
CONTAINER="${POSTGRES_CONTAINER:-derma-postgres}"
for db in identity consultation clinical knowledge ai; do
  exists=$(docker exec "$CONTAINER" psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'")
  if [ "$exists" = "1" ]; then
    echo "đã có database $db"
  else
    docker exec "$CONTAINER" psql -U postgres -c "CREATE DATABASE $db"
  fi
done
