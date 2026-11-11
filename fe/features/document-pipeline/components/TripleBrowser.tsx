"use client";

import { ArrowRight, Ban, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
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
};

function Side({ r }: { r: GraphNodeRef }) {
  const labels = useSchemaLabels();
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
              {r.link_method === "llm" && <span className="shrink-0 opacity-70">AI</span>}
            </span>
          </Hint>
        ) : (
          <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-[11px] text-destructive">chưa khớp</span>
        )}
      </div>
    </div>
  );
}

function TripleRow({
  t,
  busy,
  onUpdate,
  onPreview,
}: {
  t: Triple;
  busy: boolean;
  onUpdate: (b: TripleUpdate) => void;
  onPreview: (p: number) => void;
}) {
  const labels = useSchemaLabels();
  const [full, setFull] = useState(false);
  return (
    <>
      <TableRow className={cn(t.status === "rejected" && "opacity-60", t.status === "unlinked" && "bg-amber-500/[0.07]")}>
        <TableCell className="w-52 max-w-52">
          <Side r={t.subject} />
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
          <Side r={t.object} />
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
                <TripleRow key={t.triple_id} t={t} busy={update.isPending} onUpdate={(b) => update.mutate(b)} onPreview={onPreview} />
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
