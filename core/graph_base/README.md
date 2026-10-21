# graph_base: dựng 2 đồ thị nền từ nguồn gốc

| Đồ thị | Nguồn | Neo4j |
|---|---|---|
| Quan hệ | PrimeKG `kg.csv` (Harvard Dataverse, DOI 10.7910/DVN/IXA7BM, v2, CC0) | `:Entity` + label loại (`Disease`, `EffectPhenotype`, `Drug`, `GeneProtein`, `Exposure`) |
| Ontology | DermO v1.19 `dermatology.obo` (GitHub `dermatology-ontology/dermatology`) | `:DermoTerm` |

Hai nhánh độc lập, không nối nhau. Schema, số liệu và cách agent khai thác: `docs/module/knowledge-graph.md`.

```bash
make kg-download      # data/raw/: kg.csv (md5), dermatology.obo (+ .meta.json: url, sha256, ngày tải)
make kg-build         # data/build/{primekg,dermo}/: nodes.csv, edges.csv, terms.json, summary.json
make kg-load          # nạp Neo4j (idempotent); reset=1 xoá :Entity/:DermoTerm trước, kể cả cạnh/nút DOC từ sách
make kg-verify        # so Neo4j với summary.json, thoát lỗi nếu lệch
```

```
graph_base/
  _common.py          tải + checksum, kết nối Neo4j, xoá theo đợt
  primekg/            schema.py (5 loại nút, 11 quan hệ được giữ)  download.py  build.py  load.py
  dermo/              download.py  build.py  load.py
  verify.py
  data/               raw/ và build/, không commit
```

- PrimeKG không lọc theo da liễu; chỉ bỏ giải phẫu, pathway, bioprocess/molfunc/cellcomp, `protein_protein`, `drug_protein`. Id chỉ duy nhất theo loại nên ràng buộc đặt trên từng label.
- DermO nạp cả `IS_A` lẫn quan hệ OBO (`HAS_SYMPTOM`, `RESULTS_IN`, `ASSOCIATED_WITH`, `DERIVES_FROM`); tag `<new synonym>` đã bỏ khỏi synonym.
- `reset=1` xoá cả phần mở rộng từ sách → chạy lại `graph_index` từng tài liệu.
- Mặc định đọc `NEO4J_*` từ `core/.env` qua `app.config.settings`. Chạy trong thư mục `core/` (target Makefile đã `cd core`).
- Chưa chuyển: `reset-and-gen-data.sh` (prod), lexicon của bước `graph`, dọn script cũ trong `data_ingest/`.
