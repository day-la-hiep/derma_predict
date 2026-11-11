"""DTO Input cho danh mục loại thực thể / quan hệ của bước graph."""
from typing import Literal

from pydantic import BaseModel, Field


class EntityTypeCreate(BaseModel):
    id: str
    label: str
    title: str = Field(min_length=1, max_length=100)
    hint: str = Field(min_length=1, max_length=300)
    case_sensitive: bool = False


class EntityTypeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    hint: str | None = Field(default=None, min_length=1, max_length=300)
    case_sensitive: bool | None = None


class RelationCreate(BaseModel):
    relation_type: str
    topic: Literal["disease", "drug"]
    object_type: str
    topic_is_head: bool = True
    title: str = Field(min_length=1, max_length=100)
    display: str = Field(default="", max_length=100)  # rỗng = dùng `title`
    hint: str = Field(min_length=1, max_length=300)
    entity_hint: str = Field(default="", max_length=300)
    enabled: bool = True


class RelationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    display: str | None = Field(default=None, min_length=1, max_length=100)
    hint: str | None = Field(default=None, min_length=1, max_length=300)
    entity_hint: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None
