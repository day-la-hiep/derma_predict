# [Pending] Cải thiện nhánh Knowledge Graph

Tool `knowledge_graph_query` (`core/agent/tools/hybrid_retrieval/kg_templates.py`,
`core/app/services/knowledge_graph_service.py`) chạy được nhưng còn đơn giản. Tài liệu này ghi các điểm chưa làm để
chọn việc khi còn thời gian; không phải cam kết.

## 1. Việc chưa làm (theo mức ảnh hưởng)

| # | Việc | Vì sao | Gợi ý cách làm |
|---|---|---|---|
| 1 | **Trực quan hoá KG theo bệnh nhân (mở rộng M3.15)** | Đồ thị hành trình bệnh nhân (M3.15) đã có; phần KG tri thức quanh bệnh nhân vẫn chưa làm, xem [requirements.md](../overview/requirements.md) | API trả subgraph quanh thực thể của bệnh nhân (từ clinical fact M3.9) + thư viện vẽ graph ở FE |
| 2 | **Khớp thực thể tiếng Việt ngay trên đồ thị** | KG chỉ khớp tên tiếng Anh; việc dịch phụ thuộc hoàn toàn vào một lần gọi LLM, LLM yếu thì dịch sai là mất cả nhánh | Bảng alias Việt → Anh/DermO (từ DermO synonyms + `dermo_terms`, bổ sung tay các bệnh thường gặp) tra trước khi hỏi LLM |
| 3 | **Khớp tên bằng `CONTAINS`** | `_PRIMEKG_SEARCH_QUERY` dùng `toLower(n.name) CONTAINS ...`: có thể ra thực thể không liên quan ("acne" ra cả tên dài chứa "acne") và không dùng index | Ưu tiên khớp chính xác (`exact_dermo`) rồi mới `CONTAINS`; hoặc full-text index của Neo4j |
| 4 | **Điểm bệnh ứng viên là heuristic** | Trọng số `3 / ln(2 + degree)` và trần 2-hop chưa được kiểm chứng với ca thật | Bộ ca có đáp án để chỉnh trọng số; so thứ hạng với chẩn đoán của bác sĩ |
| 5 | **Chưa dùng chống chỉ định / tác dụng phụ của thuốc để kiểm tra đơn** | Quan hệ `CONTRAINDICATION` đã nạp nhưng chỉ hiện như một câu quan hệ | Tool kiểm tra thuốc vs tiền sử/dị ứng của bệnh nhân (`patient_profile`) |
| 6 | **Agent chỉ dùng 11 loại quan hệ** | `RELATION_LABELS` không có `DISEASE_PROTEIN`, `EXPOSURE_DISEASE`, `PHENOTYPE_PHENOTYPE` và toàn bộ quan hệ DermO (mục 3), nên chưa trả lời được câu hỏi cơ chế, tiếp xúc, biến chứng | Thêm vào `RELATION_LABELS` + template intent khi có nhu cầu (vd `DISEASE_PROTEIN` cho cơ chế, `RESULTS_IN` cho biến chứng, `EXPOSURE_DISEASE` cho dị ứng tiếp xúc) |
| 7 | **KG và sách giáo khoa chưa liên kết** | Cùng một bệnh nhưng đoạn sách và nút KG không biết nhau; chỉ gặp nhau ở bước rerank | Gắn `dermo_id`/tên chuẩn vào payload chunk lúc `index` để lọc và trích nguồn chéo |
| 8 | **Đánh giá chất lượng** | Chưa có số đo cho nhánh KG (chọn đúng thực thể? ứng viên đúng bao nhiêu?) | Bộ câu hỏi nhỏ có đáp án + script đo (xem `agent/test/try_retrieval.py`) |
| 9 | **Nạp lại KG** | Đã có `core/graph_base/` (`make kg-download kg-build kg-load kg-verify`); script cũ trong `data_ingest/` chưa dọn | Dọn script cũ, chuyển prod (`reset-and-gen-data.sh`) sang `graph_base` |
| 10 | **Neo4j là phụ thuộc cứng của nhánh KG** | Neo4j chưa chạy thì nhánh KG báo `notes` và mất ứng viên chẩn đoán | Đã chịu lỗi từng nhánh; có thể thêm cache các truy vấn phổ biến |

## 2. Ràng buộc cần giữ

- Kết quả KG chỉ là **gợi ý**, không phải bằng chứng lâm sàng và không phải chẩn đoán: `hybrid_retrieval` đã báo
  `evidence_found=false` khi chỉ có KG mà không có đoạn sách, giữ nguyên hành vi này.
- Thay đổi dữ liệu KG không được làm mất dữ liệu đã nạp (nạp lại phải idempotent).
- Entity nghiệp vụ nằm ở `core/app/dto/base/`; nếu cần entity mới (vd cho M3.15) phải hỏi duyệt trước.

## 3. Danh mục quan hệ hiện có trong đồ thị nền

Cột "Agent dùng" = có trong `kg_templates.py::RELATION_LABELS`; "Trích từ sách" = có slot trong `pipeline/document_ingest/graph_schema.py::SLOTS`
(bước `graph`). Schema đầy đủ và cách nạp: [module/knowledge-graph.md](../module/knowledge-graph.md).

### 3.1 PrimeKG (`:Entity`, cạnh không có `source` = `KG`)

| Relationship type | Đầu → đầu | Agent dùng | Trích từ sách |
|---|---|---|---|
| `DISEASE_PHENOTYPE_POSITIVE` | disease ↔ effect/phenotype | có | có (`phenotypes_present`) |
| `DISEASE_PHENOTYPE_NEGATIVE` | disease ↔ effect/phenotype | có | có (`phenotypes_absent`) |
| `DISEASE_DISEASE` (parent-child) | disease → disease | có | có (`subtypes`) |
| `INDICATION` | drug ↔ disease | có | có (`drugs_indicated`, `indications`) |
| `CONTRAINDICATION` | drug ↔ disease | có | có (`drugs_contraindicated`, `contraindications`) |
| `OFF_LABEL_USE` | drug ↔ disease | có | có (`drugs_off_label`) |
| `DRUG_EFFECT` | drug ↔ effect/phenotype | có | có (`side_effects`) |
| `DRUG_DRUG` | drug → drug (~2,67M dòng, chiếm đa số cạnh) | có (chỉ `drug_profile` nhiều thuốc) | không |
| `DISEASE_PROTEIN` | disease ↔ gene/protein | không | có (`genes`) |
| `EXPOSURE_DISEASE` | exposure ↔ disease | không | có (`exposures`) |
| `PHENOTYPE_PHENOTYPE` (parent-child) | effect/phenotype → effect/phenotype | không | không |

Đồ thị nền dựng lại ngày 2026-10-21 không còn các quan hệ hồ sơ BYT (`TYPICAL_LOCATION`, `RISK_FACTOR`, `RED_FLAG`) và cạnh "mapped to primekg";
`kg_templates.py` vẫn còn truy vấn chúng (nay trả rỗng). Sách không trích 3 quan hệ này vì `UNMAPPED_KINDS` coi chúng là thông tin không có quan hệ tương ứng để nạp.

### 3.2 DermO (`:DermoTerm`)

| Relationship type | Số cạnh | Agent dùng | Trích từ sách |
|---|---|---|---|
| `IS_A` | 3.817 | không (agent chỉ tra cha khi `lookup` DermO) | có (`subtypes`, chiều con → cha) |
| `HAS_SYMPTOM` | 126 | không | không |
| `RESULTS_IN` | 30 | không | có (`complications`) |
| `ASSOCIATED_WITH` | 18 | không | có (`associated_diseases`) |
| `DERIVES_FROM` | 2 | không | không |

### 3.3 Hướng khai thác thêm (chưa làm)

- `HAS_SYMPTOM` của DermO (126 cạnh) có thể bổ sung nguồn triệu chứng cho `symptoms_of_disease` ở các bệnh PrimeKG thiếu phenotype, qua `dermo_id`.
- `IS_A` của DermO có thể mở rộng tìm kiếm lên bệnh cha / xuống bệnh con (nhóm bệnh) thay vì chỉ so tên chính xác.
- `RESULTS_IN` cho intent mới "biến chứng"; hiện chỉ đi vào đồ thị qua cạnh `DOC`, và agent cũng chưa truy vấn tới.
- Cạnh `DOC` chỉ hiện với agent khi `KG_EDGE_SOURCES` có `DOC` (mặc định `["KG"]`).

