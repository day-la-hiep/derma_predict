"""Loại thực thể và quan hệ do bác sĩ tự định nghĩa"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exception.errors import NotFoundError
from app.models.graph_schema import GraphEntityType, GraphRelation

SessionFactory = Callable[[], Session]


class GraphSchemaRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    @contextmanager
    def _tx(self) -> Iterator[Session]:
        with self._sessions() as s, s.begin():
            yield s

    # ---- loại thực thể ----
    def list_entity_types(self) -> list[GraphEntityType]:
        with self._sessions() as s:
            return list(s.scalars(select(GraphEntityType).order_by(GraphEntityType.created_at, GraphEntityType.id)))

    def get_entity_type(self, id_: str) -> GraphEntityType:
        with self._sessions() as s:
            row = s.get(GraphEntityType, id_)
            if row is None:
                raise NotFoundError(id_)
            return row

    def create_entity_type(self, **fields: Any) -> GraphEntityType:
        with self._tx() as s:
            row = GraphEntityType(**fields)
            s.add(row)
            s.flush()
            return row

    def update_entity_type(self, id_: str, **fields: Any) -> GraphEntityType:
        with self._tx() as s:
            row = s.get(GraphEntityType, id_)
            if row is None:
                raise NotFoundError(id_)
            for k, v in fields.items():
                setattr(row, k, v)
            s.flush()
            return row

    def delete_entity_type(self, id_: str) -> None:
        with self._tx() as s:
            row = s.get(GraphEntityType, id_)
            if row is None:
                raise NotFoundError(id_)
            s.delete(row)

    # ---- quan hệ ----
    def list_relations(self) -> list[GraphRelation]:
        with self._sessions() as s:
            return list(s.scalars(select(GraphRelation).order_by(GraphRelation.created_at, GraphRelation.id)))

    def get_relation(self, id_: str) -> GraphRelation:
        with self._sessions() as s:
            row = s.get(GraphRelation, id_)
            if row is None:
                raise NotFoundError(id_)
            return row

    def create_relation(self, **fields: Any) -> GraphRelation:
        with self._tx() as s:
            row = GraphRelation(**fields)
            s.add(row)
            s.flush()
            return row

    def update_relation(self, id_: str, **fields: Any) -> GraphRelation:
        with self._tx() as s:
            row = s.get(GraphRelation, id_)
            if row is None:
                raise NotFoundError(id_)
            for k, v in fields.items():
                setattr(row, k, v)
            s.flush()
            return row

    def delete_relation(self, id_: str) -> None:
        with self._tx() as s:
            row = s.get(GraphRelation, id_)
            if row is None:
                raise NotFoundError(id_)
            s.delete(row)
