from functools import cache

import httpx
from derma_shared.minio_client import MinioClient
from derma_shared.redis_client import RedisClient

from app.clients import ClinicalClient, ConsultationClient, KnowledgeClient
from app.config.settings import settings
from app.infra.attachment_store import AttachmentStore


def _build_http(base_url: str, timeout: float = 30) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, headers={"X-Internal-Key": settings.INTERNAL_API_KEY}, timeout=timeout)


@cache
def get_redis_client() -> RedisClient:
    return RedisClient.from_settings()


@cache
def get_minio_client() -> MinioClient:
    return MinioClient.from_settings()


@cache
def get_attachment_store() -> AttachmentStore:
    return AttachmentStore(get_minio_client(), settings.MINIO_BUCKET)


@cache
def get_knowledge_client() -> KnowledgeClient:
    return KnowledgeClient(_build_http(settings.KNOWLEDGE_URL, timeout=60))


@cache
def get_clinical_client() -> ClinicalClient:
    return ClinicalClient(_build_http(settings.CLINICAL_URL))


@cache
def get_consultation_client() -> ConsultationClient:
    return ConsultationClient(_build_http(settings.CONSULTATION_URL))


async def close_clients() -> None:
    if get_redis_client.cache_info().currsize:
        await get_redis_client().close()
    for get_client in (get_knowledge_client, get_clinical_client, get_consultation_client):
        if get_client.cache_info().currsize:
            await get_client()._http.aclose()
