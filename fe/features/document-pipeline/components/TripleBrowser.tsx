"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Ban, Check, Link2, RotateCcw, Search, Undo2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { Chips, EmptyState, Pager, SearchBox, StepTitle, selectCls } from "./bits";
import { PageChip } from "./PagePreview";
import { documentApi } from "../api";
import { useSchemaLabels } from "@/features/graph-schema/hooks";
import { useData, usePage, useUpdateTriples } from "../hooks";
import type { GraphNodeRef, Triple, TripleUpdate } from "../types";

const PAGE_SIZE = 30;

const KG_TONE: Record<string, string> = {
  primekg: "bg-sky-500/10 text-sky-700 dark:text-sky-400",
  dermo: "bg-violet-500/10 text-violet-700 dark:text-violet-400",
  doc: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
};

const METHOD_HINT: Record<string, string> = {
  exact: "Khớp chính xác tên (hoặc đồng nghĩa DermO).",
  llm: "AI chọn trong các nút có tên gần giống — nên kiểm tra.",
  manual: "Bạn đã chọn nút này.",
  new: "Thực thể mới, chưa có trong PrimeKG/DermO: chỉ được lưu khi bạn chấp nhận.",
};

/** Tìm nút cùng loại để gán tay cho một đầu của quan hệ. */
function NodePicker({ side, onPick, onClose }: { side: GraphNodeRef; onPick: (id: string) => void; onClose: () => void }) {
  const [q, setQ] = useState(side.en || side.text);
  const [term, setTerm] = useState(q);
  const res = useQuery({
    queryKey: ["toc", "graph-nodes", side.type, term],
    queryFn: () => documentApi.searchNodes(side.type, term),
    enabled: term.trim().length >= 2,
  });
  return (
    <div className="space-y-2 rounded-xl border border-border bg-muted/40 p-2">
      <form
        className="flex items-center gap-1.5"
        onSubmit={(e) => {
          e.preventDefault();
          setTerm(q);
        }}
      >
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tên tiếng Anh" className="h-8 rounded-lg text-xs" autoFocus />
        <Button type="submit" size="icon-sm" variant="outline" aria-label="Tìm">
          <Search />
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onClose}>
          Đóng
        </Button>
      </form>
      <ul className="max-h-48 space-y-0.5 overflow-y-auto">
        {(res.data ?? []).map((n) => (
          <li key={`${n.kg}-${n.id}`}>
            <button
              type="button"
              onClick={() => onPick(n.id)}
              className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-left text-xs hover:bg-background"
            >
              <span className={cn("rounded px-1 font-mono text-[10px]", KG_TONE[n.kg])}>{n.source || n.kg}</span>
              <span className="min-w-0 flex-1 truncate text-foreground">{n.name}</span>
              <span className="font-mono text-[10px] text-muted-foreground">{n.id.length > 18 ? n.id.slice(0, 16) + "…" : n.id}</span>
            </button>
          </li>
        ))}
        {res.data && res.data.length === 0 && <li className="px-2 py-1 text-xs text-muted-foreground">Không tìm thấy nút.</li>}
      </ul>
    </div>
  );
}

function Side({ r, picking, onPick, accepted }: { r: GraphNodeRef; picking: boolean; onPick: () => void; accepted: boolean }) {
  const labels = useSchemaLabels();
  const isNew = r.link_method === "new";
  return (
    <div className="min-w-0 flex-1 space-y-0.5">
      <p className="text-[10px] text-muted-foreground">{labels.entity(r.type)}</p>
      <p className="truncate text-xs font-medium text-foreground" title={r.text}>
        {r.text || r.en}
      </p>
      <div className="flex min-w-0 items-center gap-1">
        {r.node_id ? (
          <Hint content={`${METHOD_HINT[r.link_method] ?? ""} ${r.node_id}`}>
            <span className={cn("inline-flex min-w-0 items-center gap-1 rounded px-1.5 py-0.5 text-[11px]", KG_TONE[r.kg])}>
              <span className="truncate">{r.name}</span>
              {isNew && <span className="shrink-0 font-semibold">{accepted || labels.custom(r.type) ? "mới ✓" : "mới"}</span>}
              {r.link_method === "llm" && <span className="shrink-0 opacity-70">AI</span>}
            </span>
          </Hint>
        ) : (
          <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-[11px] text-destructive">chưa khớp</span>
        )}
        <Hint content="Chọn nút đúng trong đồ thị. Áp dụng cho mọi quan hệ có cùng thuật ngữ này trong sách.">
          <Button size="icon-xs" variant="ghost" onClick={onPick} aria-label="Chọn nút" className={cn(picking && "bg-muted")}>
            <Link2 />
          </Button>
        </Hint>
      </div>
    </div>
  );
}

function TripleRow({
  t,
  accepted,
  busy,
  onUpdate,
  onPreview,
}: {
  t: Triple;
  accepted: Set<string>;
  busy: boolean;
  onUpdate: (b: TripleUpdate) => void;
  onPreview: (p: number) => void;
}) {
  const labels = useSchemaLabels();
  const [picking, setPicking] = useState<"subject" | "object" | null>(null);
  const [full, setFull] = useState(false);
  const sides = { subject: t.subject, object: t.object };
  const newIds = [t.subject, t.object].filter((s) => s.link_method === "new" && s.node_id && !labels.custom(s.type)).map((s) => s.node_id as string);
  const manual = (["subject", "object"] as const).filter((k) => sides[k].link_method === "manual");
  return (
    <>
      <TableRow className={cn(t.status === "rejected" && "opacity-60", t.status === "unlinked" && "bg-amber-500/[0.07]", picking && "border-b-0")}>
        <TableCell className="w-52 max-w-52">
          <Side r={t.subject} accepted={accepted.has(t.subject.node_id ?? "")} picking={picking === "subject"} onPick={() => setPicking(picking === "subject" ? null : "subject")} />
        </TableCell>
        <TableCell className="w-px">
          <span className="inline-flex items-center gap-1 whitespace-nowrap">
            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-foreground" title={t.relation}>
              {labels.relation(t.relation)}
            </span>
            <ArrowRight className="size-3.5 text-muted-foreground" />
          </span>
        </TableCell>
        <TableCell className="w-52 max-w-52">
          <Side r={t.object} accepted={accepted.has(t.object.node_id ?? "")} picking={picking === "object"} onPick={() => setPicking(picking === "object" ? null : "object")} />
        </TableCell>
        <TableCell className="max-w-xs whitespace-normal">
          <button type="button" onClick={() => setFull(!full)} className="cursor-pointer text-left" title={full ? "Thu gọn" : "Xem đầy đủ"}>
            <span className={cn("block border-l-2 border-border pl-2 text-xs leading-relaxed text-muted-foreground italic", !full && "line-clamp-2")}>“{t.evidence}”</span>
          </button>
        </TableCell>
        <TableCell>
          <span className="flex flex-wrap gap-1">
            {t.pages.map((p) => (
              <PageChip key={p} page={p} onOpen={onPreview} />
            ))}
          </span>
        </TableCell>
        <TableCell>
          <div className="flex flex-wrap justify-end gap-1">
            {manual.length > 0 && (
              <Button size="xs" variant="ghost" disabled={busy} onClick={() => onUpdate({ relink: manual.map((side) => ({ triple_id: t.triple_id, side, node_id: null })) })}>
                <Undo2 /> Bỏ sửa
              </Button>
            )}
            {newIds.length > 0 &&
              (newIds.every((id) => accepted.has(id)) ? (
                <Button size="xs" variant="ghost" disabled={busy} onClick={() => onUpdate({ unaccept_nodes: newIds })}>
                  <RotateCcw /> Bỏ chấp nhận
                </Button>
              ) : (
                <Hint content="Chấp nhận thực thể mới cho mọi quan hệ dùng nó trong sách này.">
                  <Button size="xs" variant="outline" disabled={busy} onClick={() => onUpdate({ accept_nodes: newIds })}>
                    <Check /> Chấp nhận
                  </Button>
                </Hint>
              ))}
            {t.status === "rejected" ? (
              <Button size="xs" variant="ghost" disabled={busy} onClick={() => onUpdate({ restored: [t.triple_id] })}>
                <RotateCcw /> Khôi phục
              </Button>
            ) : (
              <Button size="xs" variant="ghost" disabled={busy} onClick={() => onUpdate({ rejected: [t.triple_id] })}>
                <Ban /> Loại
              </Button>
            )}
          </div>
        </TableCell>
      </TableRow>
      {picking && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={6} className="whitespace-normal">
            <NodePicker
              side={sides[picking]}
              onClose={() => setPicking(null)}
              onPick={(id) => {
                onUpdate({ relink: [{ triple_id: t.triple_id, side: picking, node_id: id }] });
                setPicking(null);
              }}
            />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

export function TripleBrowser({ documentId, onPreview }: { documentId: string; onPreview: (p: number) => void }) {
  const labels = useSchemaLabels();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [relation, setRelation] = useState("");
  const [page, setPage] = usePage(`${q}|${status}|${relation}`);
  const list = useData(documentId, "triples", { q, status, relation, page }, () =>
    documentApi.triples(documentId, { q, status: status === "all" ? "" : status, relation, page, pageSize: PAGE_SIZE })
  );
  const update = useUpdateTriples(documentId);
  const data = list.data;
  const counts = data?.counts ?? {};
  const accepted = new Set(data?.accepted_nodes ?? []);

  return (
    <div className="space-y-4">
      <div className="sticky top-[4.5rem] flex h-[calc(100vh-6rem)] min-h-96 min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-card">
      {/* khối cao bằng khung preview, ghim cùng mốc; chỉ phần bảng cuộn bên trong */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <StepTitle step="graph" />
          <Chips
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "Tất cả", count: counts.all },
              { value: "ok", label: "Đã khớp", count: counts.ok },
              { value: "unlinked", label: "Chưa khớp", count: counts.unlinked },
              { value: "new", label: "Mới", count: counts.new },
              { value: "rejected", label: "Đã loại", count: counts.rejected },
            ]}
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Hint content="Quan hệ do AI trích từ sách, chỉ là gợi ý tham khảo, không phải chẩn đoán y khoa.">
            <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground">gợi ý</span>
          </Hint>
          <select value={relation} onChange={(e) => setRelation(e.target.value)} className={selectCls} aria-label="Loại quan hệ">
            <option value="">Mọi quan hệ</option>
            {Object.entries(counts.by_relation ?? {}).map(([r, n]) => (
              <option key={r} value={r}>
                {labels.relation(r)} ({n})
              </option>
            ))}
          </select>
          <SearchBox value={q} onChange={setQ} placeholder="Tìm thuật ngữ..." className="w-48" />
        </div>
      </div>
      {data && data.items.length === 0 ? (
        <EmptyState title="Không có quan hệ nào phù hợp" />
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Chủ thể</TableHead>
                <TableHead>Quan hệ</TableHead>
                <TableHead>Đối tượng</TableHead>
                <TableHead>Bằng chứng</TableHead>
                <TableHead>Trang</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.items ?? []).map((t) => (
                <TripleRow key={t.triple_id} t={t} accepted={accepted} busy={update.isPending} onUpdate={(b) => update.mutate(b)} onPreview={onPreview} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <Pager attached={!(data && data.items.length === 0)} page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPage={setPage} />
      </div>
    </div>
  );
}
