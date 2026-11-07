"""Hàm biến đổi của pipeline gọi trực tiếp: không cần MinIO, SQLite hay Qdrant."""
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

from app.infra.llm_client import LLMClient
from app.models.document_profile import ChunkingConfig, ExtractionConfig
from pipeline.document_ingest import mapping
from pipeline.document_ingest.stages import StageCancelled, StageError
from pipeline.document_ingest.stages.step1_ingest import extract_pages
from pipeline.document_ingest.stages.step2_toc import count_pages, read_toc, summarize_toc
from pipeline.document_ingest.stages.step3_chunks import cut_chunks
from pipeline.document_ingest.stages.step4_index import BATCH, embed_chunks
from pipeline.document_ingest.tests.test_document_pipeline import DIM, FakeEmbedding, _pages, toc_llm
from pipeline.document_ingest.types import DoclingBlock, PageRow


def _page_rows() -> list[PageRow]:
    return [PageRow.model_validate(r) for r in _pages()]


def _blank_pdf(root: Path, pages: int) -> Path:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(100, 100)
    path = root / "book.pdf"
    w.write(path)
    return path


class PureStagesTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_extract_pages_docling_reads_span_by_span_and_collects_figures(self) -> None:
        pdf = _blank_pdf(self.root, 5)
        calls: list[tuple[int, int]] = []

        def convert(first: int, last: int) -> list[DoclingBlock]:
            calls.append((first, last))
            blocks = [DoclingBlock(page=n, label="text", text=f"hello {n}") for n in range(first, last + 1)]
            blocks.append(DoclingBlock(page=first, label="page_footer", text=str(first + 10)))
            blocks.append(DoclingBlock(page=first, label="figure", text="cap", image_key=f"figures/p{first}.png"))
            return blocks

        rows, figures, summary = extract_pages(pdf, ExtractionConfig(engine="docling", docling_chunk_pages=2), document_id="d", convert=convert)
        self.assertEqual(calls, [(1, 2), (3, 4), (5, 5)])
        self.assertEqual([r.text for r in rows], [f"hello {n}" for n in range(1, 6)])
        self.assertEqual(rows[0].page_printed, 11)  # số trang in lấy từ page_footer
        self.assertEqual([f.figure_id for f in figures], ["d:f00001", "d:f00002", "d:f00003"])
        self.assertEqual((summary["pages"], summary["figures"]), (5, 3))

    def test_extract_pages_honors_page_option_and_requires_convert(self) -> None:
        pdf = _blank_pdf(self.root, 5)
        rows, _, summary = extract_pages(pdf, ExtractionConfig(engine="docling"), pages_opt="2-3",
                                         convert=lambda a, b: [DoclingBlock(page=n, label="text", text="x") for n in range(a, b + 1)])
        self.assertEqual(([r.page for r in rows], summary["page_range"]), ([2, 3], [2, 3]))
        with self.assertRaises(StageError):
            extract_pages(pdf, ExtractionConfig(engine="docling"))

    def test_extract_pages_progress_callback_can_cancel(self) -> None:
        def cancel(done: int, total: int, message: str) -> None:
            raise StageCancelled()

        with self.assertRaises(StageCancelled):
            extract_pages(_blank_pdf(self.root, 3), ExtractionConfig(engine="docling"), on_progress=cancel, convert=lambda a, b: [])

    def test_read_toc_then_build_toc_gives_offset_and_anchors(self) -> None:
        rows = _page_rows()
        llm = LLMClient("fake", cache_dir=self.root / "_cache", fn=toc_llm)
        auto = read_toc(lambda: _blank_pdf(self.root, 11), rows, ExtractionConfig(), llm, None, pages_opt="2-3")
        self.assertEqual((auto.toc_pages, auto.pages_source, len(auto.entries)), ([2, 3], "user", 7))
        doc = mapping.build_toc(auto, {}, rows, count_pages(rows, lambda: _blank_pdf(self.root, 11)))
        self.assertEqual(doc.offset, 3)
        self.assertEqual(summarize_toc(doc)["entries"], 7)

    def test_cut_chunks_needs_offset_and_returns_review(self) -> None:
        rows = _page_rows()
        llm = LLMClient("fake", cache_dir=self.root / "_cache", fn=toc_llm)
        auto = read_toc(lambda: _blank_pdf(self.root, 11), rows, ExtractionConfig(), llm, None, pages_opt="2-3")
        doc = mapping.build_toc(auto, {}, rows, 11)
        args = dict(document_id="d", document_title="Book", figure_pages=[], on_progress=lambda *_: None)
        chunks, review, summary = cut_chunks(doc, rows, ChunkingConfig(), **args)  # type: ignore[arg-type]
        self.assertTrue(chunks)
        self.assertEqual(summary["chunks"], len(chunks))
        self.assertTrue(all(r["id"].startswith("d:c") for r in review))
        with self.assertRaises(StageError):
            cut_chunks(doc.model_copy(update={"offset": None}), rows, ChunkingConfig(), **args)  # type: ignore[arg-type]

    def test_embed_chunks_batches_and_reports_progress(self) -> None:
        chunks = [{"context_text": f"c{i}"} for i in range(BATCH + 3)]
        seen: list[tuple[int, int]] = []
        vectors, dim, model = embed_chunks(chunks, FakeEmbedding(), lambda d, t, m: seen.append((d, t)))  # type: ignore[arg-type]
        self.assertEqual((len(vectors), dim, model), (len(chunks), DIM, "fake-embed"))
        self.assertEqual(seen[-1], (len(chunks), len(chunks)))


if __name__ == "__main__":
    unittest.main()
