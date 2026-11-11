"""Danh mục loại thực thể và quan hệ của bước graph: core (code) + do bác sĩ định nghĩa (Postgres)"""
import re
from collections.abc import Callable

from app.dto.base.graph_schema import GraphEntityTypeDefinition, GraphRelationDefinition
from app.dto.request.graph_schema import EntityTypeCreate, EntityTypeUpdate, RelationCreate, RelationUpdate
from app.exception.errors import ConflictError, InvalidError
from app.models.graph_schema import GraphEntityType, GraphRelation
from app.repositories.graph_schema_repository import GraphSchemaRepository
from pipeline.document_ingest.graph_schema import ENTITY_TYPES, SLOTS, TOPIC_TYPES, EntityType, GraphSchema, Relation, Slot

# id / label / relationship type được ghép thẳng vào câu Cypher nên chỉ nhận ký tự an toàn
_ENTITY_ID = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
_LABEL = re.compile(r"^[A-Z][A-Za-z0-9]{2,39}$")
_REL_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{2,49}$")
_RESERVED_LABELS = {"Entity", "DermoTerm"}


def _entity_def(row: GraphEntityType) -> GraphEntityTypeDefinition:
    return GraphEntityTypeDefinition(id=row.id, builtin=False, kg="doc", label=row.label, title=row.title, hint=row.hint,
                                     case_sensitive=row.case_sensitive, created_at=row.created_at, updated_at=row.updated_at)


def _relation_def(row: GraphRelation) -> GraphRelationDefinition:
    return GraphRelationDefinition(
        id=row.id, builtin=False, slot_id=row.slot_id, relation_type=row.relation_type, kg="doc", topic=row.topic,  # pyright: ignore[reportArgumentType]
        object_type=row.object_type, topic_is_head=row.topic_is_head, title=row.title, display=row.display, hint=row.hint,
        entity_hint=row.entity_hint, enabled=row.enabled, created_at=row.created_at, updated_at=row.updated_at)


def _slot(row: GraphRelation) -> Slot:
    rel = Relation("doc", row.relation_type, row.display, row.object_type, row.topic_is_head)
    return Slot(row.slot_id, row.topic, row.hint, (rel,), entity_hint=row.entity_hint)


class GraphSchemaService:
    def __init__(self, repository: GraphSchemaRepository) -> None:
        self._repo = repository

    # ---- đọc ----
    def list_entity_types(self) -> list[GraphEntityTypeDefinition]:
        core = [GraphEntityTypeDefinition(id=e.id, builtin=True, kg=e.kg, label=e.label, title=e.title, hint=e.hint,
                                          case_sensitive=e.case_sensitive) for e in ENTITY_TYPES.values()]
        return core + [_entity_def(r) for r in self._repo.list_entity_types()]

    def list_relations(self) -> list[GraphRelationDefinition]:
        core = [GraphRelationDefinition(builtin=True, slot_id=s.id, relation_type=r.type, kg=r.kg, topic=s.topic,  # pyright: ignore[reportArgumentType]
                                        object_type=r.object_type, topic_is_head=r.topic_is_head, title=r.display, display=r.display,
                                        hint=s.hint, entity_hint=s.entity_hint)
                for s in SLOTS for r in s.relations]
        return core + [_relation_def(r) for r in self._repo.list_relations()]

    def schema(self, include_disabled: bool = True) -> GraphSchema:
        types = dict(ENTITY_TYPES)
        for r in self._repo.list_entity_types():
            types[r.id] = EntityType(r.id, "doc", r.label, r.title, r.hint, r.case_sensitive)
        rows = [r for r in self._repo.list_relations() if include_disabled or r.enabled]
        return GraphSchema(types, [*SLOTS, *(_slot(r) for r in rows)])

    # ---- loại thực thể ----
    def create_entity_type(self, body: EntityTypeCreate) -> GraphEntityTypeDefinition:
        id_, label = body.id.strip(), body.label.strip()
        if not _ENTITY_ID.match(id_):
            raise InvalidError("Mã loại thực thể gồm chữ thường, số, gạch dưới; bắt đầu bằng chữ, dài 3–40 ký tự.")
        if not _LABEL.match(label):
            raise InvalidError("Label Neo4j viết kiểu PascalCase (vd AnatomySite), chỉ chữ và số, dài 3–40 ký tự.")
        if id_ in ENTITY_TYPES or label in _RESERVED_LABELS or label in {e.label for e in ENTITY_TYPES.values()}:
            raise InvalidError("Mã hoặc label trùng loại thực thể có sẵn của hệ thống.")
        if any(r.id == id_ or r.label == label for r in self._repo.list_entity_types()):
            raise InvalidError("Mã hoặc label đã được dùng bởi một loại thực thể khác.")
        row = self._repo.create_entity_type(id=id_, label=label, title=body.title.strip(), hint=body.hint.strip(),
                                            case_sensitive=body.case_sensitive)
        return _entity_def(row)

    def update_entity_type(self, id_: str, body: EntityTypeUpdate) -> GraphEntityTypeDefinition:
        self._require_custom_entity_type(id_)
        return _entity_def(self._repo.update_entity_type(id_, **body.model_dump(exclude_none=True)))

    def delete_entity_type(self, id_: str) -> None:
        self._require_custom_entity_type(id_)
        used = [r.relation_type for r in self._repo.list_relations() if r.object_type == id_]
        if used:
            raise ConflictError(f"Loại thực thể đang được quan hệ {', '.join(used)} dùng — hãy xoá các quan hệ đó trước.")
        self._repo.delete_entity_type(id_)

    def _require_custom_entity_type(self, id_: str) -> None:
        if id_ in ENTITY_TYPES:
            raise InvalidError("Loại thực thể có sẵn của hệ thống không sửa hoặc xoá được.")
        self._repo.get_entity_type(id_)

    # ---- quan hệ ----
    def create_relation(self, body: RelationCreate) -> GraphRelationDefinition:
        type_ = body.relation_type.strip().upper()
        if not _REL_TYPE.match(type_):
            raise InvalidError("Loại quan hệ viết HOA, số, gạch dưới; bắt đầu bằng chữ, dài 3–50 ký tự (vd DISEASE_AFFECTS_SITE).")
        existing = self._repo.list_relations()
        if type_ in {r.type for s in SLOTS for r in s.relations} or any(r.relation_type == type_ for r in existing):
            raise InvalidError(f"Loại quan hệ {type_} đã tồn tại.")
        slot_id = type_.lower()
        if any(s.id == slot_id for s in SLOTS):
            raise InvalidError(f"Mã ô {slot_id} trùng quan hệ có sẵn của hệ thống.")
        if body.topic not in TOPIC_TYPES:
            raise InvalidError("Chủ đề chỉ là bệnh hoặc thuốc.")
        custom = {r.id: r for r in self._repo.list_entity_types()}
        if body.object_type not in ENTITY_TYPES and body.object_type not in custom:
            raise InvalidError(f"Loại thực thể không hợp lệ: {body.object_type}")
        if body.topic == "drug" and body.object_type == "dermo":
            raise InvalidError("Chủ đề thuốc không có nút DermO để nối.")
        row = self._repo.create_relation(
            slot_id=slot_id, relation_type=type_, topic=body.topic, object_type=body.object_type, topic_is_head=body.topic_is_head,
            title=body.title.strip(), display=(body.display.strip() or body.title.strip()), hint=body.hint.strip(),
            entity_hint=body.entity_hint.strip(), enabled=body.enabled)
        return _relation_def(row)

    def update_relation(self, id_: str, body: RelationUpdate) -> GraphRelationDefinition:
        self._repo.get_relation(id_)
        return _relation_def(self._repo.update_relation(id_, **body.model_dump(exclude_none=True)))

    def delete_relation(self, id_: str, purge_edges: Callable[[str], None]) -> None:
        row = self._repo.get_relation(id_)
        purge_edges(row.relation_type)  # xoá cạnh trước: lỗi Neo4j thì định nghĩa còn nguyên để thử lại
        self._repo.delete_relation(id_)
