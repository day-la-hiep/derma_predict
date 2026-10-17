from typing import Literal

from pydantic import BaseModel, Field

QuerySet = Literal["ragas_single_hop", "ragas_multi_hop", "external"]
QueryType = Literal["lay", "keyword", "drug"]


class ChunkRecord(BaseModel):
    chunk_id: str
    # chunk_id đổi khi ingest lại sách, hash nội dung thì không: dùng để ánh xạ lại qrels
    content_hash: str
    document_id: str
    document_title: str
    toc_path: list[str] = Field(default_factory=list)
    text: str
    context_text: str = ""


class Query(BaseModel):
    qid: str
    set: QuerySet
    text: str
    type: QueryType = "lay"
    reference: str | None = None  # câu trả lời mẫu do RAGAS sinh, để dành cho giai đoạn generation


class Qrel(BaseModel):
    qid: str
    chunk_id: str
    content_hash: str
    relevance: Literal[0, 1, 2]
    source: Literal["ragas", "human"]
    reviewer: str | None = None
    rationale: str = ""


class Hit(BaseModel):
    chunk_id: str
    rank: int
    score: float | None = None


class Run(BaseModel):
    qid: str
    system: str
    hits: list[Hit] = Field(default_factory=list)
    ranked_by: str | None = None
    latency_ms: float = 0.0
    notes: list[str] = Field(default_factory=list)
    error: str | None = None


class RunConfig(BaseModel):
    run_id: str
    snapshot: str
    systems: list[str]
    depth: int
    embedding_model: str
    reranker_model: str
    llm_model: str
    date: str
    git_commit: str = ""
