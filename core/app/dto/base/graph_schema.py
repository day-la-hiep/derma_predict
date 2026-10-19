"""Bounded context Đồ thị tri thức: danh mục loại thực thể và quan hệ bước `graph` được phép trích từ tài liệu."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GraphEntityTypeDefinition(BaseModel):
    """Một loại thực thể (giá trị `type` của nút). Loại core nằm trong code (`pipeline/document_ingest/graph_schema.py::ENTITY_TYPES`,
    chỉ đọc); loại bác sĩ tự định nghĩa (`kg="doc"`) lưu ở `app/models/graph_schema.py::GraphEntityType`."""

    id: str
    builtin: bool
    kg: Literal["primekg", "dermo", "doc"]
    label: str  # label phụ của nút trong Neo4j
    title: str
    hint: str  # cách ghi tên thực thể, đưa thẳng vào prompt cho LLM
    case_sensitive: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GraphRelationDefinition(BaseModel):
    """Một quan hệ có thể trích: một ô (`slot_id`) LLM điền ứng với một relationship type Neo4j. Quan hệ core nằm trong code
    (`SLOTS`, chỉ đọc); quan hệ bác sĩ tự định nghĩa (`kg="doc"`) lưu ở `app/models/graph_schema.py::GraphRelation`."""

    id: str | None = None  # None với quan hệ core
    builtin: bool
    slot_id: str
    relation_type: str
    kg: Literal["primekg", "dermo", "doc"]
    topic: Literal["disease", "drug"]  # loại chủ đề của mục sách mà ô này áp dụng
    object_type: str  # loại thực thể của đầu còn lại
    topic_is_head: bool  # True: chủ đề -> đầu kia; False: đầu kia -> chủ đề
    title: str
    display: str  # `display_relation` ghi lên cạnh
    hint: str  # mô tả ô cho LLM
    entity_hint: str = ""
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
