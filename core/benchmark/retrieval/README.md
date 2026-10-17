# Benchmark retrieval (tra cứu sách)

Đo xem bước tra sách của agent (`hybrid_retrieval`) tìm đúng đoạn sách đến đâu, và từng thành phần (semantic, BM25, mở rộng query Việt-Anh, RRF, rerank) đóng góp bao nhiêu.
Chỉ đo **retrieval**: chưa đo Knowledge Graph, chưa đo câu trả lời của agent.

Kế hoạch và lý do thiết kế: [`docs/benchmark/ke-hoach-retrieval-chi-tiet.md`](../../../docs/benchmark/ke-hoach-retrieval-chi-tiet.md).
Các điểm dễ hiểu nhầm: [`docs/notice/retrieval-benchmark.md`](../../../docs/notice/retrieval-benchmark.md).

## Luồng chạy

```
prepare/corpus ──► snapshot chunk ──► prepare/queries/ragas_testset ──► queries + qrels
                                                                            │
                          evaluate/run (9 hệ thống) ◄───────────────────────┘
                                   │
                          evaluate/report ──► hit@k, recall@10, MRR@10, CI, so sánh cặp
```

| Phần | File | Việc làm |
|---|---|---|
| Chuẩn bị | `prepare/corpus.py` | Chụp mọi chunk trong Qdrant thành snapshot (bỏ trùng theo `chunk_id`). |
| Chuẩn bị | `prepare/queries/ragas_testset.py` | RAGAS sinh câu hỏi bệnh nhân (đơn bước + đa bước) và nhãn, rồi lọc. |
| Chạy test | `evaluate/systems.py`, `evaluate/run.py` | Chạy 9 hệ thống trên từng câu hỏi, có cache. |
| Chạy test | `evaluate/report.py` | Tính chỉ số và ghi `report.md`. |
| Dùng chung | `schema.py`, `paths.py`, `snapshot_store.py`, `../common/` | Kiểu dữ liệu, đường dẫn, đọc snapshot, JSONL, bootstrap CI. |

## Chạy

Mọi lệnh chạy từ `core/`. `AGENT_MODEL` phải có dạng `openai:...`, nếu không bước mở rộng query lỗi và BM25 âm thầm dùng query gốc.

```bash
cd core
export AGENT_MODEL=openai:google/gemma-4-26b-a4b-it

# 1. Snapshot (cần Qdrant có dữ liệu). Snapshot mới nhất là bản mặc định.
.venv/bin/python -m benchmark.retrieval.prepare.corpus

# 2. Sinh câu hỏi + nhãn: chạy bằng venv riêng của RAGAS (xem mục "Cài RAGAS")
PYTHONPATH=. OPENROUTER_API_KEY=... DEEPSEEK_API_KEY=... \
  benchmark/data/venv-ragas/bin/python -m benchmark.retrieval.prepare.queries.ragas_testset \
  --n 40 --chunks 120 --answer-model deepseek:deepseek-flash

# 3. Chạy các hệ thống rồi xuất báo cáo
.venv/bin/python -m benchmark.retrieval.evaluate.run --run-id v1
.venv/bin/python -m benchmark.retrieval.evaluate.report v1
```

Tham số hay dùng:

| Lệnh | Tham số |
|---|---|
| `ragas_testset` | `--n` số câu RAGAS sinh (trước lọc), `--chunks` số chunk dựng đồ thị, `--gen-model`, `--answer-model` (bắt buộc, phải khác model sinh), `--reuse-raw` (lọc lại từ `ragas_raw.jsonl`, không sinh lại), `--review-n` |
| `run` | `--run-id`, `--limit N` (thử nhanh N query đầu), `--systems`, `--queries`, `--snapshot`, `--concurrency` |
| `report` | `<run_id>`, `--qrels`, `--queries` |

Thời gian tham khảo: 120 chunk mất khoảng 20 phút để dựng đồ thị và sinh câu; toàn bộ 378 chunk ước chừng hơn 1 giờ.

### Cài RAGAS (một lần)

`ragas` chỉ cài trong môi trường riêng, không cài vào `.venv` của core (nó hạ cấp `openai`, `jiter`, `rich` và có thể làm hỏng agent). Môi trường này nằm trong `benchmark/data/` nên bị gitignore.

```bash
cd core
uv venv benchmark/data/venv-ragas --python 3.12
uv pip install --python benchmark/data/venv-ragas/bin/python ragas langchain-openai rapidfuzz \
  "langchain-community<0.4" "langchain-core<1" "langchain<1" "langchain-openai<1"
```

Các phiên bản bị ghim vì `ragas` 0.4.3 import `langchain_community.chat_models.vertexai`, chỉ có ở `langchain-community` 0.3. Script chỉ import phần pydantic của repo (`schema`, `snapshot_store`, `common`), không import `app.*` hay `agent.*`.

## 9 hệ thống (`evaluate/systems.py`)

Các hệ thống là các cách ghép khác nhau của cùng vài thành phần, để tách đóng góp của từng thành phần.

| Tên | Cách ghép |
|---|---|
| `random` | Chunk ngẫu nhiên (mốc sàn) |
| `semantic` | Chỉ semantic (embedding) |
| `bm25` | Chỉ BM25, query gốc |
| `bm25_expand` | BM25 với query đã mở rộng Việt-Anh |
| `rrf` | Semantic + BM25 mở rộng, gộp RRF, chưa rerank |
| `hybrid` | `rrf` rồi rerank. **Chính là tool `hybrid_retrieval` của agent** |
| `hybrid_no_expand` | Như `hybrid` nhưng BM25 dùng query gốc |
| `semantic_rerank` | Semantic rồi rerank (= `semantic_search`) |
| `bm25_expand_rerank` | BM25 mở rộng rồi rerank (= `keyword_search`) |

`hybrid`, `rrf`, `hybrid_no_expand` chạy thẳng `run_hybrid` trong `agent/tools/hybrid_retrieval/pipeline.py`, cùng hàm tool của agent dùng; benchmark chỉ truyền vào các hàm có cache và lọc theo snapshot. Không có bản dựng lại để phải đối chiếu.

## Dữ liệu sinh ra (`core/benchmark/data/`, gitignore, không commit)

```
data/retrieval/
  corpus/<snapshot>.jsonl      # nội dung sách (bản quyền) + manifest.json
  sets/queries.jsonl           # câu hỏi: qid, set, text, type, reference (câu trả lời mẫu)
  sets/qrels.jsonl             # nhãn: qid, chunk_id, content_hash, relevance=2, source=ragas
  ragas_raw.jsonl              # kết quả thô của RAGAS (trước lọc)
  ragas_log.jsonl              # trạng thái từng mẫu: kept / copy / unanswerable / duplicate / no_match / error
  ragas_review.md              # mẫu câu hỏi để duyệt tay
  runs/<run_id>/               # config.json, runs.jsonl, report.md
  cache.sqlite                 # cache embedding, rerank, LLM: chạy lại ra đúng kết quả cũ
data/venv-ragas/               # môi trường riêng cho RAGAS
```

Vì cả `data/` không được commit, người clone repo phải chạy lại bước chuẩn bị (cần Qdrant có dữ liệu) trước khi chạy `evaluate/`.

## Chỉ số

- `hit@k` (k = 1, 3, 5, 10): top-k có ít nhất một chunk đúng.
- `recall@10`: tỉ lệ chunk đúng nằm trong top-10 (câu đa bước có nhiều chunk đúng).
- `MRR@10`: nghịch đảo thứ hạng của chunk đúng đầu tiên.
- Khoảng tin cậy 95% bằng bootstrap theo query; so sánh cặp bằng bootstrap hiệu số trên cùng tập query.
- Báo theo bộ câu hỏi (đơn bước / đa bước) và theo sách của chunk đúng.

## Hạn chế cần nhớ khi đọc kết quả

- **Nhãn chỉ gồm chunk RAGAS nêu** (`reference_contexts`). Không có bước LLM chấm bổ sung (đã bỏ), nên chunk khác cũng trả lời được vẫn bị tính là sai: hit@k và recall@k là **cận dưới**.
- **Câu hỏi sinh từ chính chunk** nên từ vựng gần văn sách, có lợi cho BM25.
- **Chưa duyệt tay** bộ câu hỏi. `ragas_review.md` có sẵn mẫu để duyệt, kết quả duyệt chưa được ghi lại.
- **Cỡ mẫu nhỏ:** bộ thử hiện có 24 câu nên khoảng tin cậy rộng; chênh nhỏ giữa hệ thống gần nhau là nhiễu.
- **Kho hiện chỉ có sách Bộ Y tế (tiếng Việt)**, nên chưa đo tìm xuyên ngôn ngữ và mở rộng query Việt-Anh không có tác dụng. Andrews và Fitzpatrick đã tạm gỡ (bản sao lưu ở `~/Documents/derma-books-backup/`); khôi phục xong phải chụp lại snapshot và sinh lại câu hỏi.
- **Embedding và rerank qua OpenRouter không hoàn toàn tất định**: gọi lại không qua cache có thể lệch nhẹ điểm và thứ tự các chunk sát điểm.
- Bộ lọc "chép cụm" tính theo âm tiết (ngưỡng 8 âm tiết liên tiếp) vì tiếng Việt tách theo âm tiết; ngưỡng 4 từ của tiếng Anh loại oan nhiều câu có tên bệnh.

## Kiểm thử

```bash
cd core
.venv/bin/python -m unittest benchmark.retrieval.tests.test_metrics benchmark.retrieval.tests.test_pipeline
.venv/bin/python -m pyright agent benchmark/common benchmark/retrieval
```

`test_pipeline.py` kiểm tra `run_hybrid` / `rank_candidates` bằng các hàm giả truyền vào, không cần Qdrant hay LLM.
