"""Dựng cây node / sub node từ dữ liệu debug (`events` có `ns`, `calls`, `tools`) cho tab Timeline và Cây node của `debug_app.py`."""
from typing import Any

_TOL = 50  # ms, dung sai khi ghép lần gọi LLM / tool vào node chứa nó


def spans(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Mỗi event thành một khoảng thời gian có `path` (ns + tên node); node chứa node khác là `container`."""
    last_end: dict[str, int] = {}
    prev_same: dict[tuple[str, ...], int] = {}
    used: set[int] = set()
    starts = d.get("starts", [])
    out: list[dict[str, Any]] = []
    for i, e in enumerate(d["events"]):
        path = (*[p for p in e["ns"].split("/") if p], e["node"])
        start = last_end.get(e["ns"], 0)
        # Lúc bắt đầu thật do callback ghi (`starts`); file cũ không có thì suy ra từ node trước, rồi từ lần gọi LLM đầu tiên của chính node
        # (node chạy song song cùng graph con không bắt đầu lúc node trước kết thúc).
        real = next((n for n, st in enumerate(starts) if n not in used and tuple(st["path"]) == path and st["t"] <= e["t"] + _TOL), None)
        if real is not None:
            used.add(real)
            start = starts[real]["t"]
        else:
            own = [c["t"] for c in d["calls"] if c["node"] == e["node"] and prev_same.get(path, -1) <= c["t"] <= e["t"]]
            if own:
                start = min(start, min(own))
        last_end[e["ns"]] = e["t"]
        prev_same[path] = e["t"]
        out.append({"i": i, "path": path, "start": start, "end": e["t"]})
    for s in out:
        kids = [c for c in out if c["path"][:-1] == s["path"]]
        s["container"] = bool(kids)
        if kids:  # container kết thúc khi con cuối kết thúc, bắt đầu khi con đầu bắt đầu
            s["start"] = min(c["start"] for c in kids)
            s["end"] = max(s["end"], max(c["end"] for c in kids))
    return out


def tree_rows(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Các hàng theo thứ tự duyệt cây: node (container hoặc lá), rồi tool và lần gọi LLM nằm trong node đó."""
    sp = spans(d)
    calls, tools = d["calls"], d.get("tools", [])
    placed_calls: set[int] = set()
    placed_tools: set[int] = set()

    def inside(t: int, s: dict[str, Any]) -> bool:
        return s["start"] - _TOL <= t <= s["end"] + _TOL

    def build(s: dict[str, Any], depth: int) -> list[dict[str, Any]]:
        name = s["path"][-1]
        key = "/".join(s["path"])  # khoá dòng trên biểu đồ: cùng node lặp lại nhiều vòng thì chung dòng, node khác nhau thì không
        rows = [{"depth": depth, "kind": "container" if s["container"] else "node", "name": name, "key": key, "start": s["start"], "end": s["end"], "ref": s["i"]}]
        if s["container"]:
            kids = sorted((c for c in sp if c["path"][:-1] == s["path"]), key=lambda c: (c["start"], c["end"]))
            for k in kids:
                rows += build(k, depth + 1)
            return rows
        def owns(t: dict[str, Any]) -> bool:
            # `node` do callback ghi (tool chạy trong node nào); file lưu cũ không có thì chỉ biết tool chạy trong node `tools`.
            return t.get("node", "tools") == name and inside(t["t"], s)

        for j, t in sorted(((j, t) for j, t in enumerate(tools) if j not in placed_tools and owns(t)), key=lambda jt: jt[1]["t"]):
            placed_tools.add(j)
            parent = next((r for r in reversed(rows) if r["kind"] == "tool" and r["name"] == t.get("in_tool") and r["start"] - _TOL <= t["t"] <= r["end"] + _TOL), None)
            rows.append({"depth": parent["depth"] + 1 if parent else depth + 1, "kind": "tool", "name": t["name"], "key": f"{parent['key'] if parent else key}/{t['name']}", "start": t["t"], "end": t["t"] + t.get("ms", 1), "ref": j})
        for j, c in enumerate(calls):
            if j in placed_calls or c["node"] != name or not inside(c["t"], s):
                continue
            placed_calls.add(j)
            parent = next((r for r in reversed(rows) if r["kind"] == "tool" and r["name"] == c.get("in_tool") and r["start"] - _TOL <= c["t"] <= r["end"] + _TOL), None)
            label = f"LLM · {c['model'].split('/')[-1]}" + (f" (trong tool {c['in_tool']})" if c.get("in_tool") else "")
            rows.append({"depth": parent["depth"] + 1 if parent else depth + 1, "kind": "llm", "name": label, "key": f"{parent['key'] if parent else key}/{label}", "start": c["t"], "end": c["t"] + c.get("ms", 1), "ref": j})
        return rows

    rows: list[dict[str, Any]] = []
    for r in sorted((s for s in sp if len(s["path"]) == 1), key=lambda s: (s["start"], s["end"])):
        rows += build(r, 0)
    return rows


def fmt_ms(ms: int | float) -> str:
    """Thời lượng theo đơn vị vừa đủ nhỏ: dưới 1s hiện ms, từ 1s hiện giây."""
    return f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.2f} s"


def tree_text(rows: list[dict[str, Any]]) -> str:
    """Cây dạng chữ có nét nối (├─ └─ │), mỗi dòng kèm thời lượng và khoảng thời gian."""
    lines: list[str] = []
    for i, r in enumerate(rows):
        later = rows[i + 1 :]
        end_of_siblings = next((x["depth"] for x in later if x["depth"] <= r["depth"]), -1)
        r["last"] = end_of_siblings < r["depth"]
    ancestors_last: list[bool] = []
    for r in rows:
        del ancestors_last[r["depth"] :]
        prefix = "".join("   " if last else "│  " for last in ancestors_last)
        branch = "" if r["depth"] == 0 else ("└─ " if r["last"] else "├─ ")
        mark = {"container": "▣", "node": "□", "llm": "◆", "tool": "▲"}[r["kind"]]
        lines.append(f"{prefix}{branch}{mark} {r['name']}  {fmt_ms(r['end'] - r['start'])}  [{r['start'] / 1000:.2f}s → {r['end'] / 1000:.2f}s]")
        ancestors_last.append(r["last"])
    return "\n".join(lines)


def lane(r: dict[str, Any]) -> str:
    """Nhãn trục Y: thụt lề theo độ sâu để thấy node nào nằm trong node nào."""
    indent = "  " * r["depth"]
    return f"{indent}{'└ ' if r['depth'] else ''}{r['name']}"
