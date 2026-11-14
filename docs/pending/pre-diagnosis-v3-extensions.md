# [Pending] Mở rộng tiền chẩn đoán v3

Những phần của doc thiết kế ("Thiết kế pipeline tiền chẩn đoán da liễu") cố ý chưa làm ở bản v3 hiện tại, hoặc phát sinh khi chạy thật. Hạn chế chi tiết từng giai đoạn: `docs/notice/pre-diagnosis-v3-limitations.md`.

## Vấn đề
Bản v3 chạy thông khối 0–6 nhưng chất lượng xếp hạng phụ thuộc KG (PrimeKG + cạnh trích từ sách) đang thưa và lệch về bệnh hiếm; nhiều bước dùng ngưỡng / trọng số chọn tay.

## Hướng đề xuất
1. **Đánh giá & ablation** (doc mục "Đánh giá"): `RunConfig` trong `AgentContext` (model, bật/tắt VLM, `vlm_verify`, trọng số fuse, DAG vs agent), runner offline đọc dataset (SkinCaRe + mô tả Gemini), chấm top-1/top-3 trên 22 lớp, grounding (tỉ lệ ý có mã hợp lệ — đã có `claims.status`), số câu hỏi tới khi dừng, recall red flag, chi phí. StepRecorder (`AGENT_STEP_LOG_DIR`) đã ghi từng node. So sánh baseline DeepSeek Flash; độ chính xác theo màu da.
2. **Tune trọng số** `fuse_scores` / `DELTA` / `MAX_ROUNDS` trên tập validation thay vì chọn tay.
3. **Entity linking**: FAISS SapBERT đa ngôn ngữ; link lên node cha `IS_A` khi dưới ngưỡng.
4. **KG**: PPR có personalization theo IC trên đồ thị con lọc metapath (khối 1); PCST kiểu G-Retriever cho đồ thị con (khối 2); bổ sung cạnh phenotype lâm sàng cho bệnh da thường gặp.
5. **Guideline**: chunk lại theo mục bệnh hoặc gắn disease id bằng LLM theo nội dung (primary hiện 2.2%); gắn id vào stage `index` của pipeline; xử lý sách tiếng Việt.
6. **Chuẩn hoá ID sang MONDO** (`tools/v3/ids.to_mondo` đã có cho node nguồn MONDO).
7. **Danh sách phenotype "hỏi được" và "nhìn thấy được"** do bác sĩ chọn, thay bộ lọc từ khoá `is_askable` và việc gọi `vlm_verify` cho mọi câu hỏi.
8. **Report**: ghi `consultation_report` + `clinical_fact_provenance` (node id, path, nguồn cạnh, nguồn fact + ngày).
9. **Agent / subagent** dùng chung bộ tool `tools/v3/` (doc mục "DAG và agent dùng chung tool").

## Câu hỏi cần chốt
- Trọng số và điều kiện dừng; ai duyệt red flag và bảng map CNN.
- Có ghi fact v3 vào graph theo dõi bệnh nhân như v2 không.
- Có cho người bệnh thấy tên bệnh (dạng "các khả năng cần bác sĩ phân biệt") không.

## Phụ thuộc
Dataset đánh giá có nhãn; bác sĩ duyệt red flag / danh sách phenotype; endpoint provenance ở clinical (có thể đụng `dto/base`).
