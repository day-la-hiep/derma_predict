# Cơ chế lập luận da liễu của agent (v2)

> **Phiên bản v2**, tra soát theo code ngày 2026-11-14. Phản ánh: graph tiền chẩn đoán `prepare_turn → text_flow ∥ image_flow`, graph fact bệnh nhân 5 nhóm (Neo4j `Pt*`), `hybrid_retrieval` 3 nhánh, và việc đã bỏ memory dài hạn của agent. Đổi một trong các phần này thì cập nhật tài liệu và tăng phiên bản.

Kết quả của hệ thống là **gợi ý hỗ trợ, không phải chẩn đoán y khoa**. Mỗi thành phần dưới đây trình bày theo bốn mục: **Vấn đề** nó giải quyết, **Cơ chế**, **Dùng gì**, **Hạn chế**. Điểm dễ nhầm chi tiết hơn nằm ở `docs/notice/` (`patient-fact-graph.md`, `agent-graph-versions.md`, `finalize-report.md`).

Mục lục: 1 Tổng quan · 2 Kho dữ liệu · 3 Điều phối lượt · 4 Nguyên tắc bằng chứng · 5 Các node làn chữ · 6 Công cụ tra cứu · 7 Làn ảnh · 8 Graph fact bệnh nhân · 9 Clinical và vòng kín · 10 Nạp tri thức (pipeline sách) · 11 Hạn chế chung · 12 Phạm vi tra soát

---

## 1. Tổng quan một lượt

```
FE ─▶ consultation (ghi tin) ─▶ ai_service POST /internal/turns (202, chạy nền)
        ▼
  build_context ── hồ sơ, fact + tổn thương hiện hành (knowledge), ảnh đính kèm
        ▼
  chat_graph:  triage ──(answer)──▶ trả lời ngắn, hết lượt
                  └──(diagnose)──▶ pre_diagnosis
                      prepare_turn ─┬─▶ text_flow  (luôn chạy)
                                    └─▶ image_flow (chỉ khi có ảnh, song song)
        ▼
  finish_turn: (1) emit "message.done" + sentinel vào Redis Stream của hội thoại
               (2) save_turn_facts → knowledge (graph Pt*)
               (3) apply_turn → clinical (giả thuyết + kết quả ảnh)
               (4) post_turn_result → consultation (câu trả lời + các bước lập luận)
```

Trong lúc chạy, `ai_service` ghi sự kiện (`message.started`, `message.delta`, các bước tra cứu) vào **Redis Stream** `CONVERSATION_EVENTS_STREAM`; consultation đọc ra SSE cho FE. Token chỉ được stream từ node `answer`; câu trả lời của `triage` phát một lần.

---

## 2. Kho dữ liệu

| Kho | Nội dung | Ghi | Đọc |
|---|---|---|---|
| Postgres `consultation` | hội thoại, tin nhắn, kết quả lượt | consultation | consultation, ai (API) |
| Postgres `clinical` | đợt bệnh, giả thuyết, ảnh, lịch hẹn, lần khám, báo cáo kết luận + `snapshot` | clinical | clinical, FE bác sĩ |
| Postgres `ai`, schema `langgraph` | checkpoint hội thoại của agent (`AsyncPostgresSaver`) | ai | ai |
| Qdrant `derma_document_chunks_v4` | chunk sách (dense + sparse BM25) | knowledge (pipeline) | `hybrid_retrieval`, `semantic_search`, `keyword_search` |
| Qdrant `derma_finalize_reports` | báo cáo kết luận đã chốt (dense + sparse) | knowledge (`/cases`) | `search_finalize_report` |
| Neo4j nền | PrimeKG, DermO (cạnh `source=KG`), cạnh trích từ sách (`source=DOC`) | knowledge | `knowledge_graph_query`, `query_document_graph`, mở rộng fact |
| Neo4j `Pt*` | graph theo dõi fact bệnh nhân (`PtLesion`, `PtLiteral`, quan hệ `PT_*`) | knowledge | ai, clinical, identity |
| Neo4j journey | `Patient–HAD_SESSION→ConsultationSession–REPORTED_FACT→ClinicalFact…` dựng từ báo cáo đã chốt | knowledge | màn bác sĩ (journey graph, history hints); **agent chat không dùng** |
| MinIO | PDF sách, ảnh đính kèm | knowledge, consultation | knowledge, ai (ảnh) |

Quy ước: **dữ liệu lâm sàng sống ở graph `Pt*`; dữ liệu đã chốt ở Postgres dưới dạng snapshot**. Postgres `langgraph` chỉ còn checkpoint (store memory đã drop).

Mô hình: `AGENT_MODEL` mặc định `gemma-4-26b` qua OpenRouter (chọn được `deepseek-v4-pro` / `deepseek-v4-flash` theo hội thoại); reranker `qwen3-reranker-8b` qua OpenRouter; CNN ảnh `AdaptiveCNN_SkinDisease_v5_best.pth`; model mô tả ảnh `AGENT_VISION_MODEL` (mặc định rỗng = tắt).

---

## 3. Điều phối lượt (`turn.py`, `chat_graph.py`, `triage`)

### 3.1 `build_context`
- **Vấn đề:** agent cần biết người bệnh là ai và đã ghi nhận gì mà không giữ dữ liệu riêng.
- **Cơ chế:** lấy hội thoại từ consultation (hồ sơ `patient_profile_id`, model đã chọn), fact + tổn thương hiện hành từ knowledge, danh sách ảnh (`content_type` image). Tạo `AgentContext`.
- **Dùng gì:** `ConsultationClient`, `KnowledgeClient` (`GET /internal/patient-facts/{id}`).
- **Hạn chế:** knowledge lỗi thì chạy tiếp **không có fact** (chỉ log warning), nên lượt đó thiếu dị ứng / tiền sử trong prompt.

### 3.2 `triage`
- **Vấn đề:** chào hỏi, hỏi xã giao, ngoài phạm vi không đáng chạy cả graph (mỗi vòng tra cứu 30-60 giây).
- **Cơ chế:** một lần gọi LLM (`TriageDecision`: `route` = `answer` | `diagnose`, `reply`). Tin cuối không phải `HumanMessage` hoặc có dấu `[Ảnh đính kèm]` thì đi thẳng `diagnose` mà không gọi LLM. `AGENT_TRIAGE_ENABLED=false` thì bỏ node.
- **Dùng gì:** `AGENT_TRIAGE_MODEL` (rỗng thì dùng model của hội thoại), 6 tin gần nhất cắt 300 ký tự.
- **Hạn chế:** lỗi hoặc `reply` rỗng thì mặc định `diagnose` (an toàn nhưng tốn thời gian). Triage là LLM nhỏ nên có thể phân loại sai tin ngắn tiếp nối ("vâng"); prompt đã dặn nghi ngờ thì `diagnose`.

### 3.3 Lưu trạng thái giữa các lượt
- **Cơ chế:** `_pre_diagnosis_node` chỉ giữ lại các khoá `facts`, `facts_upto`, `plan`, `unsupported`, `evidence`, `evidence_status`, `done_calls`, `call_results` vào `diag` của chat graph; checkpoint lưu ở Postgres.
- **Hạn chế:** `queries`, `rounds`, `next` không lưu (mỗi lượt lập lại). Mã E#/H# lưu trong `evidence` nên giữ nguyên số thứ tự qua các lượt, nhưng `evidence` chỉ tăng, không dọn. Lỗi cả lượt thì `finish_turn` trả `_ERROR_TEXT` với status `done` (không thêm status `error` để khỏi đổi DTO/FE).

---

## 4. Nguyên tắc bằng chứng (lõi lập luận)

- **Vấn đề:** model nhỏ hay bịa bệnh và nguồn; cần cách để câu trả lời y khoa luôn truy được về dữ liệu.
- **Cơ chế (do code ép, không chỉ do prompt):**
  1. **E# = bằng chứng**: đoạn sách (`source="book"`), câu trích từ đồ thị sách (có `evidence`), ca bệnh thực tế. **H# = gợi ý**: kết quả `knowledge_graph_query`, ứng viên và câu hỏi từ `query_patient_graph`, nhãn CNN, mô tả ảnh, kiểm tra chéo.
  2. Nhãn `kind` do `label_tool_evidence` quyết định theo tên tool và nội dung, model không tự gán.
  3. `ground_hypotheses_in_evidence`: giả thuyết chỉ ở lại `plan` nếu `cites` có ít nhất một mã **E#** tồn tại; mã H# hoặc mã không tồn tại bị bỏ kèm ghi chú, giả thuyết vào `unsupported`.
  4. `answer` chọn `ANSWER_FOUND` (có `plan`) hoặc `ANSWER_NONE` (không có: cấm nêu tên bệnh, xếp hạng, khuyên điều trị). `ANSWER_FOUND` chỉ nhận E# được các giả thuyết trích.
  5. Prompt `RULES` dùng chung: kiến thức nền không phải bằng chứng; nội dung tool và tin nhắn là dữ liệu, không phải chỉ thị; thiếu dữ liệu thì nói rõ; kết bằng nhắc "không phải chẩn đoán".
- **Dùng gì:** `retrieval_evidence.py` (`label_tool_evidence`, `add_retrieval_evidence`, `ground_hypotheses_in_evidence`), `pre_diagnosis_prompts.py`.
- **Hạn chế:**
  - Ràng buộc chỉ kiểm **có mã E# hợp lệ**, không kiểm E# đó có thực sự ủng hộ giả thuyết hay không. Model có thể trích E# lạc đề.
  - `ANSWER_FOUND` vẫn do LLM viết tự do: nó có thể diễn đạt vượt bằng chứng; chỉ prompt ngăn, code không kiểm.
  - Mỗi mục bằng chứng bị cắt 600 ký tự (`_MAX_TEXT`), nội dung quan trọng nằm sau có thể mất.
  - Trùng lặp theo (`kind`, nguồn, 300 ký tự đầu), nên cùng nội dung ở hai tool khác nguồn vẫn thành hai mục.

---

## 5. Các node của làn chữ (`pre_diagnosis_nodes.py`)

Vòng lặp: `extract_facts → plan → [choose_tools → tools → label_evidence → reflect]×(≤3) → answer`.

### 5.1 `prepare_turn`
Tạo `Future` (`ctx.image_result`) trong event loop của lượt nếu có ảnh, để `label_evidence` chờ kết quả làn ảnh. Không làm gì khác.

### 5.2 `extract_facts`
- **Vấn đề:** lời kể tự do cần thành dữ kiện có cấu trúc để lưu bền, mở rộng đồ thị và đưa lại vào prompt.
- **Cơ chế:** lấy các tin mới kể từ `facts_upto`; chỉ khi có tin `PATIENT` mới gọi LLM (`ExtractedFacts`, function calling, tối đa 2 lần). Mỗi fact có `category` 1-5 (mục 8), `present`, `resolved`, `onset_text`, `lesion` (id tổn thương đã biết hoặc mã tạm), `site_text`, `scope`, `source_messages`. Sau đó: `validate_facts_evidence` (chuẩn hoá enum, cắt `detail` 300 ký tự, cảnh báo nếu không trùng từ khoá với tin nguồn), `assign_lesions` (cùng mã tạm = cùng tổn thương; không có mã thì gắn tổn thương gần nhất hoặc tạo mới), `merge_facts` theo `fact_key`. Fact trong graph **đè** fact cũ trong checkpoint.
- **Dùng gì:** `patient_fact_extractor.py`; `known_facts`/`known_lesions` từ graph; model của hội thoại.
- **Hạn chế:** lỗi hai lần thì **bỏ qua bước trích**, giữ nguyên fact đã biết (log warning), lượt đó không ghi fact mới. Chỉ giữ tối đa 30 fact mới nhất trong state (`MAX_FACTS`); graph vẫn giữ đủ. Kiểm tra nguồn chỉ cảnh báo, không loại fact. Chất lượng chọn nhóm của model nhỏ dưới prompt 5 nhóm chưa kiểm chứng với model thật.

### 5.3 `plan`
- **Vấn đề:** tránh tra cứu mù; chỉ tra điều còn thiếu.
- **Cơ chế:** LLM (`PlanInput`) nêu ≤4 giả thuyết (chỉ để chọn cái cần tra, **chưa phải kết luận**) và ≤4 truy vấn. Bối cảnh gồm hồ sơ lâm sàng (fact + fact từ ảnh), giả thuyết đã có căn cứ ở lượt trước, các lệnh đã gọi kèm kết quả, bằng chứng đã có. **Truy vấn rỗng thì đi thẳng `answer`.** Đặt `rounds=0`.
- **Dùng gì:** `PLAN_SYSTEM`, `invoke_structured_with_retry` (retry khi model viết chữ thay vì gọi hàm).
- **Hạn chế:** khi `plan` rỗng truy vấn, `reflect` **không chạy**, nên lượt đó không có giả thuyết mới gửi về clinical, và `answer` dùng `plan` của các lượt trước. Lượt đầu `plan` không thấy ảnh (kết quả ảnh chỉ vào từ `label_evidence`).

### 5.4 `choose_tools` và `tools`
- **Vấn đề:** để model tự quyết gọi tool thì chậm và hay lặp.
- **Cơ chế:** model bind toàn bộ tool với `tool_choice="any"`, gọi **song song** nhiều tool khác loại trong một vòng. Lệnh trùng khoá (`tên + args`) với lệnh đã gọi bị bỏ; riêng `query_patient_graph` khoá kèm dấu vết bộ fact (`get_facts_fingerprint`) nên gọi lại được khi fact đổi. Không chọn được tool sau 3 lần thử thì sang `reflect`. `ToolNode` bắt lỗi tool và trả chuỗi lỗi thay vì ném.
- **Dùng gì:** `pre_diagnosis_tool_registry.build_tools` (mục 6).
- **Hạn chế:** `gemma-4-26b` qua OpenRouter hay bỏ qua `tool_choice` (thử 6 lần cùng lúc thì khoảng một nửa không gọi hàm), nên cần retry. Mọi lệnh trùng thì vòng đó coi như không tra cứu.

### 5.5 `label_evidence`
- **Vấn đề:** gom kết quả rời rạc thành một sổ bằng chứng có mã.
- **Cơ chế:** (1) chờ làn ảnh (một lần mỗi lượt) và thêm các hint ảnh; (2) với kết quả tool của vòng vừa chạy (`new_calls > 0`), `label_tool_evidence` tách thành mục `{kind, source, text, ref?}`, `add_retrieval_evidence` cấp mã E#/H#, ghi `call_results` ("lệnh → n mục, m mới"); (3) `evidence_status = found` nếu có ít nhất một E#.
- **Hạn chế:** `ref` (document_id, chunk_id, trang) chỉ có với đoạn sách; kết quả KG và ca bệnh không có nên FE không mở được nguồn.

### 5.6 `reflect`
- **Vấn đề:** quyết định đã đủ căn cứ để trả lời hay cần tra tiếp; biến giả thuyết thành kết quả lưu được.
- **Cơ chế:** LLM (`ReflectInput`) viết lại **toàn bộ** giả thuyết, mỗi cái có `cites` (E#), `confidence` (cao/vừa/thấp), `code` (một trong 22 nhóm bệnh của CNN hoặc `OTHER`, chuẩn hoá bởi `normalize_code`), `body_site`, `missing`, rồi chọn `next` = `retrieve` | `answer`. Sau đó áp `ground_hypotheses_in_evidence`. Hết `MAX_TOOL_ROUNDS = 3` vòng thì **ép `answer`**. Bản giả thuyết của lần `reflect` cuối được lưu vào `ctx.turn_hypotheses` (kèm nội dung bằng chứng cắt 500 ký tự) để gửi về clinical.
- **Dùng gì:** `REFLECT_SYSTEM`, `clinical_codes.py`.
- **Hạn chế:** trần 3 vòng là ràng buộc cứng vì model nhỏ cứ chọn tra tiếp (mỗi vòng 30-60 giây). `code` và `body_site` do model điền rồi chuẩn hoá; không khớp thì `OTHER`/rỗng. Đây là phần sau này clinical dùng để mở đợt theo vùng nên sai vùng kéo theo sai đợt.

### 5.7 `answer`
Gọi model chính (stream token), prompt `ANSWER_FOUND` hoặc `ANSWER_NONE`, ngữ cảnh là hồ sơ lâm sàng + giả thuyết + chỉ các E# được trích. Không bind tool.
- **Hạn chế:** không có câu trả lời mẫu cố định khi vi phạm ràng buộc; chỉ có prompt và grounding ở bước trước.

---

## 6. Công cụ tra cứu (`ai_service/app/tools/`)

### 6.1 `hybrid_retrieval` (mặc định cho câu chung chung)
- **Vấn đề:** tra sách bằng một cách tìm thì bỏ sót: embedding tệ với tên thuốc / mã, BM25 tệ với câu diễn đạt tự nhiên và khác ngôn ngữ.
- **Cơ chế (`run_hybrid`):**
  1. **Trích thực thể** bằng LLM (`extract_entities`): bệnh/triệu chứng/thuốc, tên Anh chuẩn + tên Việt.
  2. Ba nhánh **song song**, mỗi nhánh lấy 20 chunk: **semantic** (embedding câu hỏi, dense trên Qdrant), **BM25** (câu hỏi cộng tên Anh + Việt của thực thể, sparse trên Qdrant), **graph** (knowledge `/search/graph`: chunk mà cạnh `DOC` của các thực thể trỏ tới; rỗng nếu không có thực thể y khoa).
  3. Trộn **RRF** (`k=60`), khử trùng theo `chunk_id`, giữ 20 ứng viên; chunk do graph đề xuất gắn `via_graph=true`.
  4. **Rerank** (`qwen3-reranker-8b`, mỗi đoạn cắt 3000 ký tự), trả `top_k` (≤10). Không rerank được thì giữ thứ tự RRF và `ranked_by="rrf"`.
  5. Nhánh nào lỗi chỉ thêm ghi chú vào `notes`, các nhánh còn lại vẫn trả kết quả.
- **Dùng gì:** `pipeline.py`, `fusion.py`, `corpus.py`; knowledge `/search/semantic`, `/search/bm25`, `/search/graph`.
- **Hạn chế:** thêm một lần gọi LLM (trích thực thể) cho mỗi lần tra; lỗi thì BM25 dùng query gốc (có ghi chú). Dense bỏ qua collection lệch số chiều với embedding hiện tại. Nhánh graph phụ thuộc đồ thị sách đã duyệt và độ phủ từ điển khớp nút. Điểm `score` là độ liên quan, không phải xác suất chẩn đoán. Docstring của tool (prompt cho LLM) hiện chỉ nói "ngữ nghĩa + từ khoá", chưa nhắc nhánh graph.

### 6.2 `semantic_search`, `keyword_search`
Chỉ một nhánh (embedding hoặc BM25) khi agent biết chính xác loại cần. Kết quả cũng là E# (đoạn sách). *Chưa tra soát sâu nội dung hai hàm này ngoài docstring.*

### 6.3 `knowledge_graph_query`
- **Vấn đề:** cần quan hệ bệnh–triệu chứng–thuốc có cấu trúc mà văn bản sách khó cho.
- **Cơ chế:** 8 `intent` (`disease_overview`, `symptoms_of_disease`, `diseases_with_symptom`, `differential`, `treatments`, `contraindications`, `drug_profile`, `red_flags_risk`), mỗi intent một truy vấn Cypher trên đúng nhóm quan hệ. Thực thể được khớp tên (exact, rồi LLM dịch), bệnh được mở rộng sang nút DermO/MONDO tương ứng; kết quả sắp theo ưu tiên quan hệ, ghi chú những tên không có trong đồ thị.
- **Dùng gì:** PrimeKG + DermO (+ hồ sơ BYT), `kg_intent_service.py`; chỉ cạnh theo `KG_EDGE_SOURCES` (mặc định `["KG"]`, **không gồm cạnh sách**).
- **Hạn chế:** kết quả luôn là **H#** (`source="kg"`), không bao giờ là bằng chứng. Dữ liệu gốc tiếng Anh nên tên tiếng Việt phải qua LLM dịch (có thể sai, báo trong `llm_translated`). Đồ thị thưa với bệnh da liễu hiếm/đặc thù Việt Nam.

### 6.4 `query_document_graph`
- **Vấn đề:** quan hệ giữa bệnh/thuốc/triệu chứng viết trong sách mà PrimeKG không có.
- **Cơ chế:** truy vấn triple `source=DOC` theo `entity` (và `relation` tuỳ chọn), trả kèm câu trích gốc và trang. Chỉ triple **có câu trích** mới thành E# (nguồn "đồ thị sách, trang N").
- **Dùng gì:** đồ thị dựng bởi pipeline sách (mục 10), `DocumentGraphService`.
- **Hạn chế:** chất lượng phụ thuộc bước trích triple bằng LLM và người duyệt; entity phải là tên tiếng Anh y khoa.

### 6.5 `search_finalize_report`
- **Vấn đề:** đối chiếu với ca thực tế đã được bác sĩ chốt, kèm lập luận và hướng xử trí.
- **Cơ chế:** `run_hybrid` trên corpus báo cáo (semantic + BM25 + rerank; **không có nhánh graph** vì `graph_search` chỉ chạy cho corpus sách). Mỗi ca trả chẩn đoán, dữ kiện, mô tả của bác sĩ, lập luận, dặn dò, ảnh (URL ký). Tối đa 5 ca. Kết quả thành E# ("ca bệnh thực tế"). Văn bản đánh chỉ mục đã bỏ họ tên và số điện thoại.
- **Dùng gì:** Qdrant `derma_finalize_reports`; bật/tắt bằng `AGENT_FINALIZE_REPORT_SEARCH_ENABLED`.
- **Hạn chế:** kho chỉ gồm ca đã chốt nên nhỏ và lệch theo bệnh viện; ca là ý kiến một bác sĩ nhưng được tính như bằng chứng. Ca chưa chốt hoặc chốt lỗi (knowledge lỗi lúc nạp) thì không có trong kho cho tới khi reindex.

### 6.6 `query_patient_graph`
Mở rộng từ fact của chính người bệnh (cơ chế ở mục 8.3). Ứng viên, câu hỏi, ghi chú thuốc là H#; câu trích sách là E#.

---

## 7. Làn ảnh (`skin_image_nodes.py`, `tools/skin_image/`)

- **Vấn đề:** ảnh cho thông tin mà lời kể không có; nhưng ảnh không được ép kết luận, và không được tác động ngược lên lời kể.
- **Cơ chế:** tối đa 3 ảnh, tải từ MinIO. `image_cnn` (CNN top-5 mỗi ảnh, chạy trong thread vì torch đồng bộ) và `image_vision` (model đa phương thức, ảnh thu về JPEG ≤1024px, trả 4 mục: hình thái, phân bố, giả thuyết, dấu hiệu lưu ý) chạy song song; `image_done` gom vào `ctx.image_result`. Làn ảnh dùng `SkinImageState` **không có `messages`/`facts`** nên không thấy lời người bệnh; làn chữ không thấy ảnh. Tại `label_evidence`: nhãn CNN và mô tả thành **H#**; `cross_check` so nhãn CNN (gộp theo bệnh, lấy top 3) và mô tả với giả thuyết của làn chữ qua bảng alias, ghi một hint "trùng / chỉ ảnh gợi ý / chỉ mô tả gợi ý". Kết quả CNN theo từng ảnh (`storage_key`, nhãn, điểm) gửi về clinical để gắn đợt bệnh.
- **Dùng gì:** CNN AdaptiveCNN v5 (22 lớp, `Unknown_Normal` là một lớp), `AGENT_VISION_MODEL`, subgraph LangGraph để hai làn không chặn nhau.
- **Hạn chế:**
  - Lỗi từng bước chỉ `logger.warning` rồi bỏ qua (thiếu checkpoint, ảnh hỏng, vision lỗi); lượt vẫn chạy không có ảnh.
  - `AGENT_VISION_MODEL` mặc định rỗng nên mặc định chỉ có CNN.
  - CNN phân loại **tập đóng 22 lớp**: bệnh ngoài tập vẫn bị gán nhãn gần nhất; độ tin cậy không phải xác suất lâm sàng. Chưa cắt vùng tổn thương trước khi cho CNN (`docs/pending/`).
  - `cross_check` dựa bảng alias viết tay: tên bệnh ngoài bảng chỉ so theo chuỗi; không có giả thuyết từ làn chữ thì không so.
  - `plan` và `choose_tools` vòng đầu không thấy ảnh; `label_evidence` chờ làn ảnh nên lượt chậm đúng phần vision dài hơn. Lượt mà `plan` không có truy vấn vẫn chờ làn ảnh xong nhưng kết quả không được dùng.
  - Tra ca bệnh theo nhãn CNN (`search_finalize_report_by_image`) đang **tắt** (`SEARCH_CASES_BY_LABEL = False`).

---

## 8. Graph fact bệnh nhân (`Pt*`) và mở rộng

### 8.1 Mô hình (5 nhóm)

| Nhóm | Nội dung | Cạnh | Ghi chú |
|---|---|---|---|
| 1 | triệu chứng | `PT_HAS_SYMPTOM` | `present=false` cho "không ngứa" |
| 2 | tổn thương | `PT_HAS_MORPHOLOGY` | `kind` = primary / secondary |
| 3 | đặc điểm | `PT_HAS_ATTRIBUTE` | đơn trị theo `name` (`location`, `distribution`, `arrangement`, `course`, tên tự do); `location` ghi vào `PtLesion.site_text`, không tạo cạnh |
| 4 | yếu tố tác động | `PT_TRIGGERED_BY` (có `effect`) / `PT_EXPOSED_TO` | `effect` = trigger, aggravate, relieve |
| 5 | tiền sử / thuốc | `PT_HAS_HISTORY` / `PT_TAKES_DRUG` | thuốc `kind` taking/allergy; tiền sử `of` self/family |

- **Vấn đề:** dữ liệu cũ gắn theo "đợt-vùng" làm mất fact khi chưa rõ vùng; cần thấy được phủ định, thời điểm khởi phát, lịch sử đổi giá trị.
- **Cơ chế:** chủ thể là `PtLesion` (một vùng tổn thương, id do ai_service sinh) hoặc `Patient` (`scope=body`, nhóm 4 không `effect`, nhóm 5). Nhóm đơn trị (nhóm 3): giá trị mới đánh dấu cạnh cũ `superseded`. Các nhóm khác: nhắc lại cập nhật `last_confirmed_at`, "đã hết" đánh `resolved`. `onset_at` do knowledge quy đổi từ `onset_text` (`onset_resolver.py`, theo ngày của tin nguồn; không chắc thì để trống). Truy vấn mặc định chỉ trả `current`; fact quá 14 ngày chưa nhắc lại gắn cờ "chưa xác nhận gần đây".
- **Khớp nút lúc ghi** (`patient_fact_linker.py`): khớp tên chính xác → LLM dịch sang tên chuẩn rồi khớp → tìm ứng viên chứa tên + LLM chọn → để trống (`link_method`). Tối đa 2 lần gọi LLM cho cả lô.
- **Dùng gì:** `patient_fact_graph_service.py`, `patient_fact_relations.py`, `patient_fact_linker.py`; Neo4j Community (một database nên tách bằng nhãn).
- **Hạn chế:**
  - Không có transaction chung Neo4j–Postgres; ghi graph lỗi chỉ log nên lượt đó thiếu fact. Ghi graph nằm **trước** khi trả kết quả cho consultation, nên khi có nhãn chưa khớp tin assistant `queued` lâu hơn vài giây.
  - Độ khớp nút đo ngày 2026-11-12 (35 nhãn tiếng Việt, một lần chạy, LLM không tất định): khớp chính xác 49%, thêm LLM chọn ứng viên 77%. Hụt nhiều ở nhóm hình thái / tổn thương thứ phát. Fact không khớp giữ dạng chữ và không tham gia mở rộng.
  - `name` của nhóm 3 do model điền: alias tiếng Việt phổ biến được chuẩn hoá, chữ lạ thành thuộc tính tự do (không gom vào `course` ...).
  - Dữ liệu ghi theo mẫu 14 nhóm cũ không tương thích; dùng seed (`make reseed-users`) thay vì đọc lại.

### 8.2 Vòng đời fact trong một lượt
1. `build_context` đọc fact hiện hành. 2. `extract_facts` trích và gộp. 3. Cuối lượt `save_turn_facts` ghi (`POST /internal/patient-facts/apply`); `query_patient_graph` ghi sớm khi cần mở rộng ngay. 4. Form hồ sơ ghi dị ứng/tiền sử/thuốc qua `PUT /internal/patient-facts/{id}/profile`; clinical đọc dạng dài hạn qua `GET /internal/patient-facts/long-term`.

### 8.3 Mở rộng bệnh ứng viên (`patient_graph_context_service.py`)
- **Vấn đề:** từ vài triệu chứng, gợi ý bệnh đáng tra cứu tiếp và triệu chứng nên hỏi để phân biệt.
- **Cơ chế:** hạt giống là fact `current` đã khớp nút PrimeKG, có loại cạnh đi tiếp, là thuốc đang dùng (không phải dị ứng), không phải bệnh của người nhà (tối đa 20 mới nhất). **Một bước**:

  | Hạt giống | Cạnh | Điểm |
  |---|---|---|
  | triệu chứng / hình thái | `DISEASE_PHENOTYPE_POSITIVE` | `3 / ln(2 + số bệnh nối với triệu chứng)` |
  | bệnh nền / tiền sử | `DISEASE_DISEASE` | 1.0 |
  | thuốc đang dùng | `INDICATION` | 1.0 |
  | phơi nhiễm | `EXPOSURE_DISEASE` | 1.0 |

  Cộng dồn theo bệnh, lấy 12 ứng viên, trừ **2.0** cho mỗi triệu chứng người bệnh nói không có mà bệnh thường có (qua `DISEASE_PHENOTYPE_POSITIVE`), bỏ điểm ≤ 0, giữ `top_k`. Với 3 bệnh đầu: `discriminating_questions` (bỏ phenotype đã có), ≤3 câu trích sách mỗi bệnh, ghi chú thuốc (`DRUG_EFFECT` thuốc có thể gây triệu chứng, `CONTRAINDICATION` với bệnh ứng viên).
- **Dùng gì:** PrimeKG + cạnh sách (`EDGE_SOURCES = ["KG","DOC"]`, **luôn dùng cả sách**, không theo `KG_EDGE_SOURCES` toàn cục); cạnh viết thẳng trong pattern Cypher nên cạnh `PT_*` không bao giờ khớp.
- **Hạn chế:** đồ thị thưa nên điểm đồng hạng sắp xếp tuỳ ý; chỉ PrimeKG thì ứng viên toàn bệnh hiếm ngoài da liễu (đo 2026-11-12: "ngứa + ban đỏ + mụn nước" ra epidermolysis bullosa, Hennekam-Beemer; thêm cạnh sách ra dermatitis herpetiformis, atopic dermatitis, scabies). Cạnh phủ định rất ít (2.386 cạnh PrimeKG + 159 cạnh sách so với ~300 nghìn cạnh dương) nên trừ điểm tác dụng hạn chế. Chỉ trừ điểm, không loại hẳn. Màn bác sĩ **chưa** dùng `/context`.

---

## 9. Clinical và vòng kín dữ liệu

### 9.1 `apply_turn` (ghi giả thuyết và ảnh)
- **Vấn đề:** kết quả lập luận cần lưu để bác sĩ xem và để gắn với lịch khám.
- **Cơ chế:** `ClinicalRecordService.applyClinicalEpisodeByTurn`: gom giả thuyết theo `body_site`, mỗi vùng một **đợt bệnh** (mở nếu chưa có), lưu hạng, mã bệnh, độ tin cậy, bằng chứng; ảnh gắn đợt theo vùng/mã bệnh. Đợt không còn `open` thì khoá, bỏ cập nhật.
- **Hạn chế:** giả thuyết không có vùng và hội thoại chưa có đợt nào thì **bị bỏ** (log warning). Đợt vẫn theo vùng (`clinical_episodes.body_site` NOT NULL): việc "một đợt mở mỗi hồ sơ" và đặt lịch theo hồ sơ **chưa làm** (`tmp/plan/todo/2026-11-12-chuan-hoa-state-hoi-thoai-va-dat-lich.md`).

### 9.2 Chốt kết luận (`FinalizeReportService`)
- **Vấn đề:** kết luận của bác sĩ phải bất biến, truy được, và dữ kiện lúc chốt không đổi dù graph đổi sau đó.
- **Cơ chế:** bắt buộc `diagnosis`, `reasoning`, `description`, `diagnosis_code` (thiếu thì 422). Lấy fact hiện hành từ graph (bác sĩ chỉ giữ hoặc bỏ); gọi ai `/internal/extract-facts-from-description` (trước transaction) để chuyển mô tả thành fact mới (`doctor_observed`, hoặc `doctor_corrected` khi trùng khoá fact đã giữ); lưu **snapshot** trong `finalize_reports.snapshot`. Chốt **không ghi ngược graph**.
- **Hạn chế:** ai hoặc graph lỗi thì **502 và không chốt gì** (cố ý: chốt thiếu fact tệ hơn phải thử lại). Fact bác sĩ nhập lúc chốt chỉ nằm trong snapshot, agent chat không biết. Fact bác sĩ đã bỏ vẫn còn trong graph ở lần khám sau. Chưa kiểm chứng chất lượng nhãn từ mô tả với LLM thật.

### 9.3 Đánh chỉ mục và journey
- **Cơ chế:** sau khi chốt, clinical gọi knowledge `POST /internal/cases`: `CaseIndexService.index_case` (embedding + sparse vào Qdrant) và `journey.sync_case` (Neo4j journey). `POST /internal/cases/reindex` kéo lại từng trang báo cáo từ clinical (`make reindex-cases`).
- **Vòng kín:** báo cáo đã chốt quay lại làm E# cho `search_finalize_report` ở các lượt sau.
- **Hạn chế:** lỗi gọi knowledge chỉ log (báo cáo đã lưu), ca thiếu trong Qdrant tới khi reindex. Journey graph dùng cho màn bác sĩ, không phải cho agent.

---

## 10. Nạp tri thức (pipeline sách, `document_ingest`)

- **Vấn đề:** sách PDF phải thành chunk có mục lục và đồ thị quan hệ có trích dẫn trước khi agent dùng được.
- **Cơ chế:** admin upload PDF; sáu bước, mỗi bước người duyệt phải `approve` mới chạy bước sau: `ingest` (PDF → chữ theo trang) · `toc` (AI đọc mục lục, người sửa; không phụ thuộc `ingest`) · `chunks` (cắt theo khung mục lục) · `index` (embedding + Qdrant) · `graph` (LLM trích triple từ chunk, người duyệt) · `graph_index` (lưu Neo4j, cạnh `DOC`, khớp nút bằng từ điển PrimeKG + DermO). `index` và `graph` chạy song song sau `chunks`.
- **Hạn chế:** đồ thị sách chỉ tốt bằng chất lượng trích triple và mức người duyệt xem; guideline đang chờ bác sĩ duyệt. Chưa có tài liệu triển khai pipeline; không có job dọn file MinIO mồ côi.

---

## 11. Hạn chế chung

- **Chưa kiểm chứng toàn luồng** với model thật qua worker + FE; test hiện dùng graph/LLM giả (`ai_service` 73 test, `clinical_service` 16, `knowledge_service` 135 trong đó 2 lỗi `graph_schema` có từ trước).
- Hiệu năng: mỗi lượt có nhiều lần gọi LLM tuần tự (`extract_facts`, `plan`, từng vòng `choose_tools` + `reflect`, `answer`, cộng trích thực thể mỗi lần `hybrid_retrieval`, khớp nút khi ghi fact); mỗi vòng tra cứu 30-60 giây với model nhỏ, nên có trần 3 vòng.
- Hai lớp chống bịa (E#/H# và grounding) chỉ kiểm **có nguồn**, không kiểm **nguồn có ủng hộ**.
- Phụ thuộc dịch Việt–Anh bằng LLM ở nhiều chỗ (thực thể, khớp nút, mở rộng BM25) vì dữ liệu nền tiếng Anh.
- Đợt bệnh theo vùng; chưa có thẻ "Tình trạng hiện tại" cho bệnh nhân; ưu tiên/xưng hô của người dùng không còn được agent nhớ (đã bỏ memory).
- Không có transaction chung giữa Neo4j, Qdrant và Postgres.

---

## 12. Phạm vi tra soát

Đã đọc code: `ai_service` (`turn.py`, `graph/`, `reasoning/`, `tools/`, `prompt/`, `config/`), `knowledge_service` (`retrieval_service`, `patient_fact_*`, `patient_graph_context_service`, `kg_intent_service`, `case_index_service`, `patient_journey_service`, `document_stage`), `clinical_service` (`ClinicalRecordService`, `FinalizeReportService`).

Chưa đọc sâu, chỉ dựa vào docstring hoặc ghi chú trong repo: `semantic_search`/`keyword_search`, nội dung chi tiết `document_graph_service` (truy vấn triple), `EmbeddingClient` (model embedding), tầng consultation (SSE, ghi tin nhắn), FE. Số liệu đo (độ khớp nút, điểm trừ phủ định, số cạnh phủ định) lấy từ `docs/notice/patient-fact-graph.md`, không đo lại.
