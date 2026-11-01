"use client";

import { ChevronRight, Download, ListTree, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { Chips, StepTitle, EmptyState, Pager, SearchBox } from "./bits";
import { errorMessage, documentApi } from "../api";
import { LEVEL_TONE } from "../constants";
import { useData, usePage } from "../hooks";
import type { Chunk, TocDoc, TocEntry } from "../types";
import { PageChip } from "./PagePreview";

const PAGE_SIZE = 20;

/** Cây điều hướng part → section → mục (chỉ mục có chunk). Mục con hiện khi cha được mở. */
function TocNav({
  entries,
  perNode,
  selected,
  onSelect,
}: {
  entries: TocEntry[];
  perNode: Record<string, number>;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const withChunks = useMemo(() => entries.filter((e) => perNode[e.id]), [entries, perNode]);
  const hasChild = useMemo(() => new Set(withChunks.map((e) => e.parent_id).filter(Boolean) as string[]), [withChunks]);
  const byId = useMemo(() => new Map(withChunks.map((e) => [e.id, e])), [withChunks]);
  // mục hiển thị khi mọi tổ tiên (còn trong cây) đang mở
  const visible = withChunks.filter((e) => {
    let p = e.parent_id ? byId.get(e.parent_id) : undefined;
    while (p) {
      if (!open.has(p.id)) return false;
      p = p.parent_id ? byId.get(p.parent_id) : undefined;
    }
    return true;
  });
  const toggle = (id: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (!n.delete(id)) n.add(id);
      return n;
    });

  return (
    <nav className="max-h-[70vh] space-y-0.5 overflow-y-auto pr-1" aria-label="Mục lục">
      <button
        type="button"
        onClick={() => onSelect("")}
        className={cn(
          "flex w-full cursor-pointer items-center rounded-lg px-2 py-1 text-left text-xs font-medium transition-colors",
          selected === "" ? "bg-brand/10 text-brand" : "text-muted-foreground hover:bg-muted"
        )}
      >
        Toàn bộ sách
      </button>
      {visible.map((e) => (
        <div
          key={e.id}
          className={cn(
            "flex items-center gap-0.5 rounded-lg pr-1.5 transition-colors",
            selected === e.id ? "bg-brand/10" : "hover:bg-muted"
          )}
          style={{ paddingLeft: `${e.level * 12}px` }}
        >
          {hasChild.has(e.id) ? (
            <button
              type="button"
              onClick={() => toggle(e.id)}
              className="flex size-5 shrink-0 cursor-pointer items-center justify-center text-muted-foreground"
              aria-label={open.has(e.id) ? "Thu gọn" : "Mở rộng"}
            >
              <ChevronRight className={cn("size-3 transition-transform", open.has(e.id) && "rotate-90")} />
            </button>
          ) : (
            <span className="size-5 shrink-0" />
          )}
          <button
            type="button"
            onClick={() => onSelect(e.id)}
            className={cn("min-w-0 flex-1 cursor-pointer truncate py-1 text-left text-xs", e.level <= 1 && "font-semibold", selected === e.id ? "text-brand" : LEVEL_TONE[e.level])}
            title={e.title}
          >
            {e.title}
          </button>
          <span className="font-mono text-[10px] text-muted-foreground tabular-nums">{perNode[e.id]}</span>
        </div>
      ))}
    </nav>
  );
}

const FLAG = "rounded bg-amber-500/10 px-1.5 py-0.5 text-[11px] whitespace-nowrap text-amber-600 dark:text-amber-400";

function ChunkRow({ c, onPreview, previewPage }: { c: Chunk; onPreview: (p: number) => void; previewPage: number }) {
  const [open, setOpen] = useState(false);
  const crumbs = [c.part, c.section, c.topic, c.subtopic].filter(Boolean);
  const words = Math.round(c.tokens / 1.3);
  const lengthWarn = Boolean(c.review_reason && /dài|ngắn/.test(c.review_reason));
  return (
    <>
      <TableRow className="cursor-pointer" onClick={() => setOpen(!open)} aria-expanded={open}>
        <TableCell className="font-mono text-xs text-muted-foreground">{c.chunk_id.split(":").pop()}</TableCell>
        <TableCell className="max-w-56 whitespace-normal">
          <p className="truncate text-xs font-medium text-foreground" title={crumbs.join(" › ")}>
            {crumbs[crumbs.length - 1] ?? <span className="font-normal text-muted-foreground italic">(không thuộc mục nào)</span>}
          </p>
          {crumbs.length > 1 && <p className="truncate text-[11px] text-muted-foreground" title={crumbs.join(" › ")}>{crumbs.slice(0, -1).join(" › ")}</p>}
        </TableCell>
        <TableCell onClick={(e) => e.stopPropagation()}>
          <span className="flex flex-wrap items-center gap-1">
            <PageChip page={c.page_start} onOpen={onPreview} active={previewPage >= c.page_start && previewPage <= c.page_end} />
            {c.page_end !== c.page_start && <PageChip page={c.page_end} onOpen={onPreview} />}
          </span>
        </TableCell>
        <TableCell className="text-xs whitespace-nowrap text-muted-foreground tabular-nums" title="Trang in của sách">
          {c.page_printed_start}
          {c.page_printed_end !== c.page_printed_start && `–${c.page_printed_end}`}
        </TableCell>
        <TableCell className={cn("text-xs whitespace-nowrap tabular-nums", lengthWarn ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")}>
          ~{words}
        </TableCell>
        <TableCell>
          <span className="flex flex-wrap gap-1">
            {c.boundary && <span className={FLAG} title="Chưa tìm thấy dòng tiêu đề của mục: vị trí bắt đầu mục chỉ chính xác đến trang">vị trí chưa chắc</span>}
            {c.suspect && <span className={FLAG}>mục cần kiểm tra</span>}
            {c.figure_ids?.length > 0 && <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] whitespace-nowrap text-muted-foreground" title="Hình ảnh nằm trong khoảng trang của đoạn này">{c.figure_ids.length} hình</span>}
          </span>
        </TableCell>
        <TableCell className="max-w-xs whitespace-normal">
          <p className="line-clamp-2 text-xs text-muted-foreground">{c.text}</p>
        </TableCell>
        <TableCell className="w-8 pr-3">
          <ChevronRight className={cn("size-3.5 text-muted-foreground transition-transform", open && "rotate-90")} />
        </TableCell>
      </TableRow>
      {open && (
        <TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableCell colSpan={8} className="space-y-2 whitespace-normal">
            {c.pages_hint && (
              <p className="text-[11px] text-muted-foreground">
                Khoảng trang của mục theo mục lục: tr.{c.pages_hint[0]}
                {c.pages_hint[1] !== c.pages_hint[0] && `–${c.pages_hint[1]}`}
              </p>
            )}
            <p className="text-xs leading-relaxed whitespace-pre-wrap text-foreground">{c.text}</p>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

export function ChunkBrowser({
  documentId,
  toc,
  previewPage,
  onPreview,
}: {
  documentId: string;
  toc?: TocDoc;
  previewPage: number;
  onPreview: (p: number) => void;
}) {
  const [q, setQ] = useState("");
  const [node, setNode] = useState("");
  const [only, setOnly] = useState("all");
  const [tocOpen, setTocOpen] = useState(false);
  const [page, setPage] = usePage(`${q}|${node}|${only}`);
  const list = useData(documentId, "chunks", { q, node, only, page }, () =>
    documentApi.chunks(documentId, { q, node, only_review: only === "review", page, pageSize: PAGE_SIZE })
  );
  const data = list.data;
  const counts = data?.counts ?? {};
  const selectedEntry = toc?.entries.find((e) => e.id === node);

  const download = async () => {
    try {
      const url = URL.createObjectURL(await documentApi.exportChunks(documentId));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${documentId}-chunks.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  return (
    <div className="sticky top-[4.5rem] flex h-[calc(100vh-6rem)] min-h-96 min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-card">
        {/* khối cao bằng khung preview, ghim cùng mốc; chỉ phần bảng cuộn bên trong */}
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
          <StepTitle step="chunks" />
          <Popover open={tocOpen} onOpenChange={setTocOpen}>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm">
                <ListTree /> {selectedEntry ? <span className="max-w-48 truncate">{selectedEntry.title}</span> : "Mục lục"}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-80 p-2">
              {toc ? (
                <TocNav entries={toc.entries} perNode={counts.per_node ?? {}} selected={node} onSelect={(id) => { setNode(id); setTocOpen(false); }} />
              ) : (
                <p className="px-1 text-xs text-muted-foreground">Chưa có mục lục.</p>
              )}
            </PopoverContent>
          </Popover>
          {node && (
            <Button variant="ghost" size="icon-xs" onClick={() => setNode("")} aria-label="Bỏ lọc mục lục">
              <X />
            </Button>
          )}
          <Chips
            value={only}
            onChange={setOnly}
            options={[
              { value: "all", label: "Tất cả", count: counts.all },
              { value: "review", label: "Cần xem lại", count: counts.review },
            ]}
          />
          </div>
          <div className="flex items-center gap-2">
            <SearchBox value={q} onChange={setQ} placeholder="Tìm trong nội dung..." className="w-52" />
            <Button variant="outline" size="sm" onClick={download}>
              <Download /> Tải xuống
            </Button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
        {data && (data.items ?? []).length === 0 ? (
          <EmptyState title="Không có đoạn nào phù hợp" />
        ) : (
          <div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Mã</TableHead>
                  <TableHead>Mục</TableHead>
                  <TableHead>Trang PDF</TableHead>
                  <TableHead>Trang in</TableHead>
                  <TableHead>Số từ</TableHead>
                  <TableHead>Lưu ý</TableHead>
                  <TableHead>Nội dung</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.items ?? []).map((c) => (
                  <ChunkRow key={c.chunk_id} c={c} onPreview={onPreview} previewPage={previewPage} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        </div>
        <Pager attached={!(data && (data.items ?? []).length === 0)} page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPage={setPage} />
    </div>
  );
}
