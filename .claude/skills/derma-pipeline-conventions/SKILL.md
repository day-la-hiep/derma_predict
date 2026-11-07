---
name: derma-pipeline-conventions
description: Conventions for the Derma document-ingest pipeline (`core/pipeline/document_ingest/` — PDF document → table-of-contents-anchored chunks → Qdrant, admin UI at /admin/documents) — the 6-stage model (ingest/toc/chunks/index + graph/graph_index → Neo4j), the pure-function stage contract, the `app/dto/base/document.py` business entities (`Document`/`DocumentChunk`/`DocumentTriple`/`DocumentStage`/`DocumentStageOverride`), where transformation logic vs infra clients vs persistence go, and how to add or modify a stage. Use whenever the user asks to add/modify a pipeline stage, touches `pipeline/document_ingest/`, `app/services/document_*.py`, `app/repositories/document_repository.py`, asks about document/book/TOC/chunk ingestion, or asks where document-ingest code should live — even if they don't say "pipeline" or "convention".
---

# Derma document-ingest pipeline (`pipeline/document_ingest/`) — conventions

Paths are relative to `core/`. Turns an uploaded PDF (currently: textbooks, `Document.type ==
"book"`) into table-of-contents-anchored chunks in Qdrant, reviewed stage-by-stage by a human via
`/admin/documents` (FE: `derma-fe-conventions`'s `features/document-pipeline/`). No CLI — Core records `running` and publishes to RabbitMQ, the Ingest Worker (`make ingest-worker`) runs each stage;
everything lives in Postgres (`documents`, `document_stages`,
`document_overrides`) + MinIO (`derma-documents` bucket) + Qdrant (`derma_document_chunks_v4`), never
on local disk except a PDF scratch copy.

Renamed from `book_ingest`/`Book*` on 2026-10-04 (see migration
`20261004_6e7b779ba7c1_rename_book_entities_to_document.py`) once `app/dto/base/document.py`'s
`Document` entity became generic across upload types, not just books — see
`derma-core-conventions`'s `dto/base` section. `type="book"` is still the only type this pipeline
processes; other `Document.type` values (`image`, `video`, `other`) are plain chat attachments with
no pipeline.

```
PDF → ingest (text/page)  → toc (LLM reads TOC, human reviews) → mapping (rule-based offset+anchor) → chunks → index (Qdrant)
```

| Stage | Module | Output (in MinIO `document/<document_id>/`) | LLM |
|---|---|---|---|
| `ingest` | `stages/step1_ingest.py` | `pages.jsonl` | no |
| `toc` | `stages/step2_toc.py` + `mapping.py` | `toc.auto.json` (machine), `toc.json` (+ overrides + offset + anchor) | reads a few dozen TOC pages |
| `chunks` | `stages/step3_chunks.py` | `chunks.jsonl`, `review/chunks.json` | no |
| `index` | `stages/step4_index.py` (+ `DocumentService`) | `index.json` + points in Qdrant | no (embedding via OpenRouter) |
| `graph` | `stages/step5_graph.py` + `graph_schema.py` + `graph_link.py` | `graph/units.json`, `graph/unmapped.json`, `triples.auto.jsonl` (machine), `triples.jsonl` (+ overrides) | split chunks into units by the smallest TOC node, LLM names the subject and fills slots, pick among match candidates |
| `graph_index` | `stages/step6_graph_index.py` (+ `DocumentGraphService`) | `graph_index.json` + edges `source='DOC'` in Neo4j | no |

`graph`/`graph_index` run parallel to `index` (both depend on `chunks`). Core relation types are PrimeKG/DermO; admins add their own via `/admin/graph-schema` (`GraphSchemaService`, tables
`graph_relations`/`graph_entity_types`, `kg="doc"`) — the runner passes the merged `schema` (`GraphSchema`, CORE_SCHEMA by default;
`graph` gets enabled relations only, `graph_index` all). The registry `pipeline/document_ingest/graph_schema.py` (`ENTITY_TYPES`, `SLOTS`) drives the prompt,
entity matching, Neo4j loading and the FE labels — **to add an entity type or relation, add it there** (plus
`RELATION_LABELS`/`ENTITY_LABELS` in FE `constants.ts`). Names are matched against `EntityLexicon` (the nodes of the base
graph — `nodes.csv` + DermO `terms.json` built by `core/graph_base`, loaded by `DocumentGraphService.lexicon()` from `settings.GRAPH_LEXICON_DIR`).
PrimeKG ids are unique only per node type, so nodes are always addressed by `(type, id)` / Neo4j label + id, never by `Entity.id` alone.
Reviewer overrides (stage `graph`): `rejected`, `relink` (per triple side, expanded to every triple with the same
term), `accepted_nodes` (new `doc_*` entities, only when `profile.graph.allow_new_entities`). Gotchas (PrimeKG id
collisions across node types, topic misclassification, `KG_EDGE_SOURCES`): `docs/module/knowledge-graph.md` / `knowledge-graph-flow.md`.

Stage order/deps live in `app/models/document_stage.py` (`STAGES`, `downstream()`) — the single
source of truth, shared by repository, runner, and API. `toc` does **not** depend on `ingest`:
reading the TOC only needs a handful of OCR'd pages, so a user can try it immediately without
waiting for the whole document. `mapping.py` (offset+anchor) is re-run on demand (`reapply`)
whenever the TOC changes or `pages.jsonl` becomes available — it's rule-based, cheap, no LLM.

States: `not_started → running → pending_review → approved`; `failed`/`cancelled` on error;
`stale` when an upstream stage reruns after this one already has a result. A stage only runs once
every dependency is `approved`.

## Business entities vs ORM vs wire DTO

Per `derma-core-conventions`'s `dto/base` rule, this pipeline has three layers for the same data,
and they are NOT the same class even when field sets overlap:

| Layer | Classes | Lives in |
|---|---|---|
| Business entity (source of truth) | `Document` (holds `source_file`/`ingested_file: File` + `chunks`), `DocumentChunk`, `DocumentStage`, `DocumentStageOverride`; `File` (shared, MinIO object: `file_name`, `storage_key`, `content_type`, `size`, `created_at`) | `app/dto/base/document.py`, `app/dto/base/shared.py` |
| ORM / Postgres schema | `Document`, `DocumentStage`, `DocumentOverride` | `app/models/document.py` |
| API wire contract (snake_case, same-meaning fields named as in `dto/base`) | `DocumentOutput`, `DocumentSummary`, `StageOutput`, `ChunkListOutput` (response) / `DocumentSettings`, `TocUpdate`, `RunStageInput` (request) | `app/dto/response/document.py`, `app/dto/request/document.py` |

`DocumentService` builds the `dto/base` entity from the ORM row first (`_document()`,
`_process_stages()`), then maps entity → wire DTO (`_stage_output()`) before returning from an
endpoint — don't skip the entity step and build the wire DTO directly from the ORM row. The ORM
class is also literally named `Document`/`DocumentStage`/`DocumentOverride` (same names as the
entity layer, different module) — `app/services/document_service.py` doesn't import both at once,
so there's no clash there, but if a future change needs both in one file, alias the ORM import
(`from app.models.document import Document as DocumentOrm`).

## Three-layer split (this is the part people get wrong)

> User's own rule: "`pipeline/` chỉ tập trung logic xử lý/biến đổi dữ liệu" — pipeline is
> transformation logic ONLY. Everything else (clients, persistence, control flow) goes in `app/`.

| Layer | Owns | Lives in |
|---|---|---|
| **Transform** (pure functions: plain data in, plain data out) | `extract_pages`, `read_toc`, `build_toc`, `cut_chunks`, `embed_chunks`, `extract_triples`, `build_graph_payload`, `summarize_*`; typed data objects (`types.py`) | `pipeline/document_ingest/stages/step<N>_*.py`, `mapping.py` (offset+anchor, `build_toc`, `build_tree`), `types.py`, `textutil.py`, `profile.py` |
| **Infra clients** (generic, no document logic, one class per service) | MinIO (`app/infra/minio_client.py`), Qdrant (`qdrant_client.py`), LLM-returns-JSON (`llm_client.py`), Docling OCR (`docling_client.py`), embedding (`embedding_client.py`) | `app/infra/*_client.py` |
| **Stage IO** (read inputs from MinIO, call the pure function, write outputs, check dependencies) | `DocumentStageRunner` (`run_ingest`, `run_toc`, `run_chunks`, `index_document_chunks`, `run_graph`, `run_graph_index`, `reapply_toc`, `reapply_graph`), `StageRunState` (one run's document_id/options/profile/files/llm/progress/log) | `app/services/document_stage_runner.py` |
| **Persistence + control** | `DocumentRepository` (stateless — every method takes `document_id`), `DocumentOverrideRepository` (`DocumentRepository.overrides`), `DocumentService` (CRUD + chunk/Qdrant business logic; free functions `read_profile`, `get_local_pdf`), `DocumentIngestPipelineService` (state machine: check_runnable/begin/execute, queue, cancel, approve, reapply; dispatch tables `_runners`/`_reappliers`) | `app/repositories/document_repository.py`, `app/repositories/document_override_repository.py`, `app/services/document_service.py`, `app/services/document_ingest_pipeline_service.py` |
| **API/DTO** | `/admin/documents/*` routes, Pydantic contracts | `app/api/document_api.py`, `app/dto/request/document.py`, `app/dto/response/document.py` |
| **Instance lifecycle** | `get_document_service()`, `get_document_ingest_pipeline_service()` — lazy singleton per process | `app/api/deps.py` |

A pipeline module never imports `app.services`/`app.repositories` and never touches MinIO/Postgres;
`grep -rn "app\.services\|app\.repositories" pipeline/` (excluding tests) must stay empty. Tests call the
pure functions directly (`tests/test_pure_stages.py`) and drive the whole flow through the service with
`MemoryMinio` + SQLite + in-memory Qdrant + a fake embedder (no real service running — see Testing).

## Pure stage functions (`pipeline/document_ingest/stages/`)

Each `step<N>_*.py` exposes verb-named functions; there is no `run(ctx)` and no `StageContext`.

- Input/output are plain values or the typed models in `pipeline/document_ingest/types.py`
  (`PageRow`, `DoclingBlock`, `FigureDraft`, `TocEntry`, `TocAuto`, `TocDoc`, `TocNode`, `ChunkUnit`) and
  `app/dto/base/document.py` (`DocumentChunk`, `DocumentTriple`). Every `types.py` field has a
  `Field(description=...)` — add one for each new field. Models use `extra="ignore"` + defaults so old JSON
  in MinIO still loads; output files keep their names/format (`model_dump()` when writing, `model_validate()` when reading).
- Progress/log: optional callables `on_progress(done, total, message)` and `on_log(message)`. Cancel is the
  service's `on_progress` raising `StageCancelled` — the pipeline knows nothing about Redis.
- Missing dependency (LLM, Docling, embedding, lexicon, Neo4j): the runner checks and raises `StageError`;
  a pure function only raises `StageError` for bad data/options. Raise `StageError(msg)` for anything the
  reviewer can fix (shown verbatim in the UI); anything else becomes stage `failed`.
- Inputs that need a real file get a `Callable[[], Path]` (`run.get_pdf`) so the PDF is only downloaded when needed.
- Pure files use no logger-less `except`: every skipped/failed branch calls `logger.warning(...)`.

## `StageRunState` (service side, `app/services/document_stage_runner.py`)

`DocumentStageRunner.make_state(document_id, stage_id, options, llm, cancel)` builds the per-run object:
`document_id`, `stage_id`, `options`, `profile`, `files` (`FileStoreService` scoped to `document/<id>/`),
`llm` (None if the stage doesn't use it or `profile.llm.enabled=false`), `progress` (checks cancel, then writes
`document_stages.progress`, ~2/s), `log` (appends to `logs/`), `get_pdf`.
Overrides come from `repo.overrides.get(document_id, stage)`; the title from `repo.meta(document_id)`.

## Recipes

**Modify an existing stage** — change the pure function in `stages/step<N>_*.py` if it is
transformation (parsing, chunking rule, mapping logic). If it needs a new external capability
(another LLM call shape, a new file format), add/extend the matching `app/infra/*_client.py`, inject it
into `DocumentStageRunner.__init__` (wired in `DocumentIngestPipelineService.__init__` / `app/api/deps.py`),
add a dependency check in the runner, and pass the client into the pure function as a parameter.

**Add a stage** — add an entry to `STAGES` in `app/models/document_stage.py` (id, title, `deps`, `llm`,
`outputs`) — this drives dependency gating and the UI stepper. Add `stages/step<N>_<id>.py` with the pure
function(s), a `run_<id>` (+ `reapply_<id>` if it has overrides) on `DocumentStageRunner` that reads inputs,
calls the function and writes outputs, and register them in `_runners` / `_reappliers` in
`DocumentIngestPipelineService.__init__`. No `importlib`/`module` field any more.

**Add a document setting** — field in `Profile` (`app/models/document_profile.py`, Pydantic), read
it via `run.profile.<section>.<field>` in the runner and pass the value into the pure function; surface it in the settings UI
(`derma-fe-conventions`'s `features/document-pipeline/components/SettingsDialog.tsx` + `types.ts`).

**Add/change a `dto/base` field** (`Document`/`DocumentChunk`/`DocumentStage`/`DocumentStageOverride`)
— propose it and get user approval FIRST (`derma-core-conventions`'s `dto/base` gate), then update:
the entity in `app/dto/base/document.py` → the ORM model in `app/models/document.py` (new Alembic
migration) → `DocumentService`'s entity builders (`_document()`/`_process_stages()`) → the wire DTO
mapping (`_stage_output()`) → `app/dto/request|response/document.py` if the API shape changes.

**Add an admin-pipeline API field/endpoint** — DTO in `app/dto/request/document.py` (input) or
`app/dto/response/document.py` (output) → method on
`DocumentService`/`DocumentIngestPipelineService`/`DocumentStageRunner`/`DocumentRepository` (whichever owns that data)
→ route in `app/api/document_api.py`.
Mirror in FE's `features/document-pipeline/api.ts` + `hooks.ts` (see `derma-fe-conventions`).

## Storage layout (MinIO `document/<document_id>/`)

`source.pdf`, `page_img/p<N>.png` (whole-page renders for the admin page-preview, NOT extracted
embedded figures — see below), `pages.jsonl`, `toc.auto.json`, `toc.json`, `chunks.jsonl`,
`index.json`, `status.json`, `overrides/`, `review/`, `logs/`, `docling_parts/` (OCR checkpoint —
lets a killed `ingest` resume without re-OCRing finished pages). LLM cache: `_cache/llm/`. Chunks
are embedded via OpenRouter (qwen/qwen3-embedding-8b, 4096-dim) and upserted into Qdrant collection `derma_document_chunks_v4` (unnamed dense vector + sparse vector `bm25` encoded by `app/infra/bm25/` (tokenizer + stopwords + sparse; `text_language` per document in `Profile.indexing`, stored as payload `bm25_mode`) in `DocumentService.upsert_chunks`; Qdrant applies IDF, so the agent's keyword leg queries Qdrant directly — no in-memory index)
(`settings.QDRANT_DOCUMENT_COLLECTION`), payload carries `document_id`, `toc_path`, page,
`source_pdf`. Deleting a document deletes both the MinIO objects and the Qdrant points; rerunning
`index` replaces all of a document's points.

**Figures**: with the docling engine `ingest` keeps `figure` blocks, the runner stores each crop under
`figures/p<page>_<n>.png` and writes `figures.json` (entries match `DocumentFigure`; the pure function returns `FigureDraft`
with a relative `image_key`, the runner adds `image_file.storage_key`). `pdftotext` extracts no images and clears `figures/`.
Body-text block labels live in `textutil.BODY_LABELS`.

**Temp files**: PDF scratch copy at `/tmp/document_ingest_tmp/<document_id>/source.pdf` (`get_local_pdf`, reused while the size matches,
deleted with the document, never cleaned otherwise); `pdftoppm` page previews also use it.

## Concurrency & control flow

Chạy bước nằm ở **Ingest Worker** (`app/workers/document_ingest_worker.py`, `make ingest-worker`), tiến trình riêng như Agent
Worker. `start_stage` (Core, async) chạy `check_runnable` + `begin` (ghi `running`) rồi publish `document_ingest_queue`
(`{document_id, stage_id, options}`); worker consume, chạy `execute` trong thread (một bước một lần, semaphore) và tự ghi
kết quả/log. FE vẫn poll `GET /documents/{id}`. Dừng: `cancel_stage` đặt key Redis `document:ingest:cancel:{doc}:{stage}` +
publish channel `document:ingest:cancel`; worker set `threading.Event` (callback `progress` của `StageRunState` ném `StageCancelled`) hoặc đọc key
khi nhận message nếu bước còn nằm trong queue. Khởi động worker: purge queue + `DocumentService.fail_orphaned_runs()`
đánh dấu mọi bước `running` là `failed` (Core không còn biết bước nào thật sự chạy); `docling_parts/` giúp retry không OCR
lại. `run_stage` (đồng bộ) vẫn dùng cho test/script. `document_stages`/`document_overrides` ghi dưới Postgres row lock
(`FOR UPDATE`) vì Core và worker ghi đồng thời.

## Testing

`python -m unittest pipeline.document_ingest.tests.test_document_pipeline pipeline.document_ingest.tests.test_api pipeline.document_ingest.tests.test_storage_index pipeline.document_ingest.tests.test_graph pipeline.document_ingest.tests.test_graph_schema pipeline.document_ingest.tests.test_pure_stages` + `tests/test_reindex_qdrant.py`
— verified 2026-11-05, 89 tests pass. Uses `tests/memory_infra.py`'s `MemoryMinio` + a temp SQLite
file (in place of Postgres) + `QdrantClient(":memory:")` + a fake embedder — no real
MinIO/Postgres/Qdrant service needs to be running for these tests.

## Code style

Same as `derma-core-conventions` (Vietnamese comments explaining *why*, basic-mode pyright, async
I/O) — this pipeline lives inside `core/` and follows the same rules, including **no long module
docstring at the top of a file and no multi-line function docstrings** (at most one line; put a
non-obvious algorithm decision in a short comment next to the code, or in `README.md`). Stage-level prose
("sách", "cuốn sách") still refers to the book being processed — that's fine to leave as-is since
the pipeline genuinely only processes `type="book"` documents today; only identifiers (`book_id`,
`BookService`, table/route names) were renamed to `document_*`, not the descriptive Vietnamese text.
