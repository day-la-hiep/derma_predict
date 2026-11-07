"use client";

import { useQuery } from "@tanstack/react-query";
import { ImageOff } from "lucide-react";
import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { documentApi } from "../api";
import { useData, usePage } from "../hooks";
import type { Figure } from "../types";
import { EmptyState, Pager, SearchBox, StepTitle } from "./bits";
import { PageChip } from "./PagePreview";

const PAGE_SIZE = 12;

/** Một hình: ảnh tải bằng axios (cần token) rồi hiển thị qua object URL, kèm trang và chú thích của sách. */
function FigureCard({ documentId, f, onPreview }: { documentId: string; f: Figure; onPreview: (p: number) => void }) {
  const img = useQuery({
    queryKey: ["toc", documentId, "figimg", f.figure_id],
    queryFn: () => documentApi.figureImageUrl(documentId, f.figure_id),
    staleTime: Infinity,
    gcTime: 10 * 60_000,
  });
  return (
    <article className="space-y-2 rounded-2xl border border-border bg-card p-3">
      <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded-lg bg-muted">
        {img.data ? (
          <a href={img.data} target="_blank" rel="noreferrer" title="Mở ảnh gốc">
            <img src={img.data} alt={f.caption || `Hình trang ${f.page}`} className="max-h-full max-w-full object-contain" />
          </a>
        ) : img.isError ? (
          <ImageOff className="size-6 text-muted-foreground" />
        ) : (
          <Skeleton className="size-full" />
        )}
      </div>
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="rounded bg-muted px-1.5 py-0.5 font-mono">{f.figure_id.split(":").pop()}</span>
        <PageChip page={f.page} onOpen={onPreview} />
      </div>
      <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">{f.caption || "(không có chú thích)"}</p>
    </article>
  );
}

/** Danh sách hình ảnh trích từ sách (bước Đọc nội dung, engine docling). */
export function FigureBrowser({ documentId, onPreview }: { documentId: string; onPreview: (p: number) => void }) {
  const [q, setQ] = useState("");
  const [page, setPage] = usePage(q);
  const list = useData(documentId, "figures", { q, page }, () => documentApi.figures(documentId, { q, page, pageSize: PAGE_SIZE }));
  const data = list.data;
  const items = data?.items ?? [];
  const empty = Boolean(data) && items.length === 0;
  // không có hình nào và không đang tìm: sách chưa trích ảnh (khác với tìm không ra)
  if (empty && !q) {
    return (
      <EmptyState
        title="Chưa có hình ảnh"
        hint="Ảnh chỉ được trích khi đọc bằng engine Docling (Cài đặt). Engine pdftotext không trích ảnh."
      />
    );
  }
  return (
    <div className="sticky top-[4.5rem] flex h-[calc(100vh-6rem)] min-h-96 min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-card">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-2">
        <StepTitle step="ingest" />
        <SearchBox value={q} onChange={setQ} placeholder="Tìm chú thích, số trang..." className="w-56" />
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {empty ? (
          <EmptyState title="Không có hình nào phù hợp" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((f) => (
              <FigureCard key={f.figure_id} documentId={documentId} f={f} onPreview={onPreview} />
            ))}
          </div>
        )}
      </div>
      <Pager attached={!empty} page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPage={setPage} />
    </div>
  );
}
