"""Chunk theo khung mục lục"""
import re
from bisect import bisect_right
from collections.abc import Callable
from typing import Any

from .. import mapping
from app.dto.base.document import DocumentChunk
from app.models.document_profile import ChunkingConfig
from ..types import ChunkUnit, PageRow, TocDoc, TocNode
from . import StageError

OnProgress = Callable[[int, int, str], None]

_SENT = re.compile(r"(?<=[.!?])\s+")


def est_tokens(text: str) -> int:
    """Ước lượng token (không dùng tokenizer thật): lớn hơn của ~1.3 token/từ và ~1 token/4 ký tự."""
    return int(max(len(text.split()) * 1.3, len(text) / 4)) + 1


def split_unit(text: str, max_tokens: int) -> list[str]:
    """Một khối chữ dài quá mức: cắt theo câu, câu quá dài cắt theo từ."""
    out: list[str] = []
    cur = ""
    for sent in _SENT.split(text):
        words = sent.split()
        while est_tokens(" ".join(words)) > max_tokens:  # câu dài bất thường: cắt theo từ, theo đúng phép ước lượng token
            k = max(1, int(max_tokens / 1.3))
            while k > 1 and est_tokens(" ".join(words[:k])) > max_tokens:
                k -= 1
            piece, words = " ".join(words[:k]), words[k:]
            if cur:
                out.append(cur)
                cur = ""
            out.append(piece)
        sent = " ".join(words)
        if cur and est_tokens(cur + " " + sent) > max_tokens:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def build_toc_nodes(doc: TocDoc, max_page: int) -> list[TocNode]:
    """Cây mục lục -> các nút có điểm bắt đầu"""
    nodes: list[TocNode] = []
    prev = (0, -1)
    for e in doc.entries:
        pg = e.pdf_page
        if pg is None or e.out_of_range or not 1 <= pg <= max_page:
            continue
        line = e.anchor_line if e.anchored and e.anchor_line is not None else -1
        start = max((pg, line), prev)
        anchored = e.anchored and start == (pg, line)
        prev = start
        nodes.append(TocNode(id=e.id, title=e.title, level=e.level, kind=e.kind, page=start[0], line=start[1] if anchored else -1,
                             anchored=anchored, printed_page=e.printed_page, suspect=e.suspect))
    mapping.build_tree(nodes)  # cha/đường dẫn tính lại trên các mục còn lại
    for i, n in enumerate(nodes):  # khoảng trang theo mục lục: tới trang của mục kế cùng cấp trở lên
        nxt = next((m.page for m in nodes[i + 1:] if m.level <= n.level), max_page)
        n.page_hint = [n.page, max(n.page, nxt)]
    return nodes


def get_common_prefix(paths: list[list[str]]) -> list[str]:
    out: list[str] = []
    for col in zip(*paths):
        if len(set(col)) != 1:
            break
        out.append(col[0])
    return out


def split_into_regions(nodes: list[TocNode], units: list[tuple[int, int, str]], boundary_level: int) -> tuple[list[list[ChunkUnit]], int]:
    """Chia chữ cho mục chứa nó rồi gom thành các vùng"""
    by_id = {n.id: n for n in nodes}
    starts = [(n.page, n.line) for n in nodes]
    own = {(n.page, n.line) for n in nodes if n.anchored}  # dòng tiêu đề đã neo: chính tiêu đề, không phải thân

    def group(n: TocNode) -> str:
        while n.level > boundary_level and n.parent_id:
            n = by_id[n.parent_id]
        return n.id

    regions: list[list[ChunkUnit]] = []
    last_group, last_idx, outside = None, None, 0
    for page, line, text in units:
        if (page, line) in own or not text.strip():
            continue
        idx = bisect_right(starts, (page, line)) - 1
        if idx < 0:
            outside += 1
            continue
        node = nodes[idx]
        g = group(node)
        if g != last_group:
            regions.append([])
            last_group = g
        if idx != last_idx:  # vào một mục mới: tiêu đề của nó mở đầu phần chữ của mục
            regions[-1].append(ChunkUnit(node=node, page=page, text="#" * (node.level + 1) + " " + node.title, heading=True))
            last_idx = idx
        regions[-1].append(ChunkUnit(node=node, page=page, text=text, heading=False))
    return regions, outside


def pack_units(region: list[ChunkUnit], cfg: ChunkingConfig) -> list[list[ChunkUnit]]:
    """Cắt một vùng thành các nhóm item vừa `max_tokens` (item quá dài được cắt theo câu)."""
    flat: list[ChunkUnit] = []
    for it in region:
        if est_tokens(it.text) > cfg.max_tokens:
            flat += [it.model_copy(update={"text": s, "heading": False}) for s in split_unit(it.text, cfg.max_tokens)]
        else:
            flat.append(it)
    groups: list[list[ChunkUnit]] = []
    cur: list[ChunkUnit] = []
    for it in flat:
        if cur and est_tokens("\n".join(x.text for x in cur + [it])) > cfg.max_tokens:
            groups.append(cur)
            cur = []
        cur.append(it)
    if cur:
        groups.append(cur)
    # tiêu đề đứng một mình ở cuối nhóm thì chuyển xuống nhóm sau (tránh chunk chỉ có tiêu đề)
    for i in range(len(groups) - 1):
        while len(groups[i]) > 1 and groups[i][-1].heading:
            groups[i + 1].insert(0, groups[i].pop())
    return [g for g in groups if g]


def build_chunks(nodes: list[TocNode], units: list[tuple[int, int, str]], cfg: ChunkingConfig, *, document_id: str, document_title: str,
                 printed_offset: int, figure_pages: list[tuple[str, int]] | None = None) -> tuple[list[DocumentChunk], int]:
    """`figure_pages` = [(figure_id, trang)] của các hình trong sách."""
    by_id = {n.id: n for n in nodes}
    regions, outside = split_into_regions(nodes, units, cfg.boundary_level)
    chunks: list[DocumentChunk] = []
    for region in regions:
        for group in pack_units(region, cfg):
            members = list(dict.fromkeys(it.node.id for it in group))
            first = by_id[members[0]]
            paths = [by_id[m].path for m in members]
            path = get_common_prefix(paths) if len(paths) > 1 else paths[0]
            text = "\n".join(it.text for it in group)
            pages = [it.page for it in group]
            pa, pb = min(pages), max(pages)
            crumb = " > ".join([document_title, *path] if cfg.breadcrumb and document_title else path)
            seq = len(chunks) + 1
            chunks.append(DocumentChunk(
                chunk_id=f"{document_id}:c{seq:05d}", seq=seq, document_id=document_id, text=text,
                context_text=f"{crumb}\n{text}" if crumb else text,
                # ảnh theo khoảng trang: chunk trải nhiều trang thì nhận ảnh của mọi trang đó (có thể trùng giữa các chunk)
                figure_ids=[fid for fid, page in figure_pages or [] if pa <= page <= pb],
                toc_path=path, toc_node_ids=members, level=first.level,
                pages_hint=first.page_hint,
                # ranh giới chỉ chính xác tới trang khi mục chưa neo được dòng và chunk bắt đầu ở trang của mục đó
                boundary=not first.anchored and pa == first.page,
                suspect=any(by_id[m].suspect for m in members),
                page_start=pa, page_end=pb, page_printed_start=pa - printed_offset, page_printed_end=pb - printed_offset,
                tokens=est_tokens(text), chars=len(text),
            ))
    return chunks, outside


def build_review(chunks: list[DocumentChunk], cfg: ChunkingConfig) -> list[dict]:
    out = []
    for c in chunks:
        why = []
        if c.tokens > cfg.max_tokens * 1.1:
            why.append(f"quá dài (~{round(c.tokens / 1.3)} từ)")
        elif c.tokens < cfg.min_tokens:
            why.append(f"quá ngắn (~{round(c.tokens / 1.3)} từ)")
        if c.boundary:
            why.append("vị trí bắt đầu mục chỉ chính xác đến trang")
        if c.suspect:
            why.append("mục cần kiểm tra")
        if why:
            out.append({"id": c.chunk_id, "reason": "; ".join(why), "page": c.page_start})
    return out


def _summarize(chunks: list[DocumentChunk], nodes: list[TocNode], doc: TocDoc, outside: int, cfg: ChunkingConfig) -> dict[str, Any]:
    toks = sorted(c.tokens for c in chunks)
    summary: dict[str, Any] = {
        "chunks": len(chunks), "tokens": {"min": toks[0], "median": toks[len(toks) // 2], "max": toks[-1]},
        "toc_entries_used": len(nodes), "toc_entries_total": len(doc.entries), "offset": doc.offset,
        "boundary_chunks": sum(1 for c in chunks if c.boundary), "suspect_chunks": sum(1 for c in chunks if c.suspect),
        "too_short": sum(1 for c in chunks if c.tokens < cfg.min_tokens),
        "too_long": sum(1 for c in chunks if c.tokens > cfg.max_tokens * 1.1),
        "outside_toc_lines": outside,
    }
    warnings = []
    if len(nodes) < len(doc.entries):
        warnings.append(f"{len(doc.entries) - len(nodes)} mục của mục lục nằm ngoài các trang đã đọc nên chưa có đoạn nội dung.")
    if outside:
        warnings.append(f"{outside} dòng chữ nằm trước mục đầu tiên của mục lục (bìa, lời nói đầu…) nên không thuộc đoạn nào.")
    if warnings:
        summary["warnings"] = warnings
    return summary


def cut_chunks(doc: TocDoc, rows: list[PageRow], cfg: ChunkingConfig, *, document_id: str, document_title: str,
               figure_pages: list[tuple[str, int]], on_progress: OnProgress) -> tuple[list[DocumentChunk], list[dict], dict[str, Any]]:
    """`toc.json` + các trang (đã bỏ trang nhiễu) -> (chunks, danh sách chunk cần soát, summary)."""
    if doc.offset is None:
        raise StageError("Chưa xác định được độ chênh lệch số trang — hãy nhập tay ở bước Mục lục rồi làm lại.")
    # Bước 1: mục lục -> các nút có điểm bắt đầu; thân sách -> các dòng chữ (bỏ trang mục lục)
    nodes = build_toc_nodes(doc, max(r.page for r in rows))
    if not nodes:
        raise StageError("Không mục nào của mục lục nằm trong các trang đã đọc — hãy kiểm tra độ chênh lệch số trang.")
    skip = set(doc.toc_pages)
    units = [(r.page, i, ln) for r in rows if r.page not in skip for i, ln in enumerate(r.text.split("\n"))]
    # Bước 2: cắt chunk theo khung mục lục
    on_progress(1, 2, "cắt chunk")
    chunks, outside = build_chunks(nodes, units, cfg, document_id=document_id, document_title=document_title,
                                   printed_offset=doc.offset, figure_pages=figure_pages)
    if not chunks:
        raise StageError("Không tạo được đoạn nào (nội dung sách có thể đang trống).")
    return chunks, build_review(chunks, cfg), _summarize(chunks, nodes, doc, outside, cfg)
