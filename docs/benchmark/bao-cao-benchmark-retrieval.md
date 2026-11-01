# Báo cáo đánh giá benchmark retrieval (tra cứu sách)

Phạm vi: chỉ đo bước tra sách của agent (`hybrid_retrieval`). Chưa đo Knowledge Graph và chưa đo câu trả lời cuối của agent.

## 1. Bộ test

### Kho dữ liệu
- Snapshot `20261017-378`: 378 chunk trong Qdrant, đều từ sách *Hướng dẫn chẩn đoán điều trị Da liễu* (Bộ Y tế, tiếng Việt).
- Embedding `qwen/qwen3-embedding-8b`, reranker `qwen/qwen3-reranker-8b`.

### Cách sinh câu hỏi
1. Chọn mẫu 120 chunk từ snapshot. Bỏ chunk ngắn (dưới 300 ký tự) và các mục như mục lục, tài liệu tham khảo, phụ lục.
2. RAGAS dựng đồ thị tri thức từ các chunk này, rồi sinh 42 câu hỏi theo vai bệnh nhân. Có hai loại: đơn bước (1 chunk) và đa bước (nhiều chunk). Model sinh là `gemma-4-26b-a4b-it`.
3. Nhãn đúng là các chunk nguồn mà RAGAS nêu (`reference_contexts`).
4. Lọc tự động:
   - **Chép cụm:** loại câu hỏi chép từ 8 âm tiết liên tiếp trở lên từ chunk nguồn, vì như vậy BM25 gần như chắc chắn tìm ra. Loại 2 câu.
   - **Không trả lời được:** một model khác model sinh (`deepseek-flash`) thử trả lời chỉ dựa trên chunk nguồn. Câu nào không trả lời được thì bị loại. Loại 16 câu.
   - **Trùng lặp:** loại câu có cosine ≥ 0.9 với câu đã giữ.
5. Kết quả: giữ 24 câu (10 đơn bước, 14 đa bước), kèm 36 nhãn chunk.

### Hạn chế của bộ test
- Cỡ mẫu nhỏ (n=24) nên khoảng tin cậy rộng.
- Nhãn chỉ gồm chunk RAGAS nêu, chunk khác cũng trả lời được vẫn bị tính sai. Vì vậy hit@k và recall@k là cận dưới.
- Câu hỏi sinh từ chính chunk nên từ vựng gần văn sách, có lợi cho BM25.
- Chưa duyệt tay bộ câu hỏi (mẫu duyệt ở `ragas_review.md`).
- Kho chỉ có một sách tiếng Việt, nên chưa đo tìm xuyên ngôn ngữ và mở rộng query Việt-Anh không có tác dụng.

## 2. Các hệ thống được so sánh

| Tên | Cách ghép |
|---|---|
| `random` | Chunk ngẫu nhiên (mốc sàn) |
| `semantic` | Chỉ embedding |
| `bm25` | Chỉ BM25, query gốc |
| `bm25_expand` | BM25 với query đã mở rộng Việt-Anh |
| `rrf` | Semantic + BM25 mở rộng, gộp RRF, chưa rerank |
| `hybrid` | `rrf` rồi rerank. Chính là tool `hybrid_retrieval` của agent |
| `hybrid_no_expand` | Như `hybrid` nhưng BM25 dùng query gốc |
| `semantic_rerank` | Semantic rồi rerank |
| `bm25_expand_rerank` | BM25 mở rộng rồi rerank |

Chỉ số: hit@k (top-k có ít nhất một chunk đúng), recall@10 (tỉ lệ chunk đúng nằm trong top-10), MRR@10. Khoảng tin cậy 95% bằng bootstrap theo query. Run `ragas-v1`, ngày 2026-10-17.

## 3. Kết quả

| Hệ thống | hit@1 | hit@3 | hit@5 | hit@10 | recall@10 | MRR@10 |
|---|---|---|---|---|---|---|
| random | 0.00 | 0.00 | 0.04 | 0.12 | 0.08 | 0.02 |
| semantic | 0.58 | 0.75 | 0.83 | 0.96 | 0.90 | 0.70 |
| bm25 | 0.50 | 0.67 | 0.83 | 0.88 | 0.73 | 0.63 |
| bm25_expand | 0.50 | 0.71 | 0.88 | 0.92 | 0.77 | 0.64 |
| rrf | 0.67 | 0.92 | 0.92 | 0.92 | 0.83 | 0.77 |
| **hybrid (thật)** | **0.83** | **0.92** | **1.00** | **1.00** | **0.94** | **0.90** |
| hybrid_no_expand | 0.83 | 0.92 | 1.00 | 1.00 | 0.94 | 0.90 |
| semantic_rerank | 0.88 | 0.88 | 0.96 | 0.96 | 0.90 | 0.90 |
| bm25_expand_rerank | 0.83 | 0.88 | 0.96 | 0.96 | 0.88 | 0.88 |

Khoảng tin cậy 95% đầy đủ của từng ô nằm trong `core/benchmark/data/retrieval/runs/ragas-v1/report.md`.

### So sánh cặp (hiệu hit@5, CI 95%)

| A − B | Hiệu | CI |
|---|---|---|
| hybrid − semantic | +0.17 | [+0.04, +0.33] |
| hybrid − bm25_expand | +0.12 | [+0.00, +0.25] |
| hybrid − rrf | +0.08 | [+0.00, +0.21] |
| hybrid − semantic_rerank | +0.04 | [+0.00, +0.12] |
| hybrid − hybrid_no_expand | +0.00 | [+0.00, +0.00] |

### Theo loại câu hỏi (hit@5 / recall@10)

| Hệ thống | Đa bước (n=14) | Đơn bước (n=10) |
|---|---|---|
| semantic | 0.86 / 0.89 | 0.80 / 0.90 |
| bm25_expand | 0.86 / 0.68 | 0.90 / 0.90 |
| rrf | 1.00 / 0.86 | 0.80 / 0.80 |
| hybrid | 1.00 / 0.89 | 1.00 / 1.00 |
| semantic_rerank | 1.00 / 0.89 | 0.90 / 0.90 |

## 4. Nhận xét

- Hệ thống thật (`hybrid`) tốt nhất ở hầu hết chỉ số: hit@5 = 1.00, MRR@10 = 0.90.
- Hybrid hơn semantic thô có ý nghĩa thống kê (CI không chứa 0). Hybrid hơn `rrf`, `bm25_expand` và `semantic_rerank` thì CI chạm 0, chưa kết luận chắc được.
- Rerank đóng góp nhiều nhất: `semantic_rerank` đã đạt hit@1 = 0.88. Gộp RRF thêm vào chủ yếu cải thiện recall@10 (0.90 lên 0.94).
- Mở rộng query Việt-Anh chưa có tác dụng (`hybrid` = `hybrid_no_expand`) vì kho chỉ có tiếng Việt.
- Do cỡ mẫu nhỏ và nhãn thiếu, các chênh lệch nhỏ giữa nhóm có rerank là nhiễu. Cần tăng số câu và duyệt tay trước khi kết luận thêm.

Kết quả AI chỉ là gợi ý hỗ trợ, không phải chẩn đoán y khoa.
