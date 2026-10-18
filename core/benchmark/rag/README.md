# Benchmark RAG (LLM vs LLM + RAG) — chưa làm

## Mục tiêu

Chứng minh bằng số liệu từng thành phần (sách, Knowledge Graph, web) đóng góp bao nhiêu vào câu trả lời so với LLM thuần,
gồm cả độ đúng lẫn an toàn (bỏ sót red flag, sai mức khẩn cấp). Làm sau retrieval và graph; chưa có code. Không gồm ảnh/CNN.

## Phương pháp

- **Ablation, mỗi lần đổi một thứ** (cùng model, cùng prompt, `--repeat 3`):

  | ID | Mô tả |
  |---|---|
  | `baseline_llm` | LLM thuần, không tool |
  | `no_kg` | LLM + RAG sách (+ web), không graph |
  | `no_book` | LLM + graph, không RAG sách |
  | `no_web` | tắt web search (mức toàn pipeline) |
  | `full` | hệ thống thật |

- **Chỉ số tự động:** hit@1, hit@3 theo bệnh trên bộ ca có gold mức bệnh.
- **Rubric + LLM-as-a-judge** (trục chính), thang 0-3: `correctness`, `grounding`, `safety`, `urgency`, `helpfulness`.
  `safety` chấm pass/fail; `grounding` không áp dụng cho `baseline_llm`.
- **Độ tin cậy của judge:** model khác model sinh, giấu nhãn cấu hình, xáo thứ tự, có ví dụ neo cho từng mức điểm;
  chấm tay 30 ca để tính kappa; bác sĩ/giảng viên duyệt 15-20 ca.

Kế hoạch gốc: [`docs/benchmark/ke-hoach-benchmark-tong-hop.md`](../../../docs/benchmark/ke-hoach-benchmark-tong-hop.md) mục 6.

## Việc cần làm

- [ ] Soạn bộ ca (bộ `tier_b_vi.jsonl` đã bị bỏ); gợi ý sinh từ file bệnh trong `core/data_ingest`.
- [ ] Viết rubric (`ke-hoach-danh-gia.md` được tham chiếu nhưng không còn trong `docs/benchmark/`; kiểm tra git history).
- [ ] Cơ chế bật/tắt tool theo cấu hình; sửa check `plan_first` của `experiment.py` còn kiểm `make_plan`.
- [ ] Runner + judge + report (cấu hình x tiêu chí, CI bootstrap).
- [ ] Khi có KG tự trích: thêm cấu hình `full` với KG mới.

## Hạn chế

Judge là LLM (có thể thiên vị câu dài), không thay đánh giá của bác sĩ. Kết quả AI chỉ là gợi ý, không phải chẩn đoán y khoa.
