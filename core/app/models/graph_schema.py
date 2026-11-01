"""Loại thực thể và quan hệ do bác sĩ tự định nghĩa cho bước `graph`"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class GraphEntityType(Base):
    __tablename__ = "graph_entity_types"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    hint: Mapped[str] = mapped_column(Text)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class GraphRelation(Base):
    __tablename__ = "graph_relations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    slot_id: Mapped[str] = mapped_column(String(50), unique=True)
    relation_type: Mapped[str] = mapped_column(String(50), unique=True)
    topic: Mapped[str] = mapped_column(String(16))
    # có thể là loại core (không nằm trong DB) nên không dùng khoá ngoại; service kiểm tra khi tạo/xoá
    object_type: Mapped[str] = mapped_column(String(40))
    topic_is_head: Mapped[bool] = mapped_column(Boolean)
    title: Mapped[str] = mapped_column(String(100))
    display: Mapped[str] = mapped_column(String(100))
    hint: Mapped[str] = mapped_column(Text)
    entity_hint: Mapped[str] = mapped_column(Text, default="", server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
