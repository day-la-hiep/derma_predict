# Benchmark graph (Knowledge Graph) — chưa làm

## Mục tiêu

Đo `knowledge_graph_query` (Neo4j) của agent trả đúng bệnh, đúng quan hệ đến đâu, và làm mốc so sánh khi đổi graph
(ví dụ graph tự trích từ tài liệu). Làm sau benchmark retrieval; chưa có code.

## Phương pháp

- **Gold tự động** sinh từ `core/data_ingest/01_normalize/output/diseases`:
  `differential` <- `differentials`, `red_flags_risk` <- `red_flags`, `diseases_with_symptom` <- `primary.kb_ids`.
- **So sánh:** G0 (không KG, khớp chuỗi tên bệnh) với G1 (`knowledge_graph_query` theo intent).
- **Chỉ số:** entity-resolution rate, fact precision@k, tỉ lệ `notes` lỗi, latency p50/p95; CI 95% bằng bootstrap.
- Dùng lại `../common/` và cấu trúc `prepare/` + `evaluate/` của `../retrieval/`.

Kế hoạch gốc: [`docs/benchmark/ke-hoach-benchmark-tong-hop.md`](../../../docs/benchmark/ke-hoach-benchmark-tong-hop.md) mục 5.

## Việc cần làm

- [ ] Sinh gold theo intent từ file bệnh.
- [ ] Runner G0, G1 và report.
- [ ] Chốt số của KG hiện tại **trước** khi thêm graph tự trích (mỗi relation tự trích lưu kèm `chunk_id` nguồn, nhãn nguồn riêng trong Neo4j);
  sau đó chạy lại để so sánh KG cũ / cũ + mới / mới.
