from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import (
    get_document_graph_service,
    get_knowledge_graph_service,
    get_retrieval_service,
    require_internal_key,
)
from app.dto.common import ApiResponse
from app.services.document_graph_service import DocumentGraphService
from app.services.kg_intent_service import INTENTS, run_intent
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.retrieval_corpus import CORPORA, DOCUMENT_CORPUS
from app.services.retrieval_service import RetrievalFilter, RetrievalService

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_key)])

Retrieval = Annotated[RetrievalService, Depends(get_retrieval_service)]
DocGraph = Annotated[DocumentGraphService, Depends(get_document_graph_service)]
KnowledgeGraph = Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)]


class SearchInput(BaseModel):
    corpus: Literal["document", "finalize_report"] = "document"
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    eq: dict[str, Any] = {}  # lọc bằng payload, ví dụ {"document_id": "..."}


class GraphSearchInput(BaseModel):
    names: list[str]
    limit: int = Field(default=20, ge=1, le=100)


class DocumentGraphQueryInput(BaseModel):
    entity: str
    relation: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class KgIntentInput(BaseModel):
    intent: str
    entities: list[str]
    limit: int = Field(default=10, ge=1, le=50)
    translate: bool = True


class KgIntentOutput(BaseModel):
    facts: list[dict[str, str]]
    notes: list[str]
    resolved: dict[str, Any]


class DiscriminatingQuestionsInput(BaseModel):
    diseases: list[str]
    known_phenotype_ids: list[str] | None = None
    top_k: int = Field(default=3, ge=1, le=5)


@router.post("/search/semantic", response_model=ApiResponse[list[dict[str, Any]]])
async def search_semantic(body: SearchInput, retrieval: Retrieval) -> ApiResponse[list[dict[str, Any]]]:
    corpus = CORPORA[body.corpus]
    vector = await corpus.embed_query(body.query)
    points = await retrieval.dense(corpus, vector=vector, limit=body.limit, filter=RetrievalFilter(eq=body.eq))
    return ApiResponse(data=[p.payload for p in points if p.payload])


@router.post("/search/bm25", response_model=ApiResponse[list[dict[str, Any]]])
async def search_bm25(body: SearchInput, retrieval: Retrieval) -> ApiResponse[list[dict[str, Any]]]:
    corpus = CORPORA[body.corpus]
    points = await retrieval.sparse(corpus, query=body.query, limit=body.limit, filter=RetrievalFilter(eq=body.eq))
    return ApiResponse(data=[p.payload for p in points if p.payload])


@router.post("/search/graph", response_model=ApiResponse[list[dict[str, Any]]])
async def search_by_graph(body: GraphSearchInput, graph: DocGraph, retrieval: Retrieval) -> ApiResponse[list[dict[str, Any]]]:
    chunk_ids = await graph.chunks_for_entities(body.names, body.limit)
    return ApiResponse(data=await retrieval.fetch(DOCUMENT_CORPUS, chunk_ids))


@router.post("/graph/document-query", response_model=ApiResponse[list[dict[str, Any]]])
async def query_document_graph(body: DocumentGraphQueryInput, graph: DocGraph) -> ApiResponse[list[dict[str, Any]]]:
    return ApiResponse(data=await graph.query_document_graph(body.entity, body.relation, body.limit))


@router.post("/kg/intent", response_model=ApiResponse[KgIntentOutput])
async def run_kg_intent(body: KgIntentInput, kg: KnowledgeGraph) -> ApiResponse[KgIntentOutput]:
    facts, notes, resolved = await run_intent(kg, body.intent, body.entities, body.limit, body.translate)
    return ApiResponse(data=KgIntentOutput(facts=facts, notes=notes, resolved=resolved))


@router.get("/kg/intents", response_model=ApiResponse[list[str]])
async def list_kg_intents() -> ApiResponse[list[str]]:
    return ApiResponse(data=list(INTENTS))


@router.post("/kg/discriminating-questions", response_model=ApiResponse[dict[str, Any]])
async def get_discriminating_questions(body: DiscriminatingQuestionsInput, kg: KnowledgeGraph) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(data=await kg.discriminating_questions(body.diseases, body.known_phenotype_ids, body.top_k))
