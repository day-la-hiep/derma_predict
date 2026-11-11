import json
import unittest
from types import SimpleNamespace

import jwt
from derma_shared.settings import settings
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.citation_api import router
from app.api.deps import get_document_repository
from app.api.exception_handler import register_exception_handlers
from app.services.file_store_service import FileStoreService
from tests.pipeline.document_ingest.memory_infra import MemoryMinio


def create_access_token(sub: str, role: str) -> str:
    return jwt.encode({"sub": sub, "role": role, "type": "access"}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class SignedMinio(MemoryMinio):
    def presigned_get_url(self, bucket: str, key: str, expires) -> str:  # noqa: ANN001
        return f"http://minio.test/{bucket}/{key}?ttl={int(expires.total_seconds())}"


def _chunk(seq: int, ps: int, pe: int, cid: str) -> dict:
    return {"chunk_id": cid, "seq": seq, "toc_path": ["Chương 5", "Chàm"], "page_start": ps, "page_end": pe, "page_printed_start": ps - 10, "page_printed_end": pe - 10, "text": f"văn bản đầy đủ {cid}"}


class FakeRepo:
    def __init__(self) -> None:
        self.minio = SignedMinio()
        self.files = FileStoreService(self.minio, "docs")

    def exists(self, document_id: str) -> bool:
        return document_id == "d1"

    def get_title(self, document_id: str) -> str:
        return "Sách da liễu"

    def files_for(self, document_id: str) -> FileStoreService:
        return self.files.scoped(f"document/{document_id}/")


class CitationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = FakeRepo()
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_document_repository] = lambda: self.repo
        self.c = TestClient(app)
        self.doctor = {"Authorization": f"Bearer {create_access_token('doc-1', 'doctor')}"}

    def _seed(self) -> None:
        self.repo.minio.put_bytes("docs", "document/d1/source.pdf", b"%PDF-1.4", "application/pdf")
        rows = [_chunk(i, 10 + i, 10 + i, f"c{i}") for i in range(1, 15)]
        self.repo.minio.put_bytes("docs", "document/d1/chunks.jsonl", "\n".join(json.dumps(r) for r in rows).encode())

    def test_requires_doctor_or_admin(self) -> None:
        self.assertEqual(self.c.get("/api/v1/citations/documents/d1/source-url").status_code, 401)
        patient = {"Authorization": f"Bearer {create_access_token('u-1', 'patient')}"}
        self.assertEqual(self.c.get("/api/v1/citations/documents/d1/source-url", headers=patient).status_code, 403)

    def test_source_url_is_presigned_and_404_when_missing(self) -> None:
        self.assertEqual(self.c.get("/api/v1/citations/documents/d1/source-url", headers=self.doctor).status_code, 404)  # chưa có source.pdf
        self.assertEqual(self.c.get("/api/v1/citations/documents/zzz/source-url", headers=self.doctor).status_code, 404)
        self._seed()
        data = self.c.get("/api/v1/citations/documents/d1/source-url?page=7", headers=self.doctor).json()["data"]
        self.assertEqual((data["title"], data["page"]), ("Sách da liễu", 7))
        self.assertTrue(data["url"].startswith("http://minio.test/docs/document/d1/source.pdf?ttl="))

    def test_passages_overlap_pages_mark_cited_and_cap_at_ten(self) -> None:
        self._seed()
        r = self.c.get("/api/v1/citations/documents/d1/passages?page_start=12&page_end=13&chunk_id=c3", headers=self.doctor).json()["data"]
        self.assertEqual([p["chunk_id"] for p in r["passages"]], ["c2", "c3"])
        self.assertEqual([p["is_cited"] for p in r["passages"]], [False, True])
        self.assertEqual(r["passages"][1]["text"], "văn bản đầy đủ c3")  # toàn văn, không cắt
        self.assertEqual(r["passages"][1]["pages"], "tr.3")
        wide = self.c.get("/api/v1/citations/documents/d1/passages?page_start=1&page_end=99&chunk_id=c14", headers=self.doctor).json()["data"]["passages"]
        self.assertEqual(len(wide), 10)
        self.assertIn("c14", [p["chunk_id"] for p in wide])  # đoạn được trích luôn có mặt dù vượt giới hạn

    def test_unknown_document_is_404(self) -> None:
        self.assertEqual(self.c.get("/api/v1/citations/documents/zzz/passages?page_start=1", headers=self.doctor).status_code, 404)


if __name__ == "__main__":
    unittest.main()
