# [Pending] Độ trễ tra cứu còn lại ở graph v2 (memory đã xong)

> **Phần memory đã làm xong:** memory dài hạn theo hồ sơ bệnh nhân, lưu Postgres, bỏ embedding hoàn toàn (đọc là một truy vấn SQL, không tìm theo ngữ nghĩa), v2 đọc một lần ở node đầu `load_memory`, ghi theo batch ở nền. Xem `core/app/kien-truc-memory.md` và `docs/notice/agent-graph-versions.md`. Bối cảnh: trước đó mỗi node v2 gọi `with_memory()` kèm một request embedding (đo 4 lần trên store rỗng ≈ 19 s, có lần 10,8 s), cùng một query ở cả 6–8 lần mỗi lượt. Chưa đo lại tổng thời gian một lượt sau thay đổi.

## Còn pending
- **`extract_entities` lặp trong `hybrid_retrieval`** (`tools/hybrid_retrieval/kg.py`, `pipeline.py`, `tool.py::_bm25_query`): mỗi lệnh `hybrid_retrieval` / `keyword_search` gọi LLM trích thực thể để mở rộng query BM25 Việt–Anh (trace: node `tools` 15 s, trong đó LLM 10,4 s). Hướng khả thi, cần đo trước: chạy song song với nhánh semantic, hoặc dùng model nhỏ hơn cho bước này, hoặc gộp entities đã trích vào state tích luỹ rồi truyền qua `entities_fn` sẵn có của `run_hybrid`.
- **Độ trễ API thất thường** làm số đo giây không đáng tin: `plan` 27–33 s và `reflect` tới 35 s ở vài lượt, không do memory. Cần log thời gian "node bắt đầu → LLM bắt đầu" để tách riêng.
- **`plan` vẫn sinh `queries` cho câu hỏi tiếp** không có dữ kiện mới, nên chưa rẽ sang `answer` (xem kết quả đo ở notice). Hướng: chỉnh `PLAN_SYSTEM` (`prompt/v2.py`) rồi đo lại, cần duyệt trước.
- **Hợp nhất memory với `clinical_facts`:** xem `persistent-clinical-facts.md`.
