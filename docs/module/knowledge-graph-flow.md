# Flow đồ thị tri thức: từ nguồn gốc, qua trích xuất từ sách, đến lúc agent truy vấn

Sơ đồ Mermaid. Nét đứt cam = **chưa làm**. Phần luồng trích tự động (khớp theo `(loại, id)`, lexicon từ `graph_base`) đã sửa trong code, chưa chạy với Neo4j thật. Schema và số liệu: [knowledge-graph.md](knowledge-graph.md).

## 1. Dựng đồ thị nền (`core/graph_base/`)

```mermaid
flowchart LR
    subgraph SRC["Nguồn gốc"]
        P1["PrimeKG kg.csv<br/>Harvard Dataverse"]
        D1["DermO dermatology.obo v1.19<br/>GitHub"]
    end

    P1 -- "make kg-download<br/>kiểm md5" --> P2["data/raw/primekg"]
    D1 -- "make kg-download<br/>ghi sha256" --> D2["data/raw/dermo"]

    P2 -- "make kg-build<br/>giữ 5 loại nút, 11 quan hệ<br/>bỏ cạnh trùng, dòng lỗi" --> P3["data/build/primekg<br/>nodes.csv, edges.csv, summary.json"]
    D2 -- "make kg-build<br/>parse OBO, bỏ tag new synonym" --> D3["data/build/dermo<br/>terms.json, summary.json"]

    P3 -- "make kg-load" --> N1[("Neo4j<br/>:Entity + Disease, Drug,<br/>EffectPhenotype, GeneProtein, Exposure")]
    D3 -- "make kg-load" --> N2[("Neo4j<br/>:DermoTerm<br/>IS_A, HAS_SYMPTOM, RESULTS_IN, ...")]

    N1 --> V{{"make kg-verify<br/>so số nút / cạnh theo cặp loại<br/>với summary.json"}}
    N2 --> V
```

## 2. Trích quan hệ từ sách vào đồ thị (`document_ingest`)

```mermaid
flowchart TD
    PDF["PDF sách giáo khoa"] --> ING["ingest<br/>PDF → chữ theo trang"]
    ING --> TOC["toc<br/>AI đọc mục lục, người duyệt"]
    TOC --> CHK["chunks<br/>cắt đoạn theo mục lục"]
    CHK --> IDX["index<br/>embedding → Qdrant"]
    CHK --> GR

    subgraph GRAPHSTAGE["Bước graph: trích triple"]
        GR["LLM đọc từng mục sách<br/>theo slot trong GraphSchema"]
        LEX[("EntityLexicon<br/>khoá theo type + id")]
        GR --> LINK["khớp tên trong sách<br/>→ nút PrimeKG / DermO / doc_*"]
        LEX --> LINK
        LINK --> TRI["triples.jsonl"]
        TRI --> REV{"Người duyệt<br/>sửa qua override"}
    end

    REV -- "approve" --> GI

    subgraph WRITE["Bước graph_index: ghi Neo4j"]
        GI["chỉ lấy triple status = ok"]
        GI --> CHECK["kiểm nút đã có trong Neo4j"]
        CHECK --> RESET["xoá cạnh và nút cũ<br/>của document_id này"]
        RESET --> MERGE["MERGE nút mới + cạnh<br/>source = DOC, evidence, pages"]
        MERGE --> COUNT["đếm lại cạnh đã lưu<br/>lệch thì báo lỗi"]
    end

    COUNT --> NEO[("Neo4j<br/>đồ thị nền + cạnh DOC")]
    LEXSRC["graph_base/data/build<br/>nodes.csv, terms.json"] --> LEX
```

### Cách `graph_index` nhận diện nút (đã sửa)

```mermaid
flowchart LR
    subgraph OLD["Trước: coi Entity.id duy nhất toàn cục"]
        A1["existing_types<br/>trả id → type"] --> A2["MERGE Entity id"] --> A3["MATCH Entity id ... Entity id"]
    end
    subgraph NEW["Nay: theo label loại"]
        B1["existing_nodes<br/>cặp type + id"] --> B2["MERGE Label id<br/>SET :Entity"] --> B3["MATCH Label_x id ... Label_y id"]
    end
    OLD -->|"8.822 id dùng chung cho nhiều loại"| NEW
```

## 3. Hai đồ thị gặp nhau thế nào (lúc agent truy vấn)

Không có cạnh nối `:Entity` với `:DermoTerm`; cầu nối duy nhất là so khớp tên.

```mermaid
flowchart LR
    Q["Câu hỏi người dùng"] --> EX["extract_entities<br/>LLM trích + dịch sang tiếng Anh y khoa"]
    EX --> DM["exact_dermo<br/>tra DermoTerm khớp chính xác<br/>tên hoặc synonym"]
    DM -- "tên chuẩn + đồng nghĩa" --> SEED["EXACT_SEED_QUERY / LOOSE_SEED_QUERY<br/>khớp :Entity<br/>disease, phenotype, drug"]
    EX -- "tên gốc" --> SEED
    SEED --> CY["Cypher theo intent<br/>kg_templates.py"]
    CY --> FACT["dữ kiện + trích nguồn<br/>cạnh DOC kèm source_ref nếu bật KG_EDGE_SOURCES"]
    DM --> LK["lookup_dermo_term<br/>định nghĩa, đồng nghĩa, thuật ngữ cha"]
```

## Chú thích
- Chạy `make kg-load reset=1` xoá cả cạnh `DOC`; sau đó phải chạy lại bước `graph_index` cho từng sách.
- `GRAPH_LEXICON_DIR` mặc định trỏ `core/graph_base/data/build` (cần chạy `make kg-build` trước khi chạy bước `graph`).
- Cạnh `DOC` chỉ hiện với agent khi `KG_EDGE_SOURCES` có `DOC` (mặc định `["KG"]`).
