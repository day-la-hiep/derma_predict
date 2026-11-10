# pyright: reportMissingImports=false
# (ragas chỉ cài trong core/benchmark/data/venv-ragas, không có trong .venv của core)
import argparse
import asyncio
import json
import os
import random
import re
from collections import defaultdict
from typing import Any

import numpy as np
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, SecretStr
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.run_config import RunConfig
from ragas.testset import TestsetGenerator
from ragas.testset.persona import Persona
from ragas.testset.synthesizers import default_query_distribution

from benchmark.common.jsonl import write_jsonl
from benchmark.retrieval import snapshot_store
from benchmark.retrieval.paths import DATA, SETS
from benchmark.retrieval.schema import ChunkRecord, Qrel, Query

# Chạy bằng môi trường riêng (core/benchmark/data/venv-ragas): cài ragas vào .venv của core sẽ hạ cấp openai/jiter/rich.
# Khoá API lấy từ biến môi trường OPENROUTER_API_KEY / DEEPSEEK_API_KEY, script không import app.*.
MIN_CHARS = 300
MAX_COPY_WORDS = 7  # tiếng Việt tách theo âm tiết: 5 âm tiết chỉ là tên bệnh ("nấm bàn chân mạn tính"), nên mới coi là chép từ 8 âm tiết liên tiếp
DEDUP_COSINE = 0.9
EMBED_MODEL = "qwen/qwen3-embedding-8b"
_SKIP_SECTION = re.compile(r"mục lục|tài liệu tham khảo|danh mục|phụ lục|references|bibliography|table of contents", re.I)

_CONTEXT = (
    "Mọi câu hỏi và câu trả lời viết bằng TIẾNG VIỆT. Câu hỏi do một bệnh nhân không có chuyên môn y khoa hỏi bác sĩ da liễu: "
    "kể triệu chứng hoặc tình huống bằng lời đời thường, không dùng thuật ngữ chuyên ngành, không nhắc tên sách hay 'đoạn văn'."
)
_PERSONAS = [
    Persona(name="Người lớn tự theo dõi", role_description="Người trưởng thành không có chuyên môn y khoa, lo lắng về một vấn đề trên da của mình và kể triệu chứng bằng lời đời thường."),
    Persona(name="Phụ huynh", role_description="Cha mẹ hỏi về tình trạng da của con nhỏ, quan tâm có lây không, có nguy hiểm không và cần làm gì."),
    Persona(name="Người cao tuổi", role_description="Người lớn tuổi có bệnh nền, hỏi về vấn đề da kèm thuốc đang dùng, diễn đạt giản dị."),
]
_ANSWER_SYSTEM = (
    "Chỉ dựa vào CÁC ĐOẠN SÁCH được đưa, trả lời câu hỏi của bệnh nhân. Không dùng kiến thức bên ngoài. Chỉ trả về JSON "
    '{"answerable": true|false}: true nếu các đoạn sách đủ thông tin để trả lời trực tiếp câu hỏi.'
)


class LogRow(BaseModel):
    qid: str = ""
    synthesizer: str = ""
    question: str = ""
    contexts: int = 0
    matched: int = 0
    # kept | no_match | copy | unanswerable | duplicate | surplus | error
    status: str
    detail: str = ""


def _llm(spec: str) -> ChatOpenAI:
    provider, _, name = spec.partition(":")
    if provider == "deepseek":
        return ChatOpenAI(model=name, base_url="https://api.deepseek.com", api_key=SecretStr(os.environ["DEEPSEEK_API_KEY"]), temperature=0)
    return ChatOpenAI(model=name or provider, base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"), api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]), temperature=0.3)


def _sample(chunks: list[ChunkRecord], k: int, seed: int) -> list[ChunkRecord]:
    # luân phiên theo sách, trong sách luân phiên theo mục (2 cấp đầu toc_path)
    eligible = [c for c in chunks if len(c.text) >= MIN_CHARS and not _SKIP_SECTION.search(" ".join(c.toc_path))]
    rng = random.Random(seed)
    books: dict[str, dict[tuple[str, ...], list[ChunkRecord]]] = defaultdict(lambda: defaultdict(list))
    for c in sorted(eligible, key=lambda c: c.chunk_id):
        books[c.document_title][tuple(c.toc_path[:2])].append(c)
    per_book: list[list[ChunkRecord]] = []
    for _, strata in sorted(books.items()):
        queues = [rng.sample(v, len(v)) for _, v in sorted(strata.items())]
        rng.shuffle(queues)
        picked: list[ChunkRecord] = []
        while any(queues):
            for q in queues:
                if q:
                    picked.append(q.pop())
        per_book.append(picked)
    out: list[ChunkRecord] = []
    while len(out) < k and any(per_book):
        for picked in per_book:
            if picked and len(out) < k:
                out.append(picked.pop(0))
    return out


def _words(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


def _copies_phrase(question: str, contexts: list[str]) -> bool:
    n = MAX_COPY_WORDS + 1
    grams = {tuple(t[i : i + n]) for c in contexts for t in [_words(c)] for i in range(len(t) - n + 1)}
    q = _words(question)
    return any(tuple(q[i : i + n]) in grams for i in range(len(q) - n + 1))


async def _answerable(llm: ChatOpenAI, question: str, contexts: list[str]) -> bool:
    user = "CÁC ĐOẠN SÁCH:\n" + "\n---\n".join(c[:3000] for c in contexts) + f"\n\nCÂU HỎI: {question}"
    msg = await llm.ainvoke([("system", _ANSWER_SYSTEM), ("human", user)])
    m = re.search(r"\{.*?\}", str(msg.content), re.S)
    return bool(m and json.loads(m.group(0)).get("answerable") is True)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _ctx(c: Any) -> str:
    # câu đa bước: RAGAS thêm tiền tố "<1-hop>", "<2-hop>" vào đầu mỗi ngữ cảnh
    return re.sub(r"^<\d+-hop>\s*", "", str(c))


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=20, help="số câu hỏi RAGAS sinh ra (trước khi lọc)")
    p.add_argument("--chunks", type=int, default=100, help="số chunk dựng knowledge graph")
    p.add_argument("--gen-model", default="openai:google/gemma-4-26b-a4b-it")
    p.add_argument("--answer-model", required=True, help="model lọc khả năng trả lời, KHÁC --gen-model, vd deepseek:deepseek-flash")
    p.add_argument("--snapshot", default=None)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--review-n", type=int, default=25)
    p.add_argument("--reuse-raw", action="store_true", help="bỏ qua bước sinh, lọc lại từ data/retrieval/ragas_raw.jsonl")
    args = p.parse_args()
    if args.answer_model == args.gen_model:
        raise SystemExit("--answer-model phải khác --gen-model.")

    snap = args.snapshot or snapshot_store.latest()
    corpus = snapshot_store.load(snap)
    chosen = _sample(list(corpus.values()), args.chunks, args.seed)
    docs = [Document(page_content=c.text, metadata={"chunk_id": c.chunk_id, "document_title": c.document_title}) for c in chosen]
    by_text = {_norm(c.text): c for c in chosen}

    raw = DATA / "ragas_raw.jsonl"
    embeddings = OpenAIEmbeddings(
        model=EMBED_MODEL, base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"), api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]), check_embedding_ctx_length=False
    )
    if args.reuse_raw:
        samples: list[dict[str, Any]] = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        gen_llm = LangchainLLMWrapper(_llm(args.gen_model))
        generator = TestsetGenerator(llm=gen_llm, embedding_model=LangchainEmbeddingsWrapper(embeddings), persona_list=_PERSONAS, llm_context=_CONTEXT)
        testset = generator.generate_with_chunks(
            docs,
            testset_size=args.n,
            query_distribution=default_query_distribution(gen_llm, llm_context=_CONTEXT),
            run_config=RunConfig(max_workers=args.workers, timeout=240, max_retries=3),
            raise_exceptions=False,
        )
        raw.parent.mkdir(parents=True, exist_ok=True)
        testset.to_jsonl(str(raw))  # lưu ngay: lọc lỗi thì không phải sinh lại
        samples = testset.to_list()  # type: ignore[assignment]
    print(f"{len(samples)} mẫu RAGAS từ {len(docs)} chunk ({raw})")

    answer_llm = _llm(args.answer_model)
    sem = asyncio.Semaphore(args.workers)
    rows: list[LogRow] = []
    keep: list[tuple[dict[str, Any], list[ChunkRecord], LogRow]] = []

    async def judge(s: dict[str, Any]) -> tuple[dict[str, Any], list[ChunkRecord], LogRow]:
        q = str(s.get("user_input", "")).strip()
        ctxs = [_ctx(c) for c in s.get("reference_contexts") or []]
        matched = [by_text[_norm(c)] for c in ctxs if _norm(c) in by_text]
        row = LogRow(synthesizer=str(s.get("synthesizer_name", "")), question=q, contexts=len(ctxs), matched=len(matched), status="error")
        try:
            if not q or not matched:
                row.status = "no_match"
            elif _copies_phrase(q, ctxs):
                row.status = "copy"
            else:
                async with sem:
                    ok = await _answerable(answer_llm, q, ctxs)
                row.status = "kept" if ok else "unanswerable"
        except Exception as exc:  # noqa: BLE001  # một mẫu lỗi không làm hỏng cả lượt
            row.detail = f"{type(exc).__name__}: {exc}"[:200]
        return s, matched, row

    for s, matched, row in await asyncio.gather(*(judge(s) for s in samples)):
        rows.append(row)
        if row.status == "kept":
            keep.append((s, matched, row))

    if len(keep) > 1:  # bỏ câu hỏi quá gần nhau về nghĩa
        vecs = np.array(await embeddings.aembed_documents([r.question for _, _, r in keep]))
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        accepted: list[int] = []
        for i, (_, _, r) in enumerate(keep):
            if accepted and float((vecs[accepted] @ vecs[i]).max()) > DEDUP_COSINE:
                r.status = "duplicate"
            else:
                accepted.append(i)
        keep = [k for k in keep if k[2].status == "kept"]

    queries: list[Query] = []
    qrels: list[Qrel] = []
    counters = {"single": 0, "multi": 0}
    for s, matched, row in keep:
        multi = "multi" in row.synthesizer.lower()
        counters["multi" if multi else "single"] += 1
        qid = f"{'M' if multi else 'R'}-{counters['multi' if multi else 'single']:03d}"
        row.qid = qid
        queries.append(Query(qid=qid, set="ragas_multi_hop" if multi else "ragas_single_hop", text=row.question, type="lay", reference=s.get("reference")))
        for c in {c.chunk_id: c for c in matched}.values():
            qrels.append(Qrel(qid=qid, chunk_id=c.chunk_id, content_hash=c.content_hash, relevance=2, source="ragas", rationale="reference_contexts của RAGAS"))
    write_jsonl(SETS / "queries.jsonl", queries)
    write_jsonl(SETS / "qrels.jsonl", qrels)
    write_jsonl(DATA / "ragas_log.jsonl", rows)

    sample = random.Random(args.seed).sample(queries, min(args.review_n, len(queries)))
    review = ["# Duyệt tay câu hỏi RAGAS", "", "Đánh dấu mỗi câu: tốt / hỏng (không trả lời được từ ngữ cảnh, chép văn sách, hỏi chung chung, sai ngôn ngữ).", ""]
    for i, q in enumerate(sample, start=1):
        cids = [r.chunk_id for r in qrels if r.qid == q.qid]
        review += [f"## {i}. [{q.qid}] {q.text}", f"- Chunk đúng: {', '.join(f'`{c}`' for c in cids)}", f"- Mục: {' > '.join(corpus[cids[0]].toc_path)}",
                   f"> {corpus[cids[0]].text[:400].replace(chr(10), ' ')}", "", "Kết luận: [ ] tốt  [ ] hỏng  — ghi chú:", ""]
    (DATA / "ragas_review.md").write_text("\n".join(review), encoding="utf-8")

    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r.status] += 1
    print(f"giữ {len(queries)} câu ({counters['single']} đơn bước, {counters['multi']} đa bước, {len(qrels)} qrels); trạng thái: {dict(counts)}")
    print(f"-> {SETS}/queries.jsonl, qrels.jsonl; log + file duyệt tay trong {DATA}")


if __name__ == "__main__":
    asyncio.run(main())
