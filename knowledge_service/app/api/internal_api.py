from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import (
    get_document_graph_service,
    get_knowledge_graph_service,
    get_patient_fact_linker,
    get_retrieval_service,
    require_internal_key,
)
from app.dto.api import ApiResponse
from app.services.document_graph_service import DocumentGraphService
from app.services.kg_intent_service import INTENTS, run_intent
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.patient_fact_linker import PatientFactLinker
from app.services.patient_graph_context_service import EDGE_SOURCES, get_drug_notes, rank_diseases, resolve_node_pairs
from app.services.retrieval_corpus import CORPORA, DOCUMENT_CORPUS
from app.services.retrieval_service import RetrievalFilter, RetrievalService

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_key)])

Retrieval = Annotated[RetrievalService, Depends(get_retrieval_service)]
DocGraph = Annotated[DocumentGraphService, Depends(get_document_graph_service)]
KnowledgeGraph = Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)]
Linker = Annotated[PatientFactLinker, Depends(get_patient_fact_linker)]


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


class LinkMention(BaseModel):
    text: str
    text_en: str = ""
    object_type: Literal["effect/phenotype", "disease", "drug", "exposure", "dermo"]  # = LINKABLE_TYPES


class LinkCandidatesInput(BaseModel):
    mentions: list[LinkMention] = Field(max_length=50)
    limit: int = Field(default=6, ge=1, le=20)


class DiscriminatingQuestionsInput(BaseModel):
    diseases: list[str] = []
    disease_ids: list[str] | None = None  # có thì bỏ bước tra tên, dùng cạnh KG + DOC như agent v3
    known_phenotype_ids: list[str] | None = None
    top_k: int = Field(default=3, ge=1, le=5)


class NodeRef(BaseModel):
    type: Literal["effect/phenotype", "disease", "drug", "exposure"]
    id: str


class RankDiseasesInput(BaseModel):
    present: list[NodeRef] = Field(max_length=50)
    absent: list[NodeRef] = Field(default_factory=lambda: list[NodeRef](), max_length=50)
    top_k: int = Field(default=12, ge=1, le=30)


class DiseaseIdsInput(BaseModel):
    names: list[str] = Field(max_length=10)


class DiseaseProfileInput(BaseModel):
    disease_ids: list[str] = Field(max_length=20)


class DrugNotesInput(BaseModel):
    drugs: list[NodeRef] = Field(max_length=20)
    symptoms: list[NodeRef] = Field(default_factory=lambda: list[NodeRef](), max_length=50)
    disease_names: list[str] = Field(default_factory=lambda: list[str](), max_length=20)


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
    if body.disease_ids:
        return ApiResponse(data=await kg.discriminating_questions(
            [], body.known_phenotype_ids, body.top_k, disease_ids=body.disease_ids, edge_sources=EDGE_SOURCES))
    return ApiResponse(data=await kg.discriminating_questions(body.diseases, body.known_phenotype_ids, body.top_k))


@router.post("/kg/link-candidates", response_model=ApiResponse[list[dict[str, Any]]])
async def get_link_candidates(body: LinkCandidatesInput, linker: Linker) -> ApiResponse[list[dict[str, Any]]]:
    return ApiResponse(data=[await linker.find_link_candidates(m.text, m.text_en, m.object_type, body.limit) for m in body.mentions])


@router.post("/kg/rank-diseases", response_model=ApiResponse[list[dict[str, Any]]])
async def post_rank_diseases(body: RankDiseasesInput, kg: KnowledgeGraph) -> ApiResponse[list[dict[str, Any]]]:
    nodes = await resolve_node_pairs(kg, [n.model_dump() for n in [*body.present, *body.absent]])
    present = [nodes[(n.type, n.id)]["eid"] for n in body.present if (n.type, n.id) in nodes]
    absent = [nodes[(n.type, n.id)]["eid"] for n in body.absent if n.type == "effect/phenotype" and (n.type, n.id) in nodes]
    return ApiResponse(data=await rank_diseases(kg, present, absent, body.top_k))


@router.post("/kg/disease-ids", response_model=ApiResponse[dict[str, list[str]]])
async def post_disease_ids(body: DiseaseIdsInput, kg: KnowledgeGraph) -> ApiResponse[dict[str, list[str]]]:
    return ApiResponse(data={name: await kg.disease_ids_for(name) for name in body.names})


@router.post("/kg/disease-profile", response_model=ApiResponse[dict[str, Any]])
async def post_disease_profile(body: DiseaseProfileInput, kg: KnowledgeGraph) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(data=await kg.get_disease_profiles(body.disease_ids, EDGE_SOURCES))


@router.post("/kg/drug-notes", response_model=ApiResponse[list[str]])
async def post_drug_notes(body: DrugNotesInput, kg: KnowledgeGraph) -> ApiResponse[list[str]]:
    nodes = await resolve_node_pairs(kg, [n.model_dump() for n in [*body.drugs, *body.symptoms]])
    drugs = [nodes[(n.type, n.id)]["eid"] for n in body.drugs if (n.type, n.id) in nodes]
    symptoms = [nodes[(n.type, n.id)]["eid"] for n in body.symptoms if (n.type, n.id) in nodes]
    return ApiResponse(data=await get_drug_notes(kg, drugs, symptoms, body.disease_names))
