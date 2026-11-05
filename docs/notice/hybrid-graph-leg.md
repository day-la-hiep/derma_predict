# Nhánh graph của `hybrid_retrieval`

- **Là gì:** nhánh thứ ba cạnh semantic và BM25 (`agent/tools/hybrid_retrieval/graph.py`). Thực thể trích từ câu hỏi →
  cạnh `source='DOC'` trong Neo4j → `chunk_ids` của cạnh → chunk sách lấy từ Qdrant → trộn RRF → rerank.
  Kết quả vẫn là đoạn sách (`source="book"`), chunk do đồ thị đề xuất có thêm `via_graph: true`.
- **Luôn chạy** với sách (không có công tắc, để benchmark đo trực tiếp); corpus ca bệnh trả rỗng. `run_hybrid` luôn có `graph_fn`.
- **Phụ thuộc:** sách đã chạy bước `graph_index`. Chưa có cạnh DOC thì nhánh rỗng, hybrid chạy như cũ.
- **Dễ sai:** `chunk_ids` trên cạnh là id lúc trích quan hệ. Chunk lại hoặc index lại sách mà không chạy lại graph thì
  id lệch; `RetrievalService.fetch` bỏ id không thấy và ghi warning.
- **Khớp tên:** chính xác (tên/synonym, không phân biệt hoa thường) trước, chỉ khi không có mới khớp chứa. Entity tiếng Việt
  chỉ khớp nếu đồ thị có tên/synonym tiếng Việt; thường khớp qua tên tiếng Anh do LLM dịch.
- `knowledge_graph_query` (template PrimeKG/DermO) và `query_document_graph` không đổi; nhánh này độc lập với chúng.
