"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpen, FileUp, Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Hint, HintIcon } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn, formatBytes, formatRelativeTime } from "@/lib/utils";
import { ConfirmDialog } from "@/features/document-pipeline/components/ConfirmDialog";
import { EmptyState, StateBadge } from "@/features/document-pipeline/components/bits";
import { errorMessage, documentApi } from "@/features/document-pipeline/api";
import { STEP_INFO, STEP_ORDER } from "@/features/document-pipeline/constants";
import { qk, useDocument, useDocuments } from "@/features/document-pipeline/hooks";
import type { DocumentSummary, Stage, StageState, StepId } from "@/features/document-pipeline/types";

const selectBox =
  "h-9 w-full cursor-pointer rounded-xl border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function overall(states: DocumentSummary["states"]): StageState {
  const list = STEP_ORDER.map((s) => states[s] ?? "not_started");
  if (list.includes("running")) return "running";
  if (list.includes("failed")) return "failed";
  if (list.includes("pending_review")) return "pending_review";
  if (list.includes("stale")) return "stale";
  if (list.every((s) => s === "approved")) return "approved";
  return list.every((s) => s === "not_started") ? "not_started" : "pending_review";
}

const BAR: Partial<Record<StageState, string>> = {
  approved: "bg-emerald-500",
  running: "animate-pulse bg-brand",
  pending_review: "bg-amber-500",
  failed: "bg-red-500",
  stale: "bg-orange-400",
};

function DocumentRow({
  document,
  selected,
  onSelect,
  onDelete,
}: {
  document: DocumentSummary;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const state = overall(document.states);
  const done = STEP_ORDER.filter((s) => document.states[s] === "approved").length;
  const muted = "align-middle text-xs whitespace-nowrap text-muted-foreground";
  return (
    <TableRow className={cn("cursor-pointer", selected && "bg-brand/5 hover:bg-brand/5")} onClick={onSelect} aria-selected={selected}>
      <TableCell>
        <span className="flex items-center gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
            <BookOpen className="size-4" />
          </span>
          <span className="font-medium text-foreground">{document.title}</span>
        </span>
      </TableCell>
      <TableCell className={muted}>{document.created_at ? formatRelativeTime(document.created_at) : "—"}</TableCell>
      <TableCell className={cn(muted, "tabular-nums")}>{document.pdf_pages ?? "—"}</TableCell>
      <TableCell className={cn(muted, "tabular-nums")}>{document.file_size ? formatBytes(document.file_size) : "—"}</TableCell>
      <TableCell className="align-middle">
        <div className="flex w-40 gap-1">
          {STEP_ORDER.map((s) => (
            <span
              key={s}
              title={`${STEP_INFO[s].label}: ${document.states[s] ?? "not_started"}`}
              className={cn("h-1.5 flex-1 rounded-full bg-muted", BAR[document.states[s] ?? "not_started"])}
            />
          ))}
        </div>
      </TableCell>
      <TableCell className="align-middle"><StateBadge state={state} /></TableCell>
      <TableCell className="align-middle">
        <Hint content={`${done}/${STEP_ORDER.length} bước đã xác nhận`}>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
            {done}/{STEP_ORDER.length}
          </span>
        </Hint>
      </TableCell>
      <TableCell className="align-middle">
        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="icon-xs"
            className="text-muted-foreground hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            aria-label="Xóa sách"
          >
            <Trash2 />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

function num(stage: Stage | undefined, key: string): number | null {
  const v = stage?.summary?.[key];
  return typeof v === "number" ? v : null;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm font-medium text-foreground tabular-nums" title={value}>{value}</dd>
    </div>
  );
}

function DocumentOverview({ document }: { document: DocumentSummary }) {
  const detail = useDocument(document.id).data;
  const stage = (id: StepId) => detail?.stages.find((x) => x.stage_id === id);
  const state = overall(document.states);
  const done = STEP_ORDER.filter((s) => document.states[s] === "approved").length;
  const fmt = (n: number | null, unit = "") => (n === null ? "—" : `${n.toLocaleString("vi-VN")}${unit}`);

  const engine = stage("ingest")?.summary?.engine;
  const tokens = stage("chunks")?.summary?.tokens as { median?: number } | undefined;
  const warnings = (detail?.stages ?? []).reduce(
    (n, st) => n + (Array.isArray(st.summary?.warnings) ? st.summary.warnings.length : 0),
    0,
  );
  const failed = detail?.stages.find((x) => x.state === "failed");
  const running = detail?.stages.find((x) => x.state === "running");
  const lastActivity = (detail?.stages ?? []).map((x) => x.finished_at ?? x.started_at).filter(Boolean).sort().pop();

  const file: [string, string][] = [
    ["Tên file", detail?.source_file?.file_name ?? "—"],
    ["Dung lượng", document.file_size ? formatBytes(document.file_size) : "—"],
    ["Số trang", fmt(document.pdf_pages ?? null)],
    ["Cách đọc", engine === "docling" ? "Nhận dạng từ ảnh" : engine === "pdftotext" ? "Văn bản có sẵn" : "—"],
    ["Ngày tạo", document.created_at ? formatRelativeTime(document.created_at) : "—"],
    ["Hoạt động cuối", lastActivity ? formatRelativeTime(lastActivity) : "—"],
  ];
  const content: [string, string][] = [
    ["Trang đã đọc", fmt(num(stage("ingest"), "pages"))],
    ["Mục mục lục", fmt(num(stage("toc"), "entries"))],
    ["Đoạn nội dung", fmt(num(stage("chunks"), "chunks"))],
    ["Token / đoạn", fmt(tokens?.median ?? null)],
    ["Điểm vector", fmt(num(stage("index"), "points"))],
    ["Quan hệ trích", fmt(num(stage("graph"), "triples"))],
    ["Quan hệ hợp lệ", fmt(num(stage("graph"), "ok"))],
    ["Cạnh trong đồ thị", fmt(num(stage("graph_index"), "edges"))],
  ];

  return (
    <>
      <SheetHeader className="pr-12">
        <SheetTitle className="text-base font-semibold tracking-tight">{document.title}</SheetTitle>
        <SheetDescription asChild>
          <div className="flex flex-wrap items-center gap-2">
            <StateBadge state={state} />
            <span className="text-[11px] text-muted-foreground">{done}/{STEP_ORDER.length} bước đã xác nhận</span>
          </div>
        </SheetDescription>
      </SheetHeader>
      <div className="space-y-5 px-4 pb-6">

      {(failed || running || warnings > 0) && (
        <div className="space-y-1.5">
          {running && (
            <p className="rounded-xl bg-brand/10 px-3 py-2 text-xs text-brand">
              Đang chạy: {STEP_INFO[running.stage_id].label}
              {running.progress ? ` (${running.progress.done}/${running.progress.total})` : ""}
            </p>
          )}
          {failed && (
            <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
              Lỗi ở bước {STEP_INFO[failed.stage_id].label}{failed.error ? `: ${failed.error}` : ""}
            </p>
          )}
          {warnings > 0 && (
            <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              {warnings} cảnh báo trong các bước, xem trong pipeline.
            </p>
          )}
        </div>
      )}

      <Section title="File">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
          {file.map(([k, v]) => <Stat key={k} label={k} value={v} />)}
        </dl>
      </Section>

      <Section title="Nội dung đã xử lý">
        {detail ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            {content.map(([k, v]) => <Stat key={k} label={k} value={v} />)}
          </dl>
        ) : (
          <Skeleton className="h-24 rounded-xl" />
        )}
      </Section>

      <Section title="Các bước">
        <ul className="space-y-1.5">
          {STEP_ORDER.map((s) => {
            const Icon = STEP_INFO[s].icon;
            const at = stage(s)?.approved_at ?? stage(s)?.finished_at;
            return (
              <li key={s} className="flex items-center justify-between gap-2 rounded-xl border border-border bg-background px-3 py-2">
                <span className="min-w-0">
                  <span className="flex items-center gap-2 text-xs font-medium text-foreground">
                    <Icon className="size-3.5 text-muted-foreground" />
                    {STEP_INFO[s].label}
                  </span>
                  {at && <span className="ml-5.5 block text-[10px] text-muted-foreground">{formatRelativeTime(at)}</span>}
                </span>
                <StateBadge state={document.states[s] ?? "not_started"} />
              </li>
            );
          })}
        </ul>
      </Section>

      <Button className="w-full" asChild>
        <Link href={`/admin/documents/${encodeURIComponent(document.id)}`}>
          Vào pipeline <ArrowRight />
        </Link>
      </Button>
      </div>
    </>
  );
}

function CreateDocumentDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [engine, setEngine] = useState("pdftotext");

  const create = useMutation({
    mutationFn: () => documentApi.createDocument({ file: file as File, title, engine }),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: qk.documents });
      toast.success(`Đã tạo sách “${b.title}”.`);
      onOpenChange(false);
      router.push(`/admin/documents/${encodeURIComponent(b.id)}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Thêm sách mới</DialogTitle>
          <DialogDescription>Tải lên file PDF của sách.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex w-full cursor-pointer flex-col items-center gap-2 rounded-2xl border border-dashed border-border bg-muted/30 px-4 py-8 text-center transition-colors hover:border-brand/40 hover:bg-brand/5"
          >
            <FileUp className="size-6 text-muted-foreground" />
            {file ? (
              <span className="text-sm font-medium text-foreground">
                {file.name} <span className="font-normal text-muted-foreground">· {formatBytes(file.size)}</span>
              </span>
            ) : (
              <span className="text-sm text-muted-foreground">Chọn file PDF</span>
            )}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              if (f && !title) setTitle(f.name.replace(/\.pdf$/i, ""));
            }}
          />
          <label className="block space-y-1">
            <span className="text-xs font-medium text-foreground">Tên sách</span>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} className="h-9 rounded-xl text-sm" />
          </label>
          <label className="block space-y-1">
            <span className="flex items-center gap-1 text-xs font-medium text-foreground">
              Cách đọc
              <HintIcon content="Văn bản có sẵn: nhanh. Nhận dạng từ ảnh: chậm, dùng khi PDF là bản scan hoặc chữ bị vỡ, sai dấu. Có thể đổi lại trong Cài đặt." />
            </span>
            <select value={engine} onChange={(e) => setEngine(e.target.value)} className={selectBox}>
              <option value="pdftotext">Văn bản có sẵn</option>
              <option value="docling">Nhận dạng từ ảnh</option>
            </select>
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={create.isPending}>
            Hủy
          </Button>
          <Button onClick={() => create.mutate()} disabled={!file || !title.trim() || create.isPending}>
            {create.isPending && <Loader2 className="animate-spin" />}
            {create.isPending ? "Đang tải lên..." : "Thêm sách"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function TocDocumentsPage() {
  const books = useDocuments();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = books.data?.find((b) => b.id === selectedId) ?? null;
  const [deleting, setDeleting] = useState<DocumentSummary | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) => documentApi.deleteDocument(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.documents });
      toast.success("Đã xóa sách.");
      setDeleting(null);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const actions = (
    <div className="flex flex-wrap gap-2">
      <Button onClick={() => setCreating(true)}>
        <Plus /> Thêm sách
      </Button>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-foreground">
            Sách giáo khoa
            <HintIcon
              side="right"
              content="Biến sách PDF thành các đoạn nội dung có ghi rõ nguồn (phần, chương, bài, số trang), làm nền tri thức cho trợ lý AI. Cấu trúc lấy từ mục lục của sách; bạn kiểm tra và xác nhận từng bước."
            />
          </h1>
        </div>
        {actions}
      </div>

      {books.isLoading ? (
        <Skeleton className="h-48 rounded-2xl" />
      ) : books.isError ? (
        <EmptyState title="Không tải được danh sách sách" hint={errorMessage(books.error)} action={<Button variant="outline" onClick={() => books.refetch()}>Thử lại</Button>} />
      ) : books.data && books.data.length > 0 ? (
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tên sách</TableHead>
                <TableHead>Ngày tạo</TableHead>
                <TableHead>Số trang</TableHead>
                <TableHead>Dung lượng</TableHead>
                <TableHead>Tiến độ</TableHead>
                <TableHead>Trạng thái</TableHead>
                <TableHead>Đã xác nhận</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {books.data.map((b) => (
                <DocumentRow
                  key={b.id}
                  document={b}
                  selected={selected?.id === b.id}
                  onSelect={() => setSelectedId(b.id)}
                  onDelete={() => setDeleting(b)}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <EmptyState title="Chưa có sách nào" hint="Thêm file PDF để bắt đầu." action={actions} />
      )}

      <Sheet open={selected !== null} onOpenChange={(o) => !o && setSelectedId(null)}>
        <SheetContent side="right" className="w-full gap-0 overflow-y-auto sm:max-w-xl">
          {selected && <DocumentOverview document={selected} />}
        </SheetContent>
      </Sheet>
      <CreateDocumentDialog key={`c-${creating}`} open={creating} onOpenChange={setCreating} />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Xóa “${deleting?.title ?? ""}”?`}
        description="Xóa toàn bộ file PDF, nội dung đã đọc, mục lục, các đoạn đã chia và chỉnh sửa của sách này. Không thể hoàn tác."
        confirmLabel="Xóa sách"
        destructive
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
      />
    </div>
  );
}
