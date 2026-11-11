"use client";

import { useState } from "react";
import { BookOpen, ExternalLink, FileX, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { errorMessage } from "../api";
import { useCitationPassages, useCitationSource } from "../hooks";

export interface CitationRef {
  documentId: string;
  chunkId: string | null;
  pageStart: number | null;
  pageEnd: number | null;
}

function Viewer({ label, ref_, onClose }: { label: string; ref_: CitationRef; onClose: () => void }) {
  const passages = useCitationPassages(ref_.documentId, ref_.pageStart, ref_.pageEnd, ref_.chunkId, true);
  const source = useCitationSource(ref_.documentId, ref_.pageStart, true);
  const pdfUrl = source.data ? `${source.data.url}#page=${source.data.page ?? 1}` : null;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="flex h-[90vh] max-h-[900px] w-[95vw] max-w-6xl flex-col gap-0 overflow-hidden p-0 sm:max-w-6xl sm:rounded-2xl">
        <DialogHeader className="border-b border-border px-6 py-4 text-left">
          <DialogTitle className="font-serif text-lg font-bold">{passages.data?.title || "Tài liệu trích dẫn"}</DialogTitle>
          <DialogDescription className="text-xs">
            {label}
            {ref_.pageStart ? ` · trang PDF ${ref_.pageStart}${ref_.pageEnd && ref_.pageEnd !== ref_.pageStart ? `–${ref_.pageEnd}` : ""}` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
          <div className="min-h-0 space-y-4 overflow-y-auto border-b border-border p-5 lg:border-b-0 lg:border-r">
            <h3 className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">Đoạn đã dẫn trong sách</h3>
            {passages.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-3/4 rounded" />
                <Skeleton className="h-24 w-full rounded" />
              </div>
            ) : passages.isError ? (
              <p className="text-sm text-destructive">{errorMessage(passages.error)}</p>
            ) : passages.data && passages.data.passages.length > 0 ? (
              passages.data.passages.map((p) => (
                <article key={p.chunkId} className={cn("space-y-1.5", p.isCited && "border-l-2 border-brand pl-3")}>
                  <p className="text-xs font-medium text-foreground">
                    {p.section || "Đoạn sách"}
                    {p.pages && <span className="font-normal text-muted-foreground"> · {p.pages}</span>}
                    {p.isCited && <span className="ml-2 font-medium text-brand">· được dẫn</span>}
                  </p>
                  <p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">{p.text}</p>
                </article>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Không tìm thấy đoạn văn bản tương ứng.</p>
            )}
          </div>
          <div className="relative min-h-[24rem] bg-muted/30">
            {source.isLoading ? (
              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                <Loader2 className="mr-2 size-4 animate-spin" /> Đang mở tài liệu…
              </div>
            ) : source.isError || !pdfUrl ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-muted-foreground">
                <FileX className="size-8 opacity-40" />
                <p className="text-sm">{source.isError ? errorMessage(source.error) : "Không mở được tệp tài liệu gốc."}</p>
              </div>
            ) : (
              <>
                <iframe key={pdfUrl} src={pdfUrl} title="Tài liệu gốc" className="size-full border-0" />
                <a
                  href={pdfUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-lg border border-border bg-background/90 px-2.5 py-1 text-xs text-muted-foreground shadow-sm backdrop-blur transition-colors hover:text-foreground"
                >
                  <ExternalLink className="size-3" /> Mở tab mới
                </a>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Trích dẫn dạng nút: có `ref` thì bấm mở tài liệu gốc ở đúng trang kèm đoạn văn đã dẫn; không có (ca cũ) thì hiện chữ thường
export function CitationButton({ label, citation }: { label: string; citation: CitationRef | null }) {
  const [open, setOpen] = useState(false);
  if (!citation) return <>{label}</>;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="group inline-flex max-w-full items-center gap-1.5 rounded-md text-left text-brand underline-offset-2 transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
      >
        <BookOpen className="size-3 shrink-0" />
        <span className="truncate">{label}</span>
      </button>
      {open && <Viewer label={label} ref_={citation} onClose={() => setOpen(false)} />}
    </>
  );
}
