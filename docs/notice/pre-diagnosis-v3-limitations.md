# Hạn chế và giải pháp tạm thời — tiền chẩn đoán v3

Ghi lại những gì **chưa làm đúng thiết kế**, **làm đơn giản hoá có chủ ý** hoặc **đo thật thấy yếu**, kèm cách tạm đang dùng và hướng sửa. Dùng cho mục "Hạn chế" của báo cáo. Giai đoạn theo kế hoạch triển khai v3 (1 nền tảng, 2 khối 0, 3 khối 1–4, 4 khối 5–6); hướng mở rộng ở `docs/pending/pre-diagnosis-v3-extensions.md`, cách hoạt động ở `docs/notice/agent-graph-versions.md`. Trong code, chỗ tạm đánh dấu `# shortcut:`.

Ký hiệu: ⚠ ảnh hưởng chất lượng kết quả · ⏳ chưa làm / chờ quyết định · 🔧 kỹ thuật, không ảnh hưởng người dùng.

---

## Giai đoạn 1 — Nền tảng (chọn version, state, StepRecorder)

| # | Hạn chế | Giải pháp tạm đang dùng | Hướng sửa |
|---|---|---|---|
| 1.1 | 🔧 Đổi version giữa chừng một hội thoại làm mất facts/bằng chứng đã tích luỹ của hội thoại đó | `diag` có `version`; khác version thì bỏ `diag` (có `logger.warning`), tin nhắn vẫn giữ. Checkpoint cũ không có `version` coi là v2 | Viết hàm chuyển `diag` v2 → v3 nếu cần giữ hội thoại cũ |
| 1.2 | ⚠ Mặc định đã là v3 nên khi chưa xong giai đoạn 4, chạy service cho câu trả lời chưa hoàn chỉnh | Đặt `AGENT_PRE_DIAGNOSIS_VERSION=v2` trong `.env` khi demo | Hết khi xong giai đoạn 4 |
| 1.3 | 🔧 State lưu dict thay vì Pydantic model (để checkpoint Postgres serialize được); mỗi node phải `model_validate` lại | Model chỉ dùng trong node, dict trong state | Chấp nhận |
| 1.4 | 🔧 StepRecorder ghi file jsonl có dữ liệu y tế; ghi đồng bộ trong callback | Chỉ bật khi đặt `AGENT_STEP_LOG_DIR`, để trong `/tmp/` của repo (đã gitignore); lỗi ghi chỉ warning | Ghi bất đồng bộ / vào DB khi cần đánh giá lớn |
| 1.5 | 🔧 `pyright` chưa cài trong venv `ai_service`, mirror PyPI timeout | Chạy bằng pyright của `archive/core/.venv` với `--pythonpath` | Thêm pyright vào dev dependency |

## Giai đoạn 2 — Khối 0: tiếp nhận và entity linking

| # | Hạn chế | Giải pháp tạm đang dùng | Hướng sửa |
|---|---|---|---|
| 2.1 | ⚠ Linking chỉ khớp chuỗi (chính xác / chứa chuỗi), chưa có FAISS SapBERT. Đo 1 ca: 2–3/7 fact khớp node | `extract_slots` điền luôn `text_en` (tên y khoa tiếng Anh) để tra; mention không khớp chính xác thì 1 lượt LLM chọn trong ≤ 6 ứng viên | FAISS SapBERT đa ngôn ngữ (doc khối 0) |
| 2.2 | ⚠ `rapidfuzz` chưa cài nên điểm khớp tên dùng `difflib` | Điểm chứa chuỗi = 0.6 × độ giống tên (`difflib`) để so top-1/top-2 vẫn có nghĩa | Cài `rapidfuzz` nếu cần nhanh hơn |
| 2.3 | ⚠ Dưới ngưỡng thì giữ chữ (NIL), chưa link lên node cha `IS_A` | Fact NIL vẫn dùng được ở RAG và khớp chữ trong bảng bằng chứng (×0.5) | Truy vấn cha trong knowledge |
| 2.4 | ⚠ Kết quả link khác nhau giữa các lần chạy (LLM): cùng câu "mảng đỏ" lần khớp `Erythematous plaque`, lần không | Cache theo `(text_en, slot)` trong RAM nên trong một process kết quả ổn định | Cache Redis; temperature 0 cho bước link |
| 2.5 | 🔧 Cache link nằm trong RAM process, không giới hạn, mất khi restart | Chấp nhận cho đồ án | Redis nếu chạy nhiều worker |
| 2.6 | ⚠ Ngưỡng chất lượng ảnh (cạnh < 200px, phương sai Laplace < 20) chọn tay, chưa đo trên ảnh thật | Ảnh bị loại thì báo lý do ở bước lập luận (`image_issues`) | Đo trên tập ảnh SkinCaRe |
| 2.7 | ⚠ VLM trả JSON trong văn bản (model local có thể không gọi hàm); JSON hỏng thì bỏ ảnh đó | `logger.warning`, CNN vẫn chạy | Đổi model ảnh có function calling |
| 2.8 | ⚠ Bảng 22 lớp CNN → bệnh map tay; 4 lớp `null` (DrugEruption, Infestations_Bites, Vitiligo, Unknown_Normal), 2 lớp gần đúng (Benign_tumors, Moles) | Lớp `null` không vào xếp hạng, vẫn hiện ở bước lập luận | Người rà lại bảng |
| 2.9 | ⚠ Mâu thuẫn ảnh/lời kể chỉ phát hiện ở slot `color`/`morphology` (node khác nhau) và khi một bên có / một bên không | Đánh dấu `conflict`, khối 4 ưu tiên hỏi lại | Mở rộng khi có dữ liệu |
| 2.10 | 🔧 Fact lịch sử: chỉ đọc ở lượt đầu; v3 **chưa ghi** fact mới vào graph theo dõi bệnh nhân (v2 có ghi) | `ctx.turn_facts` để trống | ⏳ Chờ quyết định câu hỏi mở 3 |
| 2.11 | 🔧 `provenance` là id tin nhắn LangGraph, không phải id DB | Giống v2 | Đổi khi cần truy vết về DB |
| 2.12 | ⚠ Lượt có ảnh chậm hơn vì VLM nằm trên đường găng của `intake` (10–17 s đo ở v2) | VLM chạy song song với trích chữ và CNN | Chấp nhận |

## Giai đoạn 3 — Khối 1–4: giả thuyết, tìm thông tin, bằng chứng, kiểm tra

| # | Hạn chế | Giải pháp tạm đang dùng | Hướng sửa |
|---|---|---|---|
| 3.1 | ⚠ **KG thưa và lệch**: psoriasis chỉ có 30 cạnh phenotype (toàn từ sách, phần lớn mô bệnh học), không có cạnh PrimeKG. KG xếp bệnh hiếm khớp 2 triệu chứng chung lên đầu; ca vảy nến kinh điển: psoriasis hạng 7/7 | Dùng cả cạnh KG + DOC; bệnh `propose_more` (LLM) luôn được giữ ngoài top 6 | ⏳ Chốt lại trọng số (tăng RAG/CNN); bổ sung cạnh phenotype lâm sàng |
| 3.2 | ⚠ Trọng số `kg 0.4 / cnn 0.3 / rag 0.2 / history 0.1`, `DELTA 0.15`, `MAX_ROUNDS 3` chọn tay | Hằng số một chỗ (`fuse_scores.py`, `check_stop.py`) | ⏳ Tune trên tập validation |
| 3.3 | ⚠ Chưa có PPR / PCST (doc khối 1–2) | Dùng truy vấn xếp hạng có sẵn: trọng số đặc hiệu `3 / ln(2 + degree)`, trừ 2 điểm mỗi triệu chứng bị phủ định | PPR trên đồ thị con lọc metapath |
| 3.4 | ⚠ `primary_disease_ids` theo tiêu đề chỉ phủ **2.2%** chunk (mục lục sách chỉ tới mức chương) | Khối 2 lọc theo `mentioned_disease_ids` (bệnh được nhắc trong đoạn, phủ 77.8%) — đoạn có thể chỉ nhắc qua bệnh, không phải chủ đề chính | Chunk lại theo mục bệnh; gắn id bằng LLM theo nội dung |
| 3.5 | ⚠ Sách tiếng Việt (Bộ Y tế) không gắn được disease id (tên bệnh trong đồ thị là tiếng Anh) | Không có | Dịch tiêu đề / dùng DermO tiếng Việt |
| 3.6 | 🔧 Chunk nạp sau khi chạy script không có `primary/mentioned_disease_ids` | Chạy lại `make tag-chunk-diseases` sau mỗi lần index sách | Gắn vào stage `index` của pipeline |
| 3.7 | ⚠ Tên bệnh nhóm ("dermatitis", "carcinoma"...) bị bỏ khi gắn `mentioned` bằng danh sách tay | `GENERIC_NAMES` trong script | Lọc theo cấp trong ontology |
| 3.8 | ⚠ Câu hỏi phân biệt lấy từ phenotype HPO, nhiều node không hỏi bệnh nhân được (di truyền, mô bệnh học, xét nghiệm) | `is_askable` lọc bằng từ khoá; vẫn có thể lọt (vd "Infantile onset") | Danh sách phenotype "hỏi được" do bác sĩ chọn |
| 3.9 | ⚠ Bảng bằng chứng: fact chưa có node khớp chữ với tên phenotype, trọng số ×0.5; chưa khớp cha/con `IS_A` | `TEXT_MATCH_FACTOR` | Khớp theo ontology |
| 3.10 | ⚠ `annotate_guideline`: kiểm được câu trích có thật trong đoạn, **không kiểm được** câu đó có thật sự ủng hộ bệnh đang xét (đo thật thấy LLM gắn "ủng hộ" cho câu chỉ liên quan lỏng lẻo) | Bỏ mục có `chunk_id` lạ / câu trích không có nguyên văn | Chấm lại bằng cross-encoder hoặc bác sĩ duyệt mẫu |
| 3.11 | ⚠ **Red flag là luật tay, chưa có bác sĩ duyệt** (`data/v3/red_flags.json`); khớp nhóm triệu chứng bằng từ khoá | Mức `urgent` thì kết luận ngay, dặn đi khám | ⏳ Bác sĩ duyệt |
| 3.12 | 🔧 Red flag lưu JSON thay yaml (plan) vì `pyyaml` chưa khai báo dependency | — | Chấp nhận |
| 3.13 | ⚠ Bệnh chỉ đến từ RAG chưa có tên ở bước `hypothesize` (hiện `disease:5083`) | `retrieve` điền tên từ hồ sơ bệnh | Lấy tên ngay khi gom điểm RAG |
| 3.14 | 🔧 Mỗi lượt khối 0–4 + trả lời ~50–60 s với Gemma qua OpenRouter | Cache hồ sơ/chunk/annotate theo bệnh trong diag | Đo lại khi tự host vLLM |
| 3.15 | ⚠ Câu hỏi phân biệt lạc đề (đo thật: hỏi người bệnh vảy nến về "khả năng học tập, giao tiếp" — phenotype của bệnh hiếm do KG đưa lên) | `is_askable` thêm từ khoá thần kinh / phát triển / bẩm sinh | Như 3.8; giảm bệnh hiếm ở 3.1 |

## Việc chờ quyết định (gom lại)

1. Trọng số `w1..w4`, `DELTA`, `MAX_ROUNDS` (3.1, 3.2).
2. Người duyệt red flag (3.11) và bảng map CNN (2.8).
3. Có ghi fact v3 vào graph theo dõi bệnh nhân không (2.10).
4. Kiểm tay 50 chunk mẫu `tmp/tag_sample.csv` (3.4).

## Giai đoạn 4 — Khối 5–6: hỏi thêm, kết luận, chạy thật

| # | Hạn chế | Giải pháp tạm đang dùng | Hướng sửa |
|---|---|---|---|
| 4.1 | ⚠ **Kết luận sớm sai bệnh** khi KG đẩy bệnh hiếm lên: ca vảy nến, sau 1 câu hỏi `check` dừng vì pityriasis rubra pilaris hơn psoriasis 0.26 điểm (≥ `DELTA` 0.15) | Bác sĩ vẫn thấy cả danh sách xếp hạng; người bệnh chỉ nhận lời dặn đi khám, không nhận tên bệnh | ⏳ Chốt trọng số (3.1); dừng chỉ khi top-1 có ít nhất N dấu hiệu khớp |
| 4.2 | ⚠ `verify_claims` loại hết bệnh khi LLM trích sai mã (đo: 1/3 lượt kết luận ra danh sách rỗng, lượt sau cùng ca lại đúng) | Phần cho bác sĩ rỗng nhưng câu trả lời người bệnh vẫn có ("cần bác sĩ khám trực tiếp"); lý do ghi ở bước lập luận | Gọi lại `reason_cot` một lần khi mọi bệnh bị loại; cho LLM chọn mã từ danh sách đóng |
| 4.3 | ⚠ Kiểm được "ý có trích mã hợp lệ", **không kiểm được** mã đó thật sự ủng hộ ý (đo: LLM trích "Fever" làm căn cứ cho cả SJS lẫn DRESS) | — | Bác sĩ duyệt mẫu; chấm bằng LLM khác |
| 4.4 | 🔧 Tách `reason_cot` (cho bác sĩ) và câu trả lời người bệnh thành 2 lượt LLM (dễ chấm, chậm hơn gộp ~1 lượt); `reason` 7–30 s | Node `reason` riêng trước `answer`, chỉ `answer` stream token | Gộp nếu cần nhanh hơn |
| 4.5 | ⚠ Người bệnh **không** được nghe tên bệnh nào (theo doc); có thể thấy "vô ích" | Tên bệnh không đưa vào ngữ cảnh của `answer`; giả thuyết chỉ gửi tab bác sĩ qua `turn_hypotheses` | Quyết định sản phẩm |
| 4.6 | 🔧 Report cho bác sĩ đi qua đường v2 sẵn có (`ctx.turn_hypotheses` → clinical `apply_turn`); **chưa** ghi `consultation_report` / `clinical_fact_provenance` | Định dạng giống v2 (`disease, code, body_site, confidence, missing, evidence`); `evidence.ref` là node id / chunk_id | Endpoint provenance ở clinical (đụng `dto/base` → hỏi duyệt) |
| 4.7 | 🔧 Giả thuyết không có `body_site` hợp lệ và hội thoại chưa có đợt bệnh nào thì clinical bỏ qua (giống v2) | LLM chọn `body_site` theo danh sách mã | — |
| 4.8 | ⚠ `code` (22 lớp CNN) suy từ tên bệnh qua bảng tên tay của v2 (`canon`); bệnh ngoài 22 lớp ra `OTHER` | Dùng lại `normalize_code` | Map theo `cnn_to_disease.json` ngược lại |
| 4.9 | ⚠ `vlm_verify` gọi cho mọi câu hỏi "discriminate/missing" khi lượt có ảnh, không biết trước phenotype có nhìn thấy được không | Prompt yêu cầu `unclear` khi không thấy được; tối đa 1 lần/lượt; chỉ ảnh của lượt hiện tại | Danh sách phenotype nhìn thấy được |
| 4.10 | 🔧 Chưa chạy qua worker + RabbitMQ + FE, chưa có ca có ảnh thật (cần ảnh trong MinIO) | Chạy graph trực tiếp với model + Neo4j + Qdrant thật, knowledge tạm ở cổng khác | ⏳ Chạy trên FE |
| 4.11 | 🔧 StepRecorder ghi 2 dòng `pre_diagnosis` mỗi lượt (node chat graph và subgraph cùng tên) | Bỏ qua khi đọc | Lọc theo namespace |

**Số đo chạy thật (2026-11-14, Gemma 4 26B qua OpenRouter, chưa có ảnh):**

| Ca / lượt | Kết quả | Thời gian | Lượt LLM |
|---|---|---|---|
| Vảy nến lượt 1 | hỏi thêm | 23 s | 6 |
| Vảy nến lượt 2 | kết luận | 37 s | 5 |
| Vảy nến lượt 3 | kết luận (cache) | 65 s | 3 (`intake` 29 s, `reason` 30 s do API chậm) |
| Red flag (allopurinol + sốt + loét miệng + bọng nước) | kết luận khẩn cấp, câu đầu khuyên đi cấp cứu; SJS đứng đầu phần cho bác sĩ | 40 s | 5 |

So với ước lượng của doc (lượt đầu 12–18 s, hỏi tiếp 5–8 s, kết luận 30–45 s, giả định tự host vLLM): chậm hơn ở lượt hỏi, gần đúng ở lượt kết luận. Độ trễ API dao động mạnh nên số giây chưa đủ tin.
