"""Test danh mục quan hệ / loại thực thể do bác sĩ định nghĩa: dùng trong bước graph, graph_index và validate khi tạo.

python -m unittest pipeline.document_ingest.tests.test_graph_schema -v"""

import json
import unittest

from app.dto.request.graph_schema import EntityTypeCreate, EntityTypeUpdate, RelationCreate, RelationUpdate
from app.exception.errors import ConflictError, InvalidError
from app.models.graph_schema import GraphEntityType, GraphRelation
from app.repositories.graph_schema_repository import GraphSchemaRepository
from app.services.document_ingest_pipeline_service import DocumentIngestPipelineService
from app.services.graph_schema_service import GraphSchemaService

from pipeline.document_ingest.stages.graph import EXTRACT_PROMPT
from pipeline.document_ingest.tests.test_document_pipeline import FakeEmbedding
from pipeline.document_ingest.tests.test_graph import CHUNKS, GraphBase, graph_llm

GROUP = EntityTypeCreate(id="patient_group", label="PatientGroup", title="Nhóm bệnh nhân", hint="nhóm bệnh nhân tiếng Anh, vd 'children'")
REL = RelationCreate(relation_type="DISEASE_AFFECTS_GROUP", topic="disease", object_type="patient_group", title="hay gặp ở",
                     hint="nhóm bệnh nhân hay mắc bệnh này", entity_hint="")


def llm_with_custom_slot(system: str, user: str) -> str:
    out = graph_llm(system, user)
    if system != EXTRACT_PROMPT:
        return out
    data = json.loads(user.split("(JSON):\n", 1)[1])
    if not any(s["id"] == "disease_affects_group" for s in data["slots"]):
        return out
    res = json.loads(out)
    res["slots"]["disease_affects_group"] = [{"text": "trẻ nhỏ", "en": "children", "evidence": "Hay gặp ở trẻ nhỏ", "chunk_id": data["chunks"][0]["chunk_id"]}]
    return json.dumps(res)


class SchemaBase(GraphBase):
    def setUp(self) -> None:
        super().setUp()
        sessions = self.repo._sessions
        bind = sessions.kw["bind"]
        for t in (GraphEntityType.__table__, GraphRelation.__table__):
            t.create(bind, checkfirst=True)  # type: ignore[attr-defined]
        self.schema = GraphSchemaService(GraphSchemaRepository(sessions))
        self.runner = DocumentIngestPipelineService(self.vectors, self.repo, embedding=FakeEmbedding(), graph=self.graph,  # type: ignore[arg-type]
                                                    graph_schema=self.schema)
        self.gllm._fn = llm_with_custom_slot


class CustomSchemaInPipelineTest(SchemaBase):
    def _add(self) -> str:
        self.schema.create_entity_type(GROUP)
        return self.schema.create_relation(REL).id or ""

    def test_custom_relation_and_entity_type_flow_through_graph_and_index(self) -> None:
        self._add()
        self.run_graph()
        t = next(x for x in self.files.read_jsonl("triples.jsonl") if x["relation"] == "DISEASE_AFFECTS_GROUP")
        self.assertEqual((t["subject"]["node_id"], t["object"]["kg"], t["object"]["link_method"], t["status"]),
                         ("5984", "doc", "new", "ok"))
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        edge = next(e for e in self.graph.edges["tbook"] if e["relation"] == "DISEASE_AFFECTS_GROUP")
        self.assertEqual((edge["display"], edge["x"], edge["y_type"]), ("hay gặp ở", "5984", "patient_group"))
        self.assertTrue(any(n["type"] == "patient_group" and n["source"] == "DOC" for n in self.graph.nodes["tbook"]))
        self.assertNotIn("skipped", out)

    def test_disabled_relation_is_not_extracted_but_reviewed_triples_still_load(self) -> None:
        rid = self._add()
        self.run_graph()
        self.schema.update_relation(rid, RelationUpdate(enabled=False))
        out = self.run_graph()
        self.assertNotIn("DISEASE_AFFECTS_GROUP", out["by_relation"])
        self.files.write_jsonl("triples.jsonl", [
            *self.files.read_jsonl("triples.jsonl"),
            {**next(x for x in self.files.read_jsonl("triples.jsonl") if x["relation"] == "DISEASE_PHENOTYPE_POSITIVE"),
             "triple_id": "keep", "relation": "DISEASE_AFFECTS_GROUP", "slot": "disease_affects_group"},
        ])
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        self.assertIn("DISEASE_AFFECTS_GROUP", out["by_relation"])

    def test_triples_of_a_deleted_relation_are_skipped_with_a_warning(self) -> None:
        rid = self._add()
        self.run_graph()
        purged: list[str] = []
        self.schema.delete_relation(rid, purged.append)
        self.assertEqual(purged, ["DISEASE_AFFECTS_GROUP"])
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        self.assertEqual(out["skipped"], {"quan hệ đã bị xoá khỏi danh mục": 1})


class SchemaServiceTest(SchemaBase):
    def test_lists_core_then_custom(self) -> None:
        self.schema.create_entity_type(GROUP)
        self.schema.create_relation(REL)
        types, rels = self.schema.list_entity_types(), self.schema.list_relations()
        self.assertEqual([t.id for t in types if not t.builtin], ["patient_group"])
        self.assertTrue(all(r.builtin for r in rels[:-1]) and not rels[-1].builtin)
        self.assertEqual(rels[-1].display, "hay gặp ở")  # display rỗng thì lấy theo title

    def test_relation_validation(self) -> None:
        self.schema.create_entity_type(GROUP)
        bad = [
            REL.model_copy(update={"relation_type": "bad type; DETACH DELETE"}),
            REL.model_copy(update={"relation_type": "INDICATION"}),  # trùng quan hệ core
            REL.model_copy(update={"object_type": "nope"}),
            REL.model_copy(update={"topic": "drug", "object_type": "dermo"}),
        ]
        for body in bad:
            with self.assertRaises(InvalidError, msg=body.relation_type):
                self.schema.create_relation(body)
        self.schema.create_relation(REL)
        with self.assertRaises(InvalidError):
            self.schema.create_relation(REL)

    def test_entity_type_validation_and_delete_guard(self) -> None:
        for body in (GROUP.model_copy(update={"id": "Bad Id"}), GROUP.model_copy(update={"label": "bad label"}),
                     GROUP.model_copy(update={"id": "drug"}), GROUP.model_copy(update={"label": "Disease"})):
            with self.assertRaises(InvalidError):
                self.schema.create_entity_type(body)
        self.schema.create_entity_type(GROUP)
        self.schema.create_relation(REL)
        with self.assertRaises(ConflictError):
            self.schema.delete_entity_type("patient_group")
        with self.assertRaises(InvalidError):
            self.schema.update_entity_type("disease", EntityTypeUpdate(title="x"))

    def test_custom_entity_type_is_case_sensitive_in_schema_only_when_asked(self) -> None:
        self.schema.create_entity_type(GROUP)
        self.assertFalse(self.schema.schema().entity_types["patient_group"].case_sensitive)


if __name__ == "__main__":
    unittest.main()
