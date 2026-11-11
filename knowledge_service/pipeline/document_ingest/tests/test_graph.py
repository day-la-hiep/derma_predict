"""Test bước Trích quan hệ (graph) và Lưu vào đồ thị (graph_index): LLM giả, từ điển nhỏ, Neo4j giả trong bộ nhớ.

python -m unittest pipeline.document_ingest.tests.test_graph -v"""

from pipeline.document_ingest.tests.memory_infra import MemoryBlobCache
import json
import unittest
from pathlib import Path
from typing import Any

from app.dto.api import TripleUpdate
from app.infra.llm_client import LLMClient
from app.services.document_graph_service import DocumentGraphService
from app.services.document_ingest_pipeline_service import DocumentIngestPipelineService
from app.services.document_service import read_profile

from pipeline.document_ingest.graph_link import EntityLexicon, LexEntry
from app.dto.base.document import DocumentChunk
from pipeline.document_ingest.stages import StageError
from pipeline.document_ingest.stages.step5_graph import EXTRACT_PROMPT, PICK_PROMPT, pick_units, split_units
from pipeline.document_ingest.tests.test_document_pipeline import Base, FakeEmbedding

IMPETIGO = ("Chốc là bệnh nhiễm khuẩn nông của da. Tổn thương ban đầu là bọng nước nông, dễ vỡ, để lại vảy tiết màu vàng mật ong. "
            "Điều trị bằng mupirocin bôi tại chỗ. Bệnh có thể gây viêm cầu thận cấp. Hay gặp ở trẻ nhỏ.")
MUPIROCIN = "Mupirocin là kháng sinh bôi. Tác dụng không mong muốn: ngứa, cảm giác bỏng rát tại chỗ."


def _chunk(cid: str, path: list[str], text: str, page: int) -> dict[str, Any]:
    return {"chunk_id": cid, "seq": int(cid[-1]), "document_id": "tbook", "text": text, "context_text": text,
            "toc_path": path, "toc_node_ids": [], "figure_ids": [], "level": 2, "pages_hint": [page],
            "boundary": False, "suspect": False, "page_start": page, "page_end": page, "page_printed_start": page - 3,
            "page_printed_end": page - 3, "tokens": 50, "chars": len(text)}


CHUNKS = [
    _chunk("tbook:c00001", ["Nhiễm khuẩn da", "Chốc"], IMPETIGO, 10),
    _chunk("tbook:c00002", ["Thuốc bôi", "Mupirocin"], MUPIROCIN, 40),
    _chunk("tbook:c00003", ["Giải phẫu da"], "Da gồm ba lớp: thượng bì, trung bì, hạ bì.", 2),
]


def lexicon() -> EntityLexicon:
    return EntityLexicon([
        LexEntry("5984", "impetigo", "disease", "MONDO", "primekg"),
        LexEntry("9000", "glomerulonephritis", "disease", "MONDO", "primekg"),
        LexEntry("100", "Bulla", "effect/phenotype", "HPO", "primekg"),
        LexEntry("101", "Pruritus", "effect/phenotype", "HPO", "primekg"),
        LexEntry("102", "Burning sensation of the skin", "effect/phenotype", "HPO", "primekg"),
        LexEntry("DB00410", "Mupirocin", "drug", "DrugBank", "primekg"),
        LexEntry("DERMO:0000001", "impetigo", "dermo", "DermO", "dermo", aliases=["impetigo contagiosa"]),
    ])


def graph_llm(system: str, user: str) -> str:
    data = json.loads(user.split("(JSON):\n", 1)[1])
    if system == EXTRACT_PROMPT:
        cid = data["chunks"][0]["chunk_id"]
        impetigo = {"text": "Chốc", "en": "impetigo"}
        if data["context"].endswith("Chốc"):
            return json.dumps({"slots": {
                "phenotypes_present": [{"subject": impetigo, "text": "bọng nước nông", "en": "bulla", "evidence": "bọng nước nông, dễ vỡ", "chunk_id": cid},
                                       {"subject": impetigo, "text": "sốt cao", "en": "high fever", "evidence": "sốt cao liên tục", "chunk_id": cid}],
                "drugs_indicated": [{"subject": impetigo, "text": "mupirocin bôi", "en": "mupirocin", "evidence": "Điều trị bằng mupirocin bôi", "chunk_id": cid}],
                "complications": [{"subject": impetigo, "text": "viêm cầu thận cấp", "en": "acute glomerulonephritis", "evidence": "gây viêm cầu thận cấp", "chunk_id": cid}],
                "genes": [{"text": "FLG", "en": "FLG", "evidence": "Chốc", "chunk_id": cid}],  # thiếu chủ thể -> bị bỏ
                "not_a_slot": [{"subject": impetigo, "text": "x", "en": "x", "evidence": "Chốc", "chunk_id": cid}],
            }, "unmapped": [{"kind": "risk_factor", "text": "trẻ nhỏ"}]})
        if data["context"].endswith("Mupirocin"):
            mupirocin = {"text": "Mupirocin", "en": "mupirocin"}
            return json.dumps({"slots": {
                "side_effects": [{"subject": mupirocin, "text": "ngứa", "en": "pruritus", "evidence": "ngứa", "chunk_id": cid},
                                 {"subject": mupirocin, "text": "bỏng rát", "en": "burning skin", "evidence": "cảm giác bỏng rát tại chỗ", "chunk_id": cid}],
            }})
        return json.dumps({"slots": {}})
    if system == PICK_PROMPT:
        choices = []
        for it in data:
            ids = [c["id"] for c in it["candidates"]]
            choices.append({"key": it["key"], "id": "102" if "102" in ids and it["en"] == "burning skin" else None})
        return json.dumps({"choices": choices})
    raise AssertionError("prompt lạ: " + system[:60])


class FakeGraph(DocumentGraphService):
    """Neo4j giả: giữ nút/cạnh trong bộ nhớ, cùng các method `DocumentGraphService` mà bước graph dùng."""

    def __init__(self, repo: Any) -> None:
        super().__init__(repo, None, Path("/nonexistent"))
        self.existing: set[tuple[str, str]] = {("disease", "5984"), ("effect/phenotype", "100"), ("drug", "DB00410"), ("gene/protein", "9000")}
        self.nodes: dict[str, list[dict[str, Any]]] = {}
        self.edges: dict[str, list[dict[str, Any]]] = {}

    @property
    def configured(self) -> bool:
        return True

    def doc_entities(self) -> list[dict[str, Any]]:
        return [n for rows in self.nodes.values() for n in rows if n["source"] == "DOC"]

    def existing_nodes(self, pairs: list[tuple[str, str]]) -> set[tuple[str, str]]:
        return {p for p in pairs if p in self.existing}

    def replace_document(self, document_id: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        self.nodes[document_id], self.edges[document_id] = nodes, edges

    def count_edges(self, document_id: str) -> int:
        return len(self.edges.get(document_id, []))

    def delete_document(self, document_id: str) -> None:
        self.nodes.pop(document_id, None)
        self.edges.pop(document_id, None)


class GraphBase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.graph = FakeGraph(self.repo)
        self.graph.set_lexicon(lexicon())
        self.vectors.graph = self.graph
        self.runner = DocumentIngestPipelineService(self.vectors, embedding=FakeEmbedding(), graph=self.graph)  # type: ignore[arg-type]
        self.files.write_jsonl("chunks.jsonl", CHUNKS)
        self.gllm = LLMClient("fake", cache=MemoryBlobCache(), fn=graph_llm)

    def run_graph(self) -> dict:
        return self.runner.run_stage("tbook", "graph", {}, force=True, llm=self.gllm)

    def triples(self) -> dict[tuple[str, str], dict[str, Any]]:
        return {(t["relation"], t["object"]["text"] if t["slot"] != "drugs_indicated" else t["subject"]["text"]): t
                for t in self.files.read_jsonl("triples.jsonl")}


class GraphStageTest(GraphBase):
    def test_subjects_come_from_the_text_not_from_toc_classification(self) -> None:
        out = self.run_graph()
        self.assertEqual((out["units"], out["units_total"]), (3, 3))
        self.assertEqual(out["subjects"], {"disease": 1, "drug": 1})
        self.assertEqual(out["warnings"], ["1 quan hệ bị bỏ vì AI không nêu chủ thể (xem nhật ký)."])
        self.assertEqual(len(self.files.read_json("graph/units.json")), 3)

    def test_trial_run_reads_only_the_requested_number_of_units(self) -> None:
        out = self.runner.run_stage("tbook", "graph", {"limit_calls": "1"}, force=True, llm=self.gllm)
        self.assertEqual((out["units"], out["units_total"]), (1, 3))
        self.assertEqual(out["subjects"], {"disease": 1})  # lô đầu sách

    def test_call_limit_must_be_an_integer(self) -> None:
        with self.assertRaises(StageError):
            self.runner.run_stage("tbook", "graph", {"limit_calls": "100-120"}, force=True, llm=self.gllm)

    def test_triples_follow_edge_direction_and_link_exactly(self) -> None:
        self.run_graph()
        t = self.triples()
        pos = t[("DISEASE_PHENOTYPE_POSITIVE", "bọng nước nông")]
        self.assertEqual((pos["subject"]["node_id"], pos["object"]["node_id"], pos["status"]), ("5984", "100", "ok"))
        ind = t[("INDICATION", "mupirocin bôi")]  # thuốc -> bệnh, dù chủ đề của mục là bệnh
        self.assertEqual((ind["subject"]["node_id"], ind["object"]["node_id"]), ("DB00410", "5984"))
        self.assertEqual(ind["pages"], [10])

    def test_fabricated_evidence_and_unknown_slots_are_dropped(self) -> None:
        out = self.run_graph()
        self.assertNotIn(("DISEASE_PHENOTYPE_POSITIVE", "sốt cao"), self.triples())
        self.assertEqual(out["evidence_dropped"], 1)
        self.assertEqual(out["unmapped"], {"risk_factor": 1})

    def test_llm_picks_among_candidates_or_leaves_unlinked(self) -> None:
        self.run_graph()
        t = self.triples()
        burn = t[("DRUG_EFFECT", "bỏng rát")]
        self.assertEqual((burn["object"]["node_id"], burn["object"]["link_method"], burn["status"]), ("102", "llm", "ok"))
        comp = t[("RESULTS_IN", "viêm cầu thận cấp")]  # DermO không có thuật ngữ này
        self.assertEqual((comp["object"]["node_id"], comp["status"]), (None, "unlinked"))
        self.assertEqual(comp["subject"]["node_id"], "DERMO:0000001")

    def test_new_entity_is_proposed_but_stays_unlinked(self) -> None:
        p = read_profile(self.repo, "tbook")
        p.graph.allow_new_entities = True
        self.repo.update_meta("tbook", profile=p.model_dump(mode="json"))
        self.run_graph()
        comp = self.triples()[("RESULTS_IN", "viêm cầu thận cấp")]
        self.assertEqual((comp["object"]["kg"], comp["object"]["link_method"], comp["status"]), ("doc", "new", "unlinked"))

    def test_rejected_triples_survive_a_rerun(self) -> None:
        self.run_graph()
        pos = self.triples()[("DISEASE_PHENOTYPE_POSITIVE", "bọng nước nông")]
        self.runner.update_triples("tbook", TripleUpdate(rejected=[pos["triple_id"]]))
        self.run_graph()
        self.assertEqual(self.triples()[("DISEASE_PHENOTYPE_POSITIVE", "bọng nước nông")]["status"], "rejected")
        self.runner.update_triples("tbook", TripleUpdate(restored=[pos["triple_id"]]))
        self.assertEqual(self.triples()[("DISEASE_PHENOTYPE_POSITIVE", "bọng nước nông")]["status"], "ok")

    def test_missing_lexicon_is_a_reviewer_facing_error(self) -> None:
        self.graph.set_lexicon(EntityLexicon())
        with self.assertRaises(StageError):
            self.run_graph()


class SplitUnitsTest(unittest.TestCase):
    @staticmethod
    def _chunks(paths: list[list[str]]) -> list[DocumentChunk]:
        return [DocumentChunk.model_validate(_chunk(f"tbook:c{i + 1:05d}", p, "x", i + 1)) for i, p in enumerate(paths)]

    def test_units_never_cross_the_smallest_toc_node_and_respect_size(self) -> None:
        chunks = self._chunks([["A", "a1"]] * 5 + [["A", "a2"]] * 2 + [["B"]])
        units = split_units(chunks, 3)
        self.assertEqual([(u["path"], len(u["chunk_ids"])) for u in units],
                         [(["A", "a1"], 3), (["A", "a1"], 2), (["A", "a2"], 2), (["B"], 1)])

    def test_trial_units_are_spread_evenly(self) -> None:
        units = [{"id": f"u{i}"} for i in range(10)]
        self.assertEqual([u["id"] for u in pick_units(units, 4)], ["u0", "u2", "u5", "u7"])  # type: ignore[arg-type]
        self.assertEqual(len(pick_units(units, 0)), 10)  # type: ignore[arg-type]
        self.assertEqual(len(pick_units(units, 99)), 10)  # type: ignore[arg-type]


class GraphIndexTest(GraphBase):
    def test_only_ok_triples_are_loaded_with_provenance(self) -> None:
        self.run_graph()
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        edges = self.graph.edges["tbook"]
        ok = [t for t in self.files.read_jsonl("triples.jsonl") if t["status"] == "ok"]
        self.assertEqual(out["edges"], len(ok))
        ind = next(e for e in edges if e["relation"] == "INDICATION")
        self.assertEqual((ind["x"], ind["y"], ind["display"]), ("DB00410", "5984", "indication"))
        self.assertEqual(ind["source_ref"], "Test, tr. 7")

    def test_primekg_node_missing_from_graph_is_added_and_same_id_of_other_type_does_not_block_it(self) -> None:
        self.run_graph()
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        added = {n["id"] for n in self.graph.nodes["tbook"]}
        self.assertIn("102", added)  # HPO chưa có trong đồ thị -> nạp thêm từ từ điển
        self.assertNotIn("9000", added)
        self.assertNotIn("skipped", out)

        self.graph.existing.add(("disease", "102"))  # id trùng nhưng khác loại: hai nút cùng tồn tại, không chặn nhau
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        self.assertNotIn("skipped", out)
        self.assertIn(("effect/phenotype", "102"), {(n["type"], n["id"]) for n in self.graph.nodes["tbook"]})

    def test_duplicate_pair_is_merged_keeping_provenance_and_self_loop_is_skipped(self) -> None:
        self.run_graph()
        rows = self.files.read_jsonl("triples.jsonl")
        base = next(t for t in rows if t["status"] == "ok" and t["relation"] == "INDICATION")
        dup = {**base, "triple_id": "dup", "evidence": "mupirocin bôi tại chỗ", "chunk_ids": ["tbook:c00002"], "pages": [9]}
        loop = {**base, "triple_id": "loop", "object": base["subject"]}
        self.files.write_jsonl("triples.jsonl", [*rows, dup, loop])
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        ind = [e for e in self.graph.edges["tbook"] if e["relation"] == "INDICATION"]
        self.assertEqual(len(ind), 1)
        self.assertIn(base["evidence"], ind[0]["evidence"])
        self.assertIn("mupirocin bôi tại chỗ", ind[0]["evidence"])
        self.assertIn(9, ind[0]["pages"])
        self.assertEqual(out["merged"], 1)
        self.assertEqual(out["skipped"], {"hai đầu trùng nút (tự trỏ về chính nó)": 1})
        self.assertEqual(out["edges"], len(self.graph.edges["tbook"]))

    def test_rerun_replaces_and_delete_document_cleans_graph(self) -> None:
        self.run_graph()
        self.runner.run_stage("tbook", "graph_index", {}, force=True)
        n = self.graph.count_edges("tbook")
        self.runner.run_stage("tbook", "graph_index", {}, force=True)
        self.assertEqual(self.graph.count_edges("tbook"), n)
        self.runner.documentService.delete_document("tbook")
        self.assertEqual(self.graph.count_edges("tbook"), 0)

    def test_regraph_marks_graph_index_stale(self) -> None:
        self.run_graph()
        self.runner.run_stage("tbook", "graph_index", {}, force=True)
        self.run_graph()
        self.assertEqual(self.repo.status("tbook")["stages"]["graph_index"]["state"], "stale")


if __name__ == "__main__":
    unittest.main()
