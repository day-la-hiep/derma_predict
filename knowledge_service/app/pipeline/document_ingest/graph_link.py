"""Khớp chữ trong sách vào nút PrimeKG / DermO"""
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from .graph_schema import ENTITY_TYPES

_SUFFIX = re.compile(r"\s*\((?:disease|disorder)\)$")
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "and", "of", "with", "due", "to", "in", "or", "type", "disease", "syndrome", "disorder"}


def norm(text: str, case_sensitive: bool = False) -> str:
    s = " ".join(unicodedata.normalize("NFC", text).split()).strip(" .,;:-")
    return s if case_sensitive else _SUFFIX.sub("", s.lower())


def variants(text: str, case_sensitive: bool = False) -> list[str]:
    """PrimeKG đảo tên kiểu "dermatitis, atopic"; sách/LLM viết "atopic dermatitis"."""
    n = norm(text, case_sensitive)
    parts = [p.strip() for p in n.split(",")]
    return list(dict.fromkeys([n, " ".join(reversed(parts))] if len(parts) == 2 else [n]))


def slug(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:60] or "x"


def new_node_id(type_: str, text: str) -> str:
    # tất định để hai tài liệu cùng đề xuất một thực thể mới thì gộp về một nút
    return f"doc_{slug(type_)}_{slug(text)}"


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) >= 3 and t not in _STOP}


@dataclass
class LexEntry:
    id: str
    name: str
    type: str
    source: str
    kg: str
    aliases: list[str] = field(default_factory=list)
    rank: int = 0  # cao hơn = ưu tiên khi nhiều nút cùng tên (vd nút đã có trong subgraph da liễu của Neo4j)


class EntityLexicon:
    def __init__(self, entries: Iterable[LexEntry] = ()) -> None:
        self._by_key: dict[tuple[str, str], LexEntry] = {}
        self._exact: dict[str, dict[str, list[str]]] = {}
        self._postings: dict[str, dict[str, set[str]]] = {}
        for e in entries:
            self.add(e)

    def __len__(self) -> int:
        return len(self._by_key)

    def add(self, e: LexEntry) -> None:
        cs = ENTITY_TYPES[e.type].case_sensitive if e.type in ENTITY_TYPES else False
        self._by_key[(e.type, e.id)] = e
        exact, postings = self._exact.setdefault(e.type, {}), self._postings.setdefault(e.type, {})
        for name in [e.name, *e.aliases]:
            for v in variants(name, cs):
                ids = exact.setdefault(v, [])
                if e.id not in ids:
                    ids.append(e.id)
            for t in _tokens(name):
                postings.setdefault(t, set()).add(e.id)

    def add_alias(self, type_: str, id_: str, alias: str) -> None:
        e = self._by_key.get((type_, id_))
        if e is not None and alias not in e.aliases:
            e.aliases.append(alias)
            self.add(e)

    def get(self, type_: str, id_: str) -> LexEntry | None:
        return self._by_key.get((type_, id_))

    def exact(self, type_: str, text: str) -> list[LexEntry]:
        cs = ENTITY_TYPES[type_].case_sensitive if type_ in ENTITY_TYPES else False
        exact = self._exact.get(type_, {})
        ids = list(dict.fromkeys(i for v in variants(text, cs) for i in exact.get(v, [])))
        hits = [self._by_key[(type_, i)] for i in ids]
        q = norm(text, cs)
        return sorted(hits, key=lambda e: (e.rank, norm(e.name, cs) == q), reverse=True)

    def candidates(self, type_: str, text: str, k: int = 8) -> list[LexEntry]:
        """Ứng viên chung từ khoá, xếp theo độ trùng (Jaccard) rồi tên ngắn — cho LLM chọn, không tự nhận."""
        q = _tokens(text)
        if not q:
            return []
        postings = self._postings.get(type_, {})
        pool: set[str] = set()
        for t in q:
            # từ quá phổ biến ("skin") không giúp thu hẹp; bỏ khi đã có từ khác
            ids = postings.get(t, set())
            if len(ids) <= 3000 or len(q) == 1:
                pool |= ids
        scored = []
        for i in pool:
            e = self._by_key[(type_, i)]
            names = [e.name, *e.aliases]
            best = max(len(q & (tk := _tokens(n))) / len(q | tk) for n in names if _tokens(n))
            scored.append((best, -len(e.name), e))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [e for s, _, e in scored[:k] if s > 0]

    def search(self, type_: str, q: str, k: int = 20) -> list[LexEntry]:
        hits = self.exact(type_, q)
        seen = {e.id for e in hits}
        return (hits + [e for e in self.candidates(type_, q, k) if e.id not in seen])[:k]
