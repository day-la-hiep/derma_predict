import asyncio
import logging
from datetime import timedelta

from derma_shared.minio_client import MinioClient
from minio.error import S3Error

logger = logging.getLogger(__name__)

_PRESIGNED_URL_TTL = timedelta(hours=1)


class AttachmentStore:
    """Chỉ đọc bucket ảnh đính kèm: lấy bytes để phân loại ảnh và tạo link tạm cho ảnh ca bệnh."""

    def __init__(self, minio: MinioClient, bucket: str) -> None:
        self._minio = minio
        self._bucket = bucket

    async def get_object_bytes(self, key: str) -> bytes | None:
        try:
            return await asyncio.to_thread(self._minio.get_bytes, self._bucket, key)
        except S3Error as exc:
            # lỗi khác NoSuchKey (AccessDenied, sai khoá...) là lỗi cấu hình MinIO: log để phân biệt với key sai/đã xoá
            logger.warning("get_object failed: code=%s key=%r bucket=%r", exc.code, key, self._bucket)
            return None

    def presigned_url(self, key: str) -> str:
        return self._minio.presigned_get_url(self._bucket, key, _PRESIGNED_URL_TTL)
