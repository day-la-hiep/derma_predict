# Yêu cầu hệ thống & trạng thái hiện tại

Tài liệu tổng hợp yêu cầu nghiệp vụ của Derma Hospital, chia theo module và chức năng để tiện giao việc.
Trạng thái được đối chiếu với code ngày **2026-10-31** (nhánh `docs/bao-cao`).

**Ký hiệu trạng thái**

| Ký hiệu | Ý nghĩa |
|---|---|
| ✅ Xong | chạy được end-to-end (BE + FE) |
| 🟡 Một phần | có một phần (chỉ BE, chỉ schema DB, hoặc làm đơn giản hơn yêu cầu) |
| 🔲 Chưa làm | chưa có code |
| ⏸ Hoãn | ngoài scope hiện tại hoặc chưa chốt luồng |

> Kết quả AI chỉ là gợi ý hỗ trợ, **không phải chẩn đoán y khoa**.

## 1. Tác nhân

| Tác nhân | Mô tả | Hiện trạng trong code |
|---|---|---|
| **Người dùng** | người đã đăng ký và đăng nhập; quản lý tài khoản của mình, đăng xuất | đã có đăng ký / đăng nhập / đăng xuất / làm mới token / sửa thông tin (JWT, `/auth/*`). Chat, hồ sơ bệnh nhân, tư vấn, video call buộc có token; API `/admin/*` (tài liệu, schema đồ thị) chưa kiểm tra token / vai trò |
| **Bệnh nhân** | dùng hệ thống để tiền chẩn đoán và trao đổi về bệnh da liễu: chat với chatbot (gửi ảnh, mô tả triệu chứng), tra cứu bệnh và ca bệnh từ KB, đặt lịch khám, quản lý báo cáo kết luận / lịch sử khám / ảnh, trao đổi với bác sĩ qua chat hoặc video call (bác sĩ chưa tiếp nhận thì tiếp tục hỏi chatbot). Cuộc trò chuyện được tổng hợp thành clinical fact và báo cáo cho bác sĩ | bảng `patient_profiles` (một user có nhiều hồ sơ). Phần chat với chatbot đã chạy |
| **Bác sĩ** | xem báo cáo tổng hợp, clinical fact, nguồn lập luận từ KB, lịch sử và hồ sơ bệnh nhân; cập nhật hồ sơ sau khám; lưu ca bệnh và ảnh đã xác nhận (làm dữ liệu tham khảo, huấn luyện CNN); chat / video call với bệnh nhân và truy xuất tin nhắn nguồn làm bằng chứng; trực quan hoá Knowledge Graph; tải giáo trình / guideline lên để bổ sung KB | bảng `doctors`, seed `doctor-1`. Có màn hình riêng ở `/doctor` (hàng đợi ca, chat, báo cáo, lịch sử khám) |
| *(Admin — có trong code, không có trong yêu cầu)* | hiện nạp sách ở `/doctor/documents` và quản lý schema đồ thị ở `/doctor/graph-schema` | bảng `admins` (seed `admin-1`). Theo yêu cầu thì việc tải tài liệu là của **bác sĩ**, cần thống nhất lại vai trò |

## 2. Tổng quan theo module

Cách chia bám theo ranh giới trong code (service / API / FE feature / worker), không theo từng bảng DB.

| Mã | Module | Tác nhân | Trạng thái | Tài liệu |
|---|---|---|---|---|
| M1 | Tài khoản & hồ sơ bệnh nhân | Người dùng | 🟡 JWT + hồ sơ xong; `/admin/*` chưa phân quyền | — |
| M2 | Chatbot tư vấn AI (agent, memory) | Bệnh nhân | ✅ phần lõi, 🟡 memory / sources | [chat.md](../module/chat.md) |
| M3 | Tư vấn với bác sĩ (báo cáo tiền tư vấn, chat, video, báo cáo kết luận, đồ thị hành trình) | Bệnh nhân, Bác sĩ | ✅ luồng chính, 🟡 một số phần phụ | [doctor-consultation.md](../module/doctor-consultation.md), [patient-journey-graph.md](../module/patient-journey-graph.md) |
| M4 | Kho tri thức: số hoá tài liệu | Bác sĩ (hiện là Admin) | ✅ pipeline sách → Qdrant, chatbot tra được | [book-ingest-pipeline.md](../module/book-ingest-pipeline.md) |
| M5 | Đồ thị tri thức (nền, cạnh trích từ sách, schema admin) | Bác sĩ (Admin), Chatbot | ✅ dựng, trích, truy vấn; 🟡 dữ liệu sách còn thưa | [knowledge-graph.md](../module/knowledge-graph.md), [knowledge-graph-flow.md](../module/knowledge-graph-flow.md) |
| M6 | Ca bệnh & dữ liệu ảnh (CNN) | Bác sĩ | 🟡 nạp ca vào KB xong; nhãn ảnh / xuất dataset chưa | — |
| M7 | Đặt lịch khám | Bệnh nhân, Bác sĩ | ⏸ hoãn (ngoài scope hiện tại) | — |

## 3. Chi tiết chức năng

### M1 — Tài khoản & hồ sơ bệnh nhân

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M1.1 | Đăng ký tài khoản | ✅ | `POST /auth/register` (`auth_api.py`), màn đăng ký ở FE (`AuthScreen`) |
| M1.2 | Đăng nhập / đăng xuất | ✅ | `POST /auth/login`, `/refresh`, `/logout`, `GET /auth/me`; FE giữ token và gắn `Authorization: Bearer` (`fe/app/access-gate.tsx`); `get_current_user` (`app/api/deps.py`) buộc token ở chat, hồ sơ, tư vấn, video call |
| M1.3 | Quản lý tài khoản cá nhân (xem / sửa thông tin) | ✅ | `PATCH /auth/me`; FE `AccountSettingsDialog` |
| M1.4 | Phân quyền theo vai trò (bệnh nhân / bác sĩ / admin) | 🟡 | `require_role` dùng cho API bác sĩ (`doctor_api.py`); `/admin/*` chưa dùng nên ai có token (hoặc không) cũng gọi được |
| M1.5 | Quản lý hồ sơ bệnh nhân (một tài khoản nhiều hồ sơ, ví dụ cho người nhà) | ✅ | API `/patient-profiles` (CRUD theo tài khoản trong JWT; chặn xoá hồ sơ cuối / hồ sơ đã có hội thoại hoặc báo cáo kết luận). Hồ sơ có quan hệ, SĐT, dị ứng và tiền sử tự khai. UI: dialog "Hồ sơ" ở menu tài khoản + chọn hồ sơ cho cuộc trò chuyện mới ở sidebar chat |
| M1.6 | Thư viện ảnh bệnh đã lưu của bệnh nhân | 🟡 | ảnh chat nằm trong `files` + `message_files`; ảnh đã gắn báo cáo kết luận nằm trong `patient_images`. Chưa có màn xem tập trung |

### M2 — Chatbot tư vấn AI (agent, memory)

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M2.1 | Hỏi đáp với chatbot, stream câu trả lời realtime | ✅ | Core → RabbitMQ → Agent Worker → Redis → SSE |
| M2.2 | Tạo / xem danh sách / xem lịch sử hội thoại | ✅ | `/conversations`, `/conversations/{id}/messages` |
| M2.3 | Gửi ảnh da, phân loại bằng CNN | ✅ | `POST /uploads` → MinIO; tool `classify_skin_image` (22 lớp, chỉ là giả thuyết) |
| M2.4 | Mô tả triệu chứng → gợi ý chẩn đoán phân biệt | ✅ | bệnh ứng viên từ `knowledge_graph_query` (intent `diseases_with_symptom` / `differential`) (cùng triệu chứng, bệnh liên quan) + gợi ý câu hỏi phân biệt trong `record_reasoning`; đường xếp hạng theo phenotype (`describe_morphology`, `generate_differential`) đã bỏ |
| M2.5 | Chatbot hỏi lại khi thiếu thông tin | ✅ | v1: tool `ask_user` + `interrupt()`, trả lời qua `/questions/{id}/answer`; v2 đặt câu hỏi ở cuối câu trả lời |
| M2.6 | Hiển thị các bước lập luận / tool đã dùng | ✅ | event `message.thinking`, `message.tool_result`, lưu `metadata.reasoning` |
| M2.7 | Tra cứu thông tin bệnh lý từ KB | ✅ | chunk sách giáo khoa (Qdrant, `hybrid_retrieval` / `semantic_search` / `keyword_search`), đồ thị trích từ sách (`query_document_graph`), PrimeKG + DermO (`knowledge_graph_query`) |
| M2.8 | Tra cứu **ca bệnh liên quan** | ✅ | tool `search_finalize_report` / `search_finalize_report_by_image` tìm trong kho báo cáo kết luận (Qdrant `derma_finalize_reports`) |
| M2.9 | Chọn model LLM cho hội thoại | ✅ | `/models`, `PATCH /conversations/{id}/model` |
| M2.10 | Ghi nhớ thông tin bệnh nhân giữa các hội thoại | 🟡 | Memory theo hồ sơ lưu Postgres (schema `langgraph`), ghi theo batch ở nền; checkpoint hội thoại cũng lưu Postgres; chưa có chính sách xoá / dọn khi xoá hồ sơ hay hội thoại |
| M2.11 | Trích dẫn nguồn (sources) cho câu trả lời | 🟡 | đã có `Source` (`dto/common/chat.py`, lưu trong `messages.metadata` JSON, không có bảng riêng); agent chưa sinh, `ChatSourceDto` trên wire chưa khớp `Source` |
| M2.12 | Lọc intent trước khi lập luận (chào hỏi / ngoài phạm vi trả lời luôn) | ✅ | `agent/graph/triage.py`, bật bằng `AGENT_TRIAGE_ENABLED` |
| M2.13 | Chọn phiên bản graph tiền chẩn đoán v1 / v2 | ✅ | `AGENT_GRAPH_VERSION`; v2 có hai làn chữ / ảnh, chưa chạy qua Worker + API thật, xem [agent-graph-versions](../notice/agent-graph-versions.md) |
| M2.14 | Trích dữ kiện bệnh nhân mỗi lượt (v2) | 🟡 | `diag.facts` trong checkpoint, chưa lưu bền vào `clinical_facts` ([persistent-clinical-facts](../pending/persistent-clinical-facts.md)) |
| M2.15 | Mô tả ảnh bằng model multimodal bổ sung cho CNN | 🟡 | chỉ bật khi `AGENT_VISION_MODEL` không rỗng, xem [medgemma-image-description](../notice/medgemma-image-description.md) |

### M3 — Tư vấn với bác sĩ

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M3.1 | Bệnh nhân gửi yêu cầu tư vấn bác sĩ từ một hội thoại | ✅ | `POST /conversations/{id}/request-consultation` (`consultation_sessions`: `pending → active → resolved`, tin mốc `consultation_requested`); FE `RequestConsultationDialog` |
| M3.2 | Bác sĩ xem hàng đợi yêu cầu, nhận ca | ✅ | `GET /doctor/consultations`, `POST .../accept`, SSE `/doctor/consultations/stream`; FE `SessionList` |
| M3.3 | Bác sĩ và bệnh nhân chat trực tiếp trong cùng hội thoại | ✅ | `POST /doctor/consultations/{id}/reply` và `POST /conversations/{id}/messages` khi ca `active`; realtime qua room SSE (`message.created`) |
| M3.4 | Bác sĩ chưa nhận thì bệnh nhân vẫn hỏi chatbot | ✅ | ca `pending` thì AI vẫn trả lời; ca `active` chỉ ghi tin, không tạo turn agent |
| M3.5 | Video call | ✅ | WebRTC: `/video-calls/*` (tạo, accept, end, signal, ICE config, SSE `/video-calls/stream`), bảng `video_calls`, FE `features/video-call/`; cần TURN khi khác mạng, xem [video-call](../notice/video-call.md) |
| M3.6 | Bác sĩ đóng ca tư vấn | ✅ | `POST .../resolve` hoặc chốt báo cáo kết luận (`POST .../finalize`), tin mốc `consultation_resolved` |
| M3.7 | Bệnh nhân huỷ yêu cầu khi chưa có bác sĩ nhận | 🔲 | chưa có endpoint huỷ; phiên `pending` chỉ đóng được khi bác sĩ nhận rồi đóng |
| M3.8 | Sinh **báo cáo tổng hợp** trước khi bác sĩ tư vấn | 🟡 | đã có schema: `ConsultationSession.report` → bảng `pre_consultation_reports`. Sinh khi bệnh nhân yêu cầu tư vấn (M4.1) qua `agent/handler/consultation_report.py` (Worker); sinh lại được, khác báo cáo kết luận của bác sĩ |
| M3.9 | Trích **clinical fact** có cấu trúc từ hội thoại (triệu chứng, thời gian, vị trí, tiền sử, thuốc, dị ứng...) | 🟡 | đã có schema: `PatientProfile.clinical_facts` → bảng `clinical_facts` (`template_id` trỏ `clinical_fact_templates` giữ loại / nhãn / `ontology_id`; fact giữ chi tiết, trạng thái thay thế). Trích xuất chạy khi bệnh nhân yêu cầu tư vấn: Worker xử lý turn `consultation_report` (`agent/handler/consultation_report.py`, `agent/common/fact_extractor.py`); v2 còn trích dữ kiện mỗi lượt vào `diag.facts` (chưa lưu bền vào `clinical_facts`, xem [persistent-clinical-facts](../pending/persistent-clinical-facts.md)) |
| M3.10 | Mỗi clinical fact liên kết tới **tin nhắn nguồn** | 🟡 | đã có schema: `ClinicalFact.provenances[].message` (`ClinicalProvenance`) → bảng `clinical_provenances` |
| M3.11 | Bác sĩ xem clinical fact, nguồn lập luận từ KB, mở tin nhắn nguồn | 🟡 | FE `features/doctor/` (`ClinicalFactList`, `FactSources`, `AiSummaryView`, `ReportPanel`); nguồn lập luận từ KB chưa hiển thị đủ |
| M3.12 | Bác sĩ xem hồ sơ + lịch sử báo cáo kết luận của bệnh nhân | ✅ | `ConsultationSessionOutput.patient` có thêm quan hệ/SĐT/dị ứng/tiền sử; `GET /doctor/consultations/{id}/finalize-reports` trả lịch sử báo cáo kết luận của bệnh nhân thuộc phiên. UI: `PatientInfoCard` hiện quan hệ + cảnh báo dị ứng, panel "Báo cáo kết luận" trong `ReportPanel` |
| M3.13 | Bác sĩ cập nhật hồ sơ / báo cáo kết luận sau mỗi lượt khám | 🟡 | bác sĩ **chốt** báo cáo kết luận khi bấm "Đóng ca": form điền sẵn dữ kiện đang hiệu lực kèm nguồn (`GET /doctor/consultations/{id}/finalize-draft`), chốt + đóng ca trong một request (`POST .../finalize`); hoặc đóng ca không ghi báo cáo kết luận. Form chốt có khối **gợi ý từ đồ thị** (nhận định/lời khuyên các phiên trước từ PJKG, bệnh ứng viên và cờ đỏ từ KG) để bác sĩ bấm chọn; không còn luồng khám trực tiếp. Phiếu đã chốt không sửa. Hồ sơ (dị ứng/tiền sử/SĐT) vẫn chỉ bệnh nhân tự sửa. Hạn chế: bác sĩ tìm được mọi hồ sơ bệnh nhân (chưa phân quyền theo bệnh nhân phụ trách) |
| M3.14 | Báo cáo kết luận / lịch sử khám | 🟡 | bệnh nhân xem báo cáo kết luận của từng hồ sơ (chỉ đọc, `GET /patient-profiles/{id}/finalize-reports`, tab "Báo cáo kết luận": nhận định + ghi chú). Bác sĩ có màn **Lịch sử khám** (`/doctor/records`): bảng phiếu do mình chốt (lọc thời gian / mức khẩn cấp, tìm kiếm), chi tiết 3 tab Tóm tắt / Dữ kiện / Hội thoại và ảnh, Xuất PDF (in trình duyệt), Mở ca gốc. Mỗi phiếu có cột `snapshot` (JSONB) — bản chụp bất biến lúc chốt: hồ sơ bệnh nhân, cơ sở nhận định, mức khẩn cấp, dặn dò, dữ kiện kèm `origin` và tin nhắn nguồn. Ảnh bệnh trong `patient_images` chưa có API. Hạn chế: dữ kiện sinh trước khi ghi `clinical_provenances` không có nguồn; báo cáo kết luận cũ (`snapshot = null`) chỉ hiện nhận định/ghi chú |
| M3.15 | **Trực quan hoá** KG liên quan đến bệnh nhân | ✅ | đồ thị hành trình bệnh nhân: `GET /doctor/patient-profiles/{id}/journey-graph`, FE `PatientJourneyCanvas`; xem [patient-journey-graph](../module/patient-journey-graph.md) |
| M3.16 | Giới hạn phạm vi bác sĩ xem hội thoại (tới hết phiên gần nhất của mình) | ✅ | `ConsultationService.room_access`, xem [doctor-chat-access](../notice/doctor-chat-access.md) |

### M4 — Kho tri thức: số hoá tài liệu

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M4.1 | Tải lên giáo trình PDF, số hoá theo mục lục, nạp Qdrant | ✅ | `/doctor/documents`, các bước `ingest → toc → chunks → index`, có người duyệt, chạy ở Ingest Worker (`make ingest-worker`) |
| M4.2 | Tải lên guideline / tài liệu y khoa dạng khác | 🟡 | guideline hiện nạp bằng script (`data_ingest/`); pipeline chỉ nhận `type="book"` |
| M4.3 | Chatbot tra cứu tài liệu đã nạp | ✅ | `hybrid_retrieval`, `semantic_search`, `keyword_search` (Qdrant `derma_document_chunks_v4`), `query_document_graph` (cạnh `DOC` trong Neo4j) |
| M4.4 | Phối hợp chatbot để làm giàu KB (gợi ý / bổ sung tri thức) | ⏸ | chưa chốt luồng — đề xuất ở [docs/pending/kb-enrichment.md](../pending/kb-enrichment.md) |
| M4.5 | Quyền tải tài liệu dành cho bác sĩ | 🟡 | đã có `documents.uploaded_by_id` → `doctors`; API `/admin/*` chưa kiểm tra vai trò, phụ thuộc M1.4 |
| M4.6 | Nạp lại Qdrant (đổi model embedding, mất collection) | ✅ | `make reindex-qdrant`, xem [qdrant-reindex](../notice/qdrant-reindex.md) |

### M5 — Đồ thị tri thức

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M5.1 | KG da liễu (bệnh – triệu chứng – thuốc – gen) và ontology thuật ngữ | ✅ | PrimeKG + DermO trong Neo4j, dựng bằng `core/graph_base/` (`make kg-download kg-build kg-load kg-verify`) |
| M5.2 | Chatbot truy vấn KG | ✅ | tool `knowledge_graph_query` (template Cypher theo intent: ứng viên, phân biệt, điều trị, chống chỉ định, hồ sơ thuốc...) |
| M5.3 | Trích quan hệ từ sách và nạp Neo4j (cạnh `source='DOC'`) | ✅ | các bước `chunks → graph → graph_index` của pipeline; LLM trích theo ô quan hệ, người duyệt qua override |
| M5.4 | Người duyệt xem / sửa quan hệ trích từ sách | ✅ | `GET\|PATCH /admin/documents/{id}/triples`, FE `TripleBrowser`; tìm nút bằng `GET /admin/graph/nodes` |
| M5.5 | Admin định nghĩa loại thực thể và quan hệ cho bước trích | ✅ | `/doctor/graph-schema`, API `/admin/graph-schema/*`, bảng `graph_entity_types`, `graph_relations` |
| M5.6 | Chatbot truy vấn đồ thị trích từ sách (kèm câu trích + trang) | 🟡 | tool `query_document_graph`; dữ liệu còn thưa, khớp theo chuỗi nên tên tiếng Việt thường không khớp |
| M5.7 | Chuẩn hoá thuật ngữ bệnh nhân sang DermO | 🟡 | chạy bên trong `hybrid_retrieval` / `knowledge_graph_query`, chưa là chức năng độc lập |

### M6 — Ca bệnh & dữ liệu ảnh (CNN)

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M6.1 | Bác sĩ lưu ca bệnh (chẩn đoán đã xác nhận + ảnh + mô tả) | ✅ | lưu cùng báo cáo kết luận ([doctor-consultation](../module/doctor-consultation.md)); cờ `is_reference_case` hiện chỉ là metadata trong payload Qdrant, chưa có luồng "ca tham khảo" riêng |
| M6.2 | Ca bệnh đã xác nhận được nạp vào KB để chatbot tra (cho M2.8) | ✅ | chốt báo cáo kết luận thì `FinalizeReportIndexService.index_report` nạp Qdrant `derma_finalize_reports` (kèm ảnh); lỗi nạp chỉ ghi warning, bù bằng `make reindex-qdrant` |
| M6.3 | Xác nhận / gán nhãn ảnh để làm dữ liệu huấn luyện CNN | 🟡 | ghi được `patient_images.confirmed_label` khi chốt báo cáo; chưa có màn xác nhận / sửa riêng; nhãn nên khớp 22 lớp của CNN |
| M6.4 | Xuất bộ dữ liệu huấn luyện lại CNN | 🔲 | chưa có endpoint hay script export |

### M7 — Đặt lịch khám

| Mã | Chức năng | Trạng thái | Hiện trạng / việc cần làm |
|---|---|---|---|
| M7.1 | Bác sĩ khai báo lịch làm việc / khung giờ trống | ⏸ | hoãn: ngoài scope đồ án hiện tại, chưa có entity |
| M7.2 | Bệnh nhân đặt lịch khám | ⏸ | hoãn |
| M7.3 | Xem / huỷ / đổi lịch (cả hai phía) | ⏸ | hoãn |

## 4. Gợi ý thứ tự làm và chia việc

Các module có phụ thuộc, nên làm theo thứ tự sau để mỗi bước demo được:

| Đợt | Việc | Lý do |
|---|---|---|
| 1 | **M1** (đăng nhập, vai trò, hồ sơ) | mọi màn hình bác sĩ / bệnh nhân đều cần biết ai đang đăng nhập |
| 2 | **M2** (chat) và **M4** + **M5** (kho tri thức, đồ thị) | agent cần dữ liệu để tra cứu; M2.11 (sources) công sức thấp |
| 3 | **M3.1–M3.11** (yêu cầu, nhận ca, chat, báo cáo tiền tư vấn) | luồng chính bệnh nhân ↔ bác sĩ |
| 4 | **M3.12–M3.15** (hồ sơ, báo cáo kết luận, đồ thị hành trình), **M6** | cần bác sĩ đã dùng được hệ thống |
| 5 | **M3.5** (video call), **M4.4** (làm giàu KB), **M6.3–M6.4** | tính năng mở rộng |
| — | **M7** (đặt lịch) | hoãn, ngoài scope đồ án hiện tại |

Có thể giao song song theo 3 nhánh ít đụng nhau:
- **Nhánh nền tảng (BE + FE)**: M1, M7.
- **Nhánh AI / tri thức**: M2, M4, M5.
- **Nhánh tư vấn bác sĩ (BE + FE)**: M3, M6.

Quy trình thêm một nghiệp vụ mới: entity `dto/base` (**hỏi duyệt trước**) → model + migration → repository →
service → endpoint → màn hình FE. Quy ước chi tiết trong các skill ở `.claude/skills/`.
