"""Test bước Trích quan hệ (graph) và Lưu vào đồ thị (graph_index): LLM giả, từ điển nhỏ, Neo4j giả trong bộ nhớ.

python -m unittest pipeline.document_ingest.tests.test_graph -v"""

import json
import unittest
from pathlib import Path
from typing import Any

from app.dto.request.document import TripleRelink, TripleUpdate
from app.infra.llm_client import LLMClient
from app.services.document_graph_service import DocumentGraphService
from app.services.document_ingest_pipeline_service import DocumentIngestPipelineService

from pipeline.document_ingest.graph_link import EntityLexicon, LexEntry
from pipeline.document_ingest.stages import StageError
from pipeline.document_ingest.stages.graph import EXTRACT_PROMPT, PICK_PROMPT, TOPIC_PROMPT
from pipeline.document_ingest.tests.test_document_pipeline import Base, FakeEmbedding

IMPETIGO = ("Chốc là bệnh nhiễm khuẩn nông của da. Tổn thương ban đầu là bọng nước nông, dễ vỡ, để lại vảy tiết màu vàng mật ong. "
            "Điều trị bằng mupirocin bôi tại chỗ. Bệnh có thể gây viêm cầu thận cấp. Hay gặp ở trẻ nhỏ.")
MUPIROCIN = "Mupirocin là kháng sinh bôi. Tác dụng không mong muốn: ngứa, cảm giác bỏng rát tại chỗ."


def _chunk(cid: str, path: list[str], topic: str, text: str, page: int) -> dict[str, Any]:
    return {"chunk_id": cid, "seq": int(cid[-1]), "document_id": "tbook", "text": text, "context_text": text, "part": "", "section": path[0],
            "topic": topic, "subtopic": "", "toc_path": path, "toc_node_ids": [], "figure_ids": [], "level": 2, "pages_hint": [page],
            "boundary": False, "suspect": False, "page_start": page, "page_end": page, "page_printed_start": page - 3,
            "page_printed_end": page - 3, "tokens": 50, "chars": len(text)}


CHUNKS = [
    _chunk("tbook:c00001", ["Nhiễm khuẩn da", "Chốc"], "Chốc", IMPETIGO, 10),
    _chunk("tbook:c00002", ["Thuốc bôi", "Mupirocin"], "Mupirocin", MUPIROCIN, 40),
    _chunk("tbook:c00003", ["Giải phẫu da"], "", "Da gồm ba lớp: thượng bì, trung bì, hạ bì.", 2),
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
    if system == TOPIC_PROMPT:
        kinds = {"Chốc": ("disease", "impetigo"), "Mupirocin": ("drug", "mupirocin")}
        return json.dumps({"topics": [{"id": t["id"], "kind": kinds.get(t["title"], ("other", ""))[0],
                                       "en": kinds.get(t["title"], ("", ""))[1]} for t in data]})
    if system == EXTRACT_PROMPT:
        cid = data["chunks"][0]["chunk_id"]
        if data["topic"]["kind"] == "disease":
            return json.dumps({"slots": {
                "phenotypes_present": [{"text": "bọng nước nông", "en": "bulla", "evidence": "bọng nước nông, dễ vỡ", "chunk_id": cid},
                                       {"text": "sốt cao", "en": "high fever", "evidence": "sốt cao liên tục", "chunk_id": cid}],
                "drugs_indicated": [{"text": "mupirocin bôi", "en": "mupirocin", "evidence": "Điều trị bằng mupirocin bôi", "chunk_id": cid}],
                "complications": [{"text": "viêm cầu thận cấp", "en": "acute glomerulonephritis", "evidence": "gây viêm cầu thận cấp", "chunk_id": cid}],
                "not_a_slot": [{"text": "x", "en": "x", "evidence": "Chốc", "chunk_id": cid}],
            }, "unmapped": [{"kind": "risk_factor", "text": "trẻ nhỏ"}]})
        return json.dumps({"slots": {
            "side_effects": [{"text": "ngứa", "en": "pruritus", "evidence": "ngứa", "chunk_id": cid},
                             {"text": "bỏng rát", "en": "burning skin", "evidence": "cảm giác bỏng rát tại chỗ", "chunk_id": cid}],
        }})
    if system == PICK_PROMPT:
        choices = []
        for it in data:
            ids = [c["id"] for c in it["candidates"]]
            choices.append({"key": it["key"], "id": "102" if "102" in ids and it["en"] == "burning skin" else None})
        return json.dumps({"choices": choices})
    raise AssertionError("prompt lạ: " + system[:60])


class FakeGraph(DocumentGraphService):
    """Neo4j giả: giữ nút/cạnh trong bộ nhớ, cùng hợp đồng `GraphStore`."""

    def __init__(self, repo: Any) -> None:
        super().__init__(repo, None, Path("/nonexistent"))
        self.existing: dict[str, str] = {"5984": "disease", "100": "effect/phenotype", "DB00410": "drug", "9000": "gene/protein"}
        self.nodes: dict[str, list[dict[str, Any]]] = {}
        self.edges: dict[str, list[dict[str, Any]]] = {}

    @property
    def configured(self) -> bool:
        return True

    def doc_entities(self) -> list[dict[str, Any]]:
        return [n for rows in self.nodes.values() for n in rows if n["source"] == "DOC"]

    def existing_types(self, ids: list[str]) -> dict[str, str]:
        return {i: self.existing[i] for i in ids if i in self.existing}

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
        self.runner = DocumentIngestPipelineService(self.vectors, self.repo, embedding=FakeEmbedding(), graph=self.graph)  # type: ignore[arg-type]
        self.files.write_jsonl("chunks.jsonl", CHUNKS)
        self.gllm = LLMClient("fake", cache_dir=Path(self.tmp.name) / "_gcache", fn=graph_llm)

    def run_graph(self) -> dict:
        return self.runner.run_stage("tbook", "graph", {}, force=True, llm=self.gllm)

    def triples(self) -> dict[tuple[str, str], dict[str, Any]]:
        return {(t["relation"], t["object"]["text"] if t["slot"] != "drugs_indicated" else t["subject"]["text"]): t
                for t in self.files.read_jsonl("triples.jsonl")}


class GraphStageTest(GraphBase):
    def test_topics_are_classified_and_only_disease_drug_sections_are_extracted(self) -> None:
        out = self.run_graph()
        kinds = {t["title"]: t["kind"] for t in self.files.read_json("graph/topics.json")}
        self.assertEqual(kinds, {"Chốc": "disease", "Mupirocin": "drug", "Giải phẫu da": "other"})
        self.assertEqual(out["topics_used"], {"disease": 1, "drug": 1, "other": 1})

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

    def test_new_entity_is_proposed_but_needs_acceptance(self) -> None:
        p = self.vectors.read_profile(self.repo, "tbook")
        p.graph.allow_new_entities = True
        self.repo.set_profile("tbook", p)
        self.run_graph()
        comp = self.triples()[("RESULTS_IN", "viêm cầu thận cấp")]
        self.assertEqual((comp["object"]["kg"], comp["object"]["link_method"], comp["status"]), ("doc", "new", "unlinked"))
        self.runner.update_triples("tbook", TripleUpdate(accept_nodes=[comp["object"]["node_id"]]))
        self.assertEqual(self.triples()[("RESULTS_IN", "viêm cầu thận cấp")]["status"], "ok")

    def test_review_overrides_survive_a_rerun(self) -> None:
        self.run_graph()
        t = self.triples()
        pos, comp = t[("DISEASE_PHENOTYPE_POSITIVE", "bọng nước nông")], t[("RESULTS_IN", "viêm cầu thận cấp")]
        self.runner.update_triples("tbook", TripleUpdate(
            rejected=[pos["triple_id"]],
            relink=[TripleRelink(triple_id=comp["triple_id"], side="object", node_id="DERMO:0000001")]))
        self.run_graph()
        t = self.triples()
        self.assertEqual(t[("DISEASE_PHENOTYPE_POSITIVE", "bọng nước nông")]["status"], "rejected")
        self.assertEqual(t[("RESULTS_IN", "viêm cầu thận cấp")]["object"]["link_method"], "manual")

    def test_relinking_a_topic_applies_to_every_triple_using_it(self) -> None:
        self.graph.lexicon().add(LexEntry("777", "contagious impetigo", "disease", "MONDO", "primekg"))
        self.run_graph()
        t = self.triples()
        ind = t[("INDICATION", "mupirocin bôi")]  # chủ đề "Chốc" là đuôi ở cạnh này, là đầu ở cạnh triệu chứng
        self.runner.update_triples("tbook", TripleUpdate(relink=[TripleRelink(triple_id=ind["triple_id"], side="object", node_id="777")]))
        t = self.triples()
        self.assertEqual(t[("DISEASE_PHENOTYPE_POSITIVE", "bọng nước nông")]["subject"]["node_id"], "777")
        self.runner.update_triples("tbook", TripleUpdate(
            relink=[TripleRelink(triple_id=ind["triple_id"], side="object", node_id=None, same_term=False)]))
        t = self.triples()
        self.assertEqual(t[("INDICATION", "mupirocin bôi")]["object"]["node_id"], "5984")
        self.assertEqual(t[("DISEASE_PHENOTYPE_POSITIVE", "bọng nước nông")]["subject"]["node_id"], "777")

    def test_relink_to_unknown_node_is_refused(self) -> None:
        self.run_graph()
        tid = next(iter(self.triples().values()))["triple_id"]
        with self.assertRaises(Exception):
            self.runner.update_triples("tbook", TripleUpdate(relink=[TripleRelink(triple_id=tid, side="object", node_id="nope")]))

    def test_missing_lexicon_is_a_reviewer_facing_error(self) -> None:
        self.graph.set_lexicon(EntityLexicon())
        with self.assertRaises(StageError):
            self.run_graph()


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

    def test_primekg_node_missing_from_subgraph_is_added_but_type_collision_is_skipped(self) -> None:
        self.run_graph()
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        added = {n["id"] for n in self.graph.nodes["tbook"]}
        self.assertIn("102", added)  # HPO chưa có trong subgraph -> nạp thêm từ PrimeKG đầy đủ
        self.assertNotIn("9000", added)
        self.assertNotIn("skipped", out)

        self.graph.existing["102"] = "disease"  # id trùng với nút khác loại đã có
        out = self.runner.run_stage("tbook", "graph_index", {}, force=True)
        self.assertEqual(out["skipped"], {"trùng id khác loại trong Neo4j": 1})

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
