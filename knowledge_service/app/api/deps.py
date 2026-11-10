from functools import cache
from pathlib import Path

import httpx
import jwt
from derma_shared.errors import AuthenticationError, ForbiddenError
from derma_shared.minio_client import MinioClient
from derma_shared.rabbitmq_client import RabbitMQClient
from derma_shared.redis_client import RedisClient
from derma_shared.security import decode_token
from fastapi import Header, Request

from app.config.settings import settings
from app.infra.docling_client import DoclingClient
from app.infra.embedding_client import EmbeddingClient
from app.infra.neo4j_client import Neo4jClient
from app.infra.postgres_client import PostgresClient
from app.infra.qdrant_client import QdrantVectorClient
from app.repositories.document_repository import DocumentRepository
from app.repositories.graph_schema_repository import GraphSchemaRepository
from app.services.case_index_service import CaseIndexService
from app.services.document_graph_service import DocumentGraphService
from app.services.document_ingest_pipeline_service import DocumentIngestPipelineService
from app.services.document_service import DocumentService
from app.services.file_store_service import FileStoreService
from app.services.graph_schema_service import GraphSchemaService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.patient_journey_service import PatientJourneyService
from app.services.retrieval_service import RetrievalService


@cache
def get_postgres_client() -> PostgresClient:
    return PostgresClient.from_settings()


@cache
def get_redis_client() -> RedisClient:
    return RedisClient.from_settings()


@cache
def get_rabbitmq_client() -> RabbitMQClient:
    return RabbitMQClient()


@cache
def get_qdrant_client() -> QdrantVectorClient:
    return QdrantVectorClient.from_settings()


@cache
def get_neo4j_client() -> Neo4jClient:
    return Neo4jClient.from_settings()


@cache
def get_minio_client() -> MinioClient:
    return MinioClient.from_settings()


@cache
def get_docling_client() -> DoclingClient:
    return DoclingClient()


@cache
def get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient()


@cache
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(get_qdrant_client())


@cache
def get_knowledge_graph_service() -> KnowledgeGraphService:
    return KnowledgeGraphService(get_neo4j_client())


@cache
def get_case_index_service() -> CaseIndexService:
    return CaseIndexService(get_qdrant_client(), get_embedding_client())


@cache
def get_patient_journey_service() -> PatientJourneyService:
    return PatientJourneyService(get_neo4j_client())


@cache
def get_clinical_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.CLINICAL_URL, headers={"X-Internal-Key": settings.INTERNAL_API_KEY}, timeout=30)


@cache
def get_document_file_store() -> FileStoreService:
    return FileStoreService(get_minio_client(), settings.MINIO_DOCUMENTS_BUCKET)


@cache
def get_document_repository() -> DocumentRepository:
    return DocumentRepository(get_document_file_store(), get_postgres_client().sync_session_factory)


@cache
def get_graph_schema_service() -> GraphSchemaService:
    return GraphSchemaService(GraphSchemaRepository(get_postgres_client().sync_session_factory))


@cache
def get_document_graph_service() -> DocumentGraphService:
    return DocumentGraphService(
        get_document_repository(), get_neo4j_client(), Path(settings.GRAPH_LEXICON_DIR),
        schema=lambda: get_graph_schema_service().schema(include_disabled=True),
    )


@cache
def get_document_service() -> DocumentService:
    return DocumentService(
        get_document_repository(), get_qdrant_client(), settings.QDRANT_DOCUMENT_COLLECTION,
        graph=get_document_graph_service(),
    )


@cache
def get_document_ingest_pipeline_service() -> DocumentIngestPipelineService:
    return DocumentIngestPipelineService(
        get_document_service(),
        get_document_repository(),
        docling=get_docling_client(),
        embedding=get_embedding_client(),
        rabbitmq=get_rabbitmq_client(),
        redis=get_redis_client(),
        graph=get_document_graph_service(),
        graph_schema=get_graph_schema_service(),
    )


async def close_clients() -> None:
    for get_client in (get_postgres_client, get_redis_client, get_rabbitmq_client, get_qdrant_client, get_neo4j_client):
        if get_client.cache_info().currsize:
            await get_client().close()


def require_admin(request: Request) -> dict:
    """Xác thực bằng claim trong JWT do identity phát; knowledge không có bảng user để tra lại."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AuthenticationError("Yêu cầu đăng nhập (thiếu Authorization Bearer header).")
    try:
        claims = decode_token(auth.removeprefix("Bearer ").strip())
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Access token không hợp lệ hoặc đã hết hạn.") from exc
    if claims.get("type") != "access" or not claims.get("sub"):
        raise AuthenticationError("Token không phải là access token.")
    if claims.get("role") != "admin":
        raise ForbiddenError("Bạn không có quyền truy cập chức năng này (yêu cầu vai trò: admin).")
    return claims


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise ForbiddenError("Thiếu hoặc sai X-Internal-Key.")
