# Knowledge graph (Neo4j): schema, cơ chế nạp, cơ chế khai thác

Neo4j chứa **hai đồ thị nền** dựng thẳng từ nguồn gốc bằng `core/graph_base/` (PrimeKG cho quan hệ, DermO cho ontology) cộng **cạnh trích từ sách giáo khoa**
(`source='DOC'`) do pipeline `document_ingest` thêm vào. Kết quả đồ thị chỉ là **gợi ý, không phải bằng chứng lâm sàng hay chẩn đoán**.
Hai đồ thị độc lập, không có cạnh nối nhau; chỉ gặp nhau qua so khớp tên (mục 3.2).

## 1. Schema

### 1.1 Đồ thị quan hệ: PrimeKG (namespace `:Entity`)

Nguồn: `kg.csv` của PrimeKG (Harvard Dataverse, DOI 10.7910/DVN/IXA7BM, CC0). **Không lọc theo da liễu**: mọi cách neo vào bệnh da liễu đều phải tự đặt luật
(đệ quy từ "skin disease" ra 17.008 bệnh gồm cả bệnh ngoài da; cắt theo độ sâu không ổn định). Chỉ bỏ các nhóm không dùng: giải phẫu, pathway,
bioprocess/molfunc/cellcomp, `protein_protein`, `drug_protein`.

Nút: `(:Entity:<Label> {id, name, type, source})`. **`id` chỉ duy nhất theo loại** (id HPO 972 và NCBI 972 là hai nút khác nhau), nên ràng buộc duy nhất
đặt trên từng `<Label>`, không đặt trên `:Entity`. Có thêm index tra cứu `Entity(id)`.

| `type` | Label | `source` | Số nút |
|---|---|---|---|
| `disease` | `Disease` | MONDO / MONDO_grouped | 15.813 / 1.267 |
| `effect/phenotype` | `EffectPhenotype` | HPO | 15.310 |
| `gene/protein` | `GeneProtein` | NCBI | 9.080 |
| `drug` | `Drug` | DrugBank | 4.540 |
| `exposure` | `Exposure` | CTD | 474 |

Cạnh: `(x)-[:<RELATION> {display_relation}]->(y)`; relationship type = tên quan hệ viết hoa. Phần lớn quan hệ có **cả hai chiều** như nguồn
(mỗi cặp hai cạnh ngược nhau), trừ `DRUG_DRUG`, `DISEASE_DISEASE`, `PHENOTYPE_PHENOTYPE` chỉ một chiều. Tổng ~3,46M cạnh.

| Relationship type | `display_relation` | Đầu → đầu | Số cạnh |
|---|---|---|---|
| `DRUG_DRUG` | synergistic interaction | drug → drug | 2.672.628 |
| `DISEASE_PHENOTYPE_POSITIVE` | phenotype present | disease ↔ effect/phenotype | 300.634 |
| `DISEASE_PROTEIN` | associated with | disease ↔ gene/protein | 160.822 |
| `DRUG_EFFECT` | side effect | drug ↔ effect/phenotype | 129.568 |
| `DISEASE_DISEASE` | parent-child | disease → disease | 64.388 |
| `CONTRAINDICATION` | contraindication | drug ↔ disease | 61.350 |
| `PHENOTYPE_PHENOTYPE` | parent-child | effect/phenotype → effect/phenotype | 37.472 |
| `INDICATION` | indication | drug ↔ disease | 18.776 |
| `OFF_LABEL_USE` | off-label use | drug ↔ disease | 5.136 |
| `EXPOSURE_DISEASE` | linked to | exposure ↔ disease | 4.608 |
| `DISEASE_PHENOTYPE_NEGATIVE` | phenotype absent | disease ↔ effect/phenotype | 2.386 |

Cạnh gốc **không có** property `source`; cạnh từ sách có `source='DOC'`. Truy vấn dùng `coalesce(r.source,'KG')`.
Số liệu trên theo bản `kg.csv` đang dùng (855 MB); bản Dataverse hiện tại (981 MB) có thể nhiều hơn.

> `DRUG_DRUG` chiếm ~77% số cạnh nên mọi truy vấn viết thẳng loại cạnh trong pattern.
> Hồ sơ Bộ Y tế (BYT) không còn trong đồ thị: không còn nút `RiskFactor` / `TypicalLocation` / `RedFlag` và cạnh `DISEASE_TYPICAL_LOCATION` / `DISEASE_RISK_FACTOR` / `DISEASE_RED_FLAG`.

### 1.2 Đồ thị ontology: DermO (namespace `:DermoTerm`)

Nguồn: `dermatology.obo` v1.19 (GitHub `dermatology-ontology/dermatology`, cùng bản với BioPortal). Label **riêng**, không dùng chung `:Entity` vì id khác namespace
(`DERMO:0000005` so với số thuần).

- Nút `(:DermoTerm {id, name, def, synonyms[], xrefs[], alt_ids[], is_obsolete})`: 3.427 term, 169 term có `def`. `synonyms` là danh sách tên (đã bỏ tag `<new synonym>`);
  `xrefs` là danh sách id (SNOMED, DOID, ICD10, OMIM…), không kèm mô tả.
- Cạnh giữ nguyên tên và chiều gốc của OBO: `IS_A` (3.817), `HAS_SYMPTOM` (126), `RESULTS_IN` (30), `ASSOCIATED_WITH` (18), `DERIVES_FROM` (2).
- Theo bài báo gốc (Fisher et al., 2016) DermO là ontology đơn giản, ít đa phân cấp. `has_symptom` nối bệnh với một biểu hiện đặc trưng (đích vẫn là term trong cùng ontology,
  có khi trông như tên bệnh); `results_in` là bệnh phát sinh từ bệnh khác. Bài báo không nêu `associated_with` / `derives_from`. Đây là lớp quan hệ phụ, thưa; quan hệ lâm sàng chính nằm ở PrimeKG.
- DermO dùng để **chuẩn hoá tên** (đồng nghĩa, cha–con); không nối trực tiếp sang `:Entity`. Cầu nối là so khớp tên ở runtime (mục 3.2).

### 1.3 Phần mở rộng từ sách (`document_ingest`)

- Cạnh thêm: `(x)-[r:<REL> {document_id, display_relation, source:'DOC', evidence, chunk_ids, pages, source_ref, triple_id}]->(y)`.
- Nút thêm (nếu chưa có): `:Entity` hoặc `:DermoTerm` với `added_by = [document_id,…]` để gỡ khi xoá sách.
- Loại thực thể và quan hệ trích được lấy từ `GraphSchema` = bảng core trong `pipeline/document_ingest/graph_schema.py` + định nghĩa của bác sĩ trong Postgres (`graph_entity_types`, `graph_relations`, trang `/doctor/graph-schema`). Xem `docs/notice/graph-relation-catalog.md`.
- Loại thực thể do bác sĩ tự định nghĩa thành nút `doc_<loại>_<slug tên tiếng Anh>`, `source='DOC'`.

## 2. Cơ chế nạp

### 2.1 Đồ thị nền (chạy tay, ngoài pipeline sách): `core/graph_base/`

```
tải gốc (data/raw) --build--> data/build/{primekg,dermo} --load--> Neo4j --verify
```

| Lệnh | Việc |
|---|---|
| `make kg-download` | Tải `kg.csv` (kiểm md5) và `dermatology.obo` (ghi sha256 vào `.meta.json`); bỏ qua nếu đã có |
| `make kg-build` | PrimeKG: giữ 5 loại nút và 11 quan hệ, bỏ cạnh trùng và dòng lỗi → `nodes.csv`, `edges.csv`, `summary.json`. DermO: parse OBO → `terms.json`, `summary.json` |
| `make kg-load [reset=1]` | Nạp PrimeKG rồi DermO. Batch 5.000 |
| `make kg-verify` | So số nút / cạnh theo từng cặp loại trong Neo4j với `summary.json`; báo cạnh nối sai loại, synonym còn tag |

- PrimeKG: ràng buộc duy nhất `id` theo từng label, cạnh `MATCH` theo `(Label {id})` nên không nối nhầm loại. Quan hệ chưa có cạnh nào thì `CREATE` (nhanh), đã có thì `MERGE`.
- `reset=1` xoá `:Entity` / `:DermoTerm` **kể cả cạnh và nút `DOC` từ sách** → phải chạy lại `graph_index` cho từng sách. Xoá theo đợt, cạnh trước nút (xoá thẳng nút thuốc có hàng trăm nghìn cạnh `DRUG_DRUG` làm Neo4j hết bộ nhớ giao dịch).
- Chạy lại không reset là upsert; **chưa thử** trên toàn bộ dữ liệu (nhánh `MERGE` của `DRUG_DRUG` có thể chậm).
- Chi tiết, cấu trúc thư mục và nguồn: `core/graph_base/README.md`.
- Chưa chuyển sang: `reset-and-gen-data.sh` (prod) vẫn gọi loader cũ trong `data_ingest/01_normalize/scripts/`.
- Không có bước tự kiểm tra lúc khởi động agent; quên nạp thì chỉ phát hiện khi query rỗng hoặc `graph_index` bỏ cạnh.

### 2.2 Cạnh từ sách (pipeline, mỗi tài liệu)

- Bước **`graph`** (`stages/graph.py`): LLM đọc từng mục sách theo "ô" (slot) trong `GraphSchema`, ra triple; thực thể được khớp vào nút PrimeKG / DermO / nút `doc_*` → `triples.jsonl`, người duyệt sửa qua override.
- Bước **`graph_index`** (`stages/graph_index.py` → `DocumentGraphService.replace_document`): chỉ lưu triple `status == "ok"` đã duyệt.
  - Đầu `dermo`: coi như có sẵn. Đầu `primekg`: `existing_nodes` hỏi Neo4j theo cặp `(loại, id)` (label loại + `id`); cặp đã có thì dùng, chưa có thì lấy từ lexicon rồi tạo nút,
    không có ở cả hai thì bỏ triple. Id trùng ở loại khác không còn chặn nhau (đồ thị mới có 8.822 id dùng chung nhiều loại).
  - Nút và cạnh luôn `MERGE` / `MATCH` theo `(label loại, id)`; nút mới thêm `:Entity`; nút DermO mới có `is_obsolete=false`, `synonyms/xrefs/alt_ids=[]` (thiếu `is_obsolete` thì `lookup_dermo_term` bỏ sót).
  - Lexicon của bước `graph` đọc `graph_base/data/build` (`GRAPH_LEXICON_DIR`): chỉ gồm nút thật sự có trong đồ thị nền; nút gộp `MONDO_grouped` xếp sau bệnh thường khi trùng tên.
  - Nạp theo kiểu thay thế: xoá cạnh/nút cũ của chính `document_id` rồi `MERGE` lại, nên chạy lại bước này không nhân đôi. Cạnh gộp theo (loại quan hệ, hai đầu, tài liệu).
  - Xoá tài liệu thì gỡ cạnh `document_id` đó và nút mà `added_by` rỗng và không còn cạnh nào.
- Xoá một quan hệ khỏi danh mục: `delete_relation_edges` xoá mọi cạnh `source='DOC'` loại đó, **không** đụng cạnh gốc cùng loại.

## 3. Cơ chế khai thác (agent)

Truy cập Neo4j qua `KnowledgeGraphService` (`app/services/knowledge_graph_service.py`); mọi truy vấn tự thêm tham số `edge_sources = settings.KG_EDGE_SOURCES`.

### 3.1 Nguồn cạnh: `KG_EDGE_SOURCES`
Mặc định `["KG"]`: agent **chỉ thấy cạnh gốc**. Thêm `"DOC"` mới cho agent dùng cạnh trích từ sách (kèm `source_ref` để trích nguồn). Quan hệ mới của bác sĩ vào được đồ thị nhưng agent chưa truy vấn tới nếu không có trong `RELATION_LABELS`.

### 3.2 Giải quyết thực thể (`resolve_seeds`)
1. LLM (`extract_entities`) trích thực thể từ câu hỏi, dịch sang tiếng Anh y khoa kèm tên tiếng Việt.
2. `exact_dermo`: tra `:DermoTerm` khớp **chính xác** tên hoặc synonym (`_LOOKUP_QUERY`, ưu tiên khớp chính xác trước `CONTAINS`) → lấy `dermo_id` và gom tên + từ đồng nghĩa.
3. Dùng tập tên đó khớp `:Entity` (`disease` / `effect/phenotype` / `drug`) bằng `EXACT_SEED_QUERY`; không có thì `LOOSE_SEED_QUERY` (`CONTAINS`, tối đa 3). Kết quả là các **seed** (`elementId`).

Đây là cầu nối giữa hai đồ thị: DermO chuẩn hoá tên, PrimeKG cung cấp quan hệ.

### 3.3 Tool `knowledge_graph_query(intent, entities, top_k)`
Mỗi `intent` ứng với một câu Cypher cố định (`agent/tools/hybrid_retrieval/kg_templates.py`), chỉ duyệt đúng nhóm quan hệ cần:

| intent | Quan hệ duyệt |
|---|---|
| `disease_overview` | PHENOTYPE_POSITIVE, TYPICAL_LOCATION, RISK_FACTOR, RED_FLAG, DISEASE_DISEASE (3 quan hệ BYT hiện không còn dữ liệu) |
| `symptoms_of_disease` | PHENOTYPE_POSITIVE / NEGATIVE |
| `red_flags_risk` | RED_FLAG, RISK_FACTOR, TYPICAL_LOCATION (cả ba hiện không còn dữ liệu → trả rỗng) |
| `treatments` | INDICATION, OFF_LABEL_USE |
| `contraindications` | CONTRAINDICATION |
| `drug_profile` | INDICATION, CONTRAINDICATION, OFF_LABEL_USE, DRUG_EFFECT, DRUG_DRUG |
| `diseases_with_symptom`, `differential` | đường riêng: chấm điểm ứng viên bệnh qua 1-hop (triệu chứng, bệnh liên quan, chỉ định) và 2-hop qua phenotype chung (trần điểm `_SHARED_CAP`); loại chính bệnh đầu vào, có `_EXPAND_MAPPED` để đi qua cạnh "mapped to primekg" (cạnh này do bản BYT cũ tạo, đồ thị mới không còn) |

- Quy tắc chung: cạnh duyệt không phân biệt chiều; lọc `edge_sources`; `ORDER BY m.name` trước `collect` để cắt `per_relation` ổn định; kết quả xếp theo thứ tự `RELATION_LABELS`; mỗi dữ kiện trả `{intent, relation, text}` kèm `refs` (trang sách) nếu là cạnh DOC.
- Intent cần loại thực thể nhất định (`needs`); không khớp thì trả ghi chú cho agent.

### 3.4 Các nơi khác dùng đồ thị
- `lookup_dermo_term` (`search_dermo_terms`): tra định nghĩa, từ đồng nghĩa, thuật ngữ cha của DermO.
- `reasoning.py` → `discriminating_questions`: với ≥2 bệnh đang cân nhắc, lấy tập `DISEASE_PHENOTYPE_POSITIVE` từng bệnh, chọn phenotype phân biệt tốt (tính `degree` của phenotype) để agent hỏi người dùng tiếp.
- `hybrid_retrieval`: nhánh KG dùng `extract_entities` để mở rộng query BM25 bằng tên chuẩn.

## 4. Lưu ý
- Id PrimeKG chỉ duy nhất theo loại (8.822 id dùng chung cho nhiều loại), nên mọi truy vấn viết tay phải kèm label loại (`:Disease {id}`), không chỉ `:Entity {id}`.
- Chuỗi Cypher ghép label / relationship type trực tiếp; chỉ an toàn vì giá trị đến từ dữ liệu cố định hoặc regex ở `GraphSchemaService`. Không nới lỏng.
- Đổi danh mục quan hệ không tự đánh `stale` tài liệu; muốn áp dụng phải chạy lại `graph` của từng sách.
- Đồ thị nền nạp ngoài pipeline và không có kiểm tra bắt buộc; quên `make kg-load` thì agent trả rỗng.
