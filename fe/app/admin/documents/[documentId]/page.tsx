"use client";

import { ArrowLeft, Loader2, PanelRightOpen, Settings2 } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { Topbar } from "@/components/layout/sidebar-shell";
import { EmptyState, StateBadge } from "@/features/document-pipeline/components/bits";
import { errorMessage, documentApi } from "@/features/document-pipeline/api";
import { ChunkBrowser } from "@/features/document-pipeline/components/ChunkBrowser";
import { FigureBrowser } from "@/features/document-pipeline/components/FigureBrowser";
import { PagePreview } from "@/features/document-pipeline/components/PagePreview";
import { hasRunOptions, RunDialog } from "@/features/document-pipeline/components/RunDialog";
import { SettingsDialog } from "@/features/document-pipeline/components/SettingsDialog";
import { StageLogDialog } from "@/features/document-pipeline/components/StageLogDialog";
import { StagePanel } from "@/features/document-pipeline/components/StagePanel";
import { TocEditor } from "@/features/document-pipeline/components/TocEditor";
import { TripleBrowser } from "@/features/document-pipeline/components/TripleBrowser";
import { STEP_INFO, STEP_ORDER } from "@/features/document-pipeline/constants";
import { useDocument, useData, useStageActions } from "@/features/document-pipeline/hooks";
import type { Document, Stage, StepId, TocEntry } from "@/features/document-pipeline/types";

const HAS_RESULT = ["pending_review", "approved", "stale"];

/** Một dòng tóm tắt dưới tên bước trên thanh các bước. */
function stepLine(stage: Stage): string {
  const s = stage.summary ?? {};
  if (stage.state === "running") return stage.progress?.message || "đang xử lý";
  if (!HAS_RESULT.includes(stage.state)) return "chưa có kết quả";
  if (stage.stage_id === "ingest") return `${s.pages ?? "?"} trang`;
  if (stage.stage_id === "toc") return `${s.entries ?? "?"} mục`;
  if (stage.stage_id === "chunks") return `${s.chunks ?? "?"} đoạn`;
  if (stage.stage_id === "graph") return `${s.ok ?? "?"}/${s.triples ?? "?"} quan hệ đã khớp`;
  if (stage.stage_id === "graph_index") return `${s.edges ?? "?"} cạnh đã lưu`;
  return `${s.points ?? "?"} đoạn đã lưu`;
}

const PREVIEW_KEY = "derma.document.previewCollapsed";

function StepButton({ id, doc, step, onPick }: { id: StepId; doc: Document; step: StepId; onPick: (s: StepId) => void }) {
  const stage = doc.stages.find((s) => s.stage_id === id) as Stage;
  const Icon = STEP_INFO[id].icon;
  const active = id === step;
  return (
    <button
      type="button"
      onClick={() => onPick(id)}
      aria-current={active ? "step" : undefined}
      className={cn(
        "flex w-full cursor-pointer items-center gap-3 rounded-2xl border p-3 text-left transition-colors",
        active ? "border-brand/50 bg-card bg-linear-to-b from-brand/5 to-brand/5" : "border-border bg-card hover:border-brand/30"
      )}
    >
      <span
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-xl",
          stage.state === "approved" ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground",
          active && stage.state !== "approved" && "bg-brand/10 text-brand"
        )}
      >
        <Icon className="size-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-muted-foreground">{STEP_ORDER.indexOf(id) + 1}</span>
          <span className="truncate text-sm font-semibold tracking-tight text-foreground">{STEP_INFO[id].label}</span>
        </span>
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{stepLine(stage)}</span>
      </span>
      <StateBadge state={stage.state} />
    </button>
  );
}

// ô lưới (cột, hàng) của từng bước: ingest/toc song song -> chunks -> index/graph song song -> graph_index
const FLOW_CELLS: Record<StepId, string> = {
  ingest: "col-start-1 row-start-1",
  toc: "col-start-1 row-start-2",
  chunks: "col-start-2 row-span-2 row-start-1 self-center",
  index: "col-start-3 row-start-1",
  graph: "col-start-3 row-start-2",
  graph_index: "col-start-4 row-start-2",
};

// cạnh phụ thuộc, toạ độ % theo tâm ô (4 cột, 2 hàng); khớp `deps` ở `app/models/document_stage.py`
const FLOW_EDGES = [
  "M12.5 25 C25 25 25 50 37.5 50",
  "M12.5 75 C25 75 25 50 37.5 50",
  "M37.5 50 C50 50 50 25 62.5 25",
  "M37.5 50 C50 50 50 75 62.5 75",
  "M62.5 75 L87.5 75",
];

function Stepper({ doc, step, onPick }: { doc: Document; step: StepId; onPick: (s: StepId) => void }) {
  return (
    <nav aria-label="Các bước xử lý">
      <div className="relative hidden xl:block">
        <svg className="pointer-events-none absolute inset-0 size-full text-border" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
          {FLOW_EDGES.map((d) => (
            <path key={d} d={d} fill="none" stroke="currentColor" strokeWidth={2} vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        <ol className="relative grid grid-cols-4 grid-rows-2">
          {STEP_ORDER.map((id) => (
            <li key={id} className={cn("px-4 py-1.5", FLOW_CELLS[id])}>
              <StepButton id={id} doc={doc} step={step} onPick={onPick} />
            </li>
          ))}
        </ol>
      </div>
      <ol className="grid gap-2 sm:grid-cols-2 xl:hidden">
        {STEP_ORDER.map((id) => (
          <li key={id}>
            <StepButton id={id} doc={doc} step={step} onPick={onPick} />
          </li>
        ))}
      </ol>
    </nav>
  );
}

function defaultStep(doc: Document): StepId {
  if (doc.running_stage) return doc.running_stage;
  return STEP_ORDER.find((id) => doc.stages.find((s) => s.stage_id === id)?.state !== "approved") ?? "chunks";
}

export default function TocDocumentPage({ params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = use(params);
  const documentQuery = useDocument(documentId);
  const { run, cancel, approve } = useStageActions(documentId);
  const [picked, setPicked] = useState<StepId | null>(null);
  const [previewPage, setPreviewPage] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [runOpen, setRunOpen] = useState(false);
  const [logStage, setLogStage] = useState<StepId | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // thu gọn khung xem trang nhớ theo trình duyệt (trang chỉ render ở client sau AccessGate)
  const [previewCollapsed, setPreviewCollapsedState] = useState(() => {
    try {
      return localStorage.getItem(PREVIEW_KEY) === "1";
    } catch {
      return false;
    }
  });
  const setPreviewCollapsed = (v: boolean) => {
    setPreviewCollapsedState(v);
    try {
      localStorage.setItem(PREVIEW_KEY, v ? "1" : "0");
    } catch {
      // trình duyệt chặn lưu trữ: vẫn thu gọn được trong phiên này
    }
  };

  const data = documentQuery.data;
  const tocStage = data?.stages.find((s) => s.stage_id === "toc");
  const tocReady = Boolean(tocStage && HAS_RESULT.includes(tocStage.state));
  const toc = useData(documentId, "toc", {}, () => documentApi.toc(documentId), tocReady);

  if (documentQuery.isError) {
    return (
      <EmptyState
        title="Không mở được sách"
        hint={errorMessage(documentQuery.error)}
        action={
          <Button variant="outline" asChild>
            <Link href="/admin/documents">Về danh sách</Link>
          </Button>
        }
      />
    );
  }
  if (!data) return <Skeleton className="h-96 rounded-2xl" />;

  const step = picked ?? defaultStep(data);
  const stage = data.stages.find((s) => s.stage_id === step) as Stage;
  const hasResult = HAS_RESULT.includes(stage.state);
  const busy = run.isPending || cancel.isPending || approve.isPending;
  const runningName = data.running_stage ? STEP_INFO[data.running_stage].label : null;
  const nextStep = STEP_ORDER[STEP_ORDER.indexOf(step) + 1];

  const selected = toc.data?.entries.find((e) => e.id === selectedId) ?? null;
  const page = previewPage ?? selected?.page ?? (step === "toc" ? toc.data?.toc_pages[0] : undefined) ?? 1;
  const caption =
    step === "toc" && selected ? (
      <>
        <span className="font-medium text-foreground">{selected.title}</span> · trang in {selected.page_printed ?? "—"}
        {selected.page != null && selected.page === page && (
          <>
            {" "}→ trang {selected.page} trong file · {selected.anchored ? "đã định vị" : "chưa định vị"}
          </>
        )}
      </>
    ) : step === "toc" && toc.data?.toc_pages.includes(page) ? (
      "Trang mục lục"
    ) : undefined;

  const pick = (s: StepId) => {
    setPicked(s);
    setPreviewPage(null);
  };
  const onSelectEntry = (e: TocEntry) => {
    setSelectedId(e.id);
    setPreviewPage(e.page ?? null);
  };
  const startRun = () => (hasRunOptions(step) ? setRunOpen(true) : run.mutate({ stage: step }));

  return (
    <div className="space-y-5">
      <Topbar>
        <Button variant="ghost" size="icon-sm" asChild aria-label="Về danh sách sách" title="Về danh sách sách">
          <Link href="/admin/documents">
            <ArrowLeft />
          </Link>
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-base font-semibold tracking-tight text-foreground">{data.title}</h1>
          <p className="flex flex-wrap items-center gap-x-3 font-mono text-[10px] text-muted-foreground">
            <span className="truncate">{documentId}</span>
            {data.pdf_pages != null && <span>{data.pdf_pages} trang</span>}
            {runningName && (
              <span className="inline-flex items-center gap-1 text-brand">
                <Loader2 className="size-3 animate-spin" /> đang xử lý: {runningName}
              </span>
            )}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setSettingsOpen(true)}>
          <Settings2 /> Cài đặt
        </Button>
      </Topbar>

      <Stepper doc={data} step={step} onPick={pick} />

      <div className={cn("grid items-start gap-5", previewCollapsed ? "xl:grid-cols-[minmax(0,1fr)_3rem]" : "xl:grid-cols-[minmax(0,1fr)_26rem]")}>
        <div className="min-w-0 space-y-4">
          <StagePanel
            stage={stage}
            busy={busy}
            anotherRunning={Boolean(data.running_stage) && data.running_stage !== step}
            onRun={startRun}
            onCancel={() => cancel.mutate(step)}
            onApprove={() => approve.mutate(step)}
            onLog={() => setLogStage(step)}
            onNext={nextStep ? () => pick(nextStep) : undefined}
          />

          {step === "ingest" && hasResult && <FigureBrowser documentId={documentId} onPreview={(p) => setPreviewPage(p)} />}
          {step === "toc" &&
            (hasResult && toc.data ? (
              <TocEditor documentId={documentId} doc={toc.data} selectedId={selectedId} onSelect={onSelectEntry} onPreview={(p) => setPreviewPage(p)} />
            ) : (
              !["running"].includes(stage.state) && (
                <EmptyState
                  title="Chưa đọc mục lục"
                  hint="Nhấn Bắt đầu để AI đọc mục lục."
                />
              )
            ))}
          {step === "index" && !hasResult && stage.state !== "running" && (
            <EmptyState
              title="Chưa lưu vào kho tri thức"
              hint="Làm sau khi đã xác nhận Chia đoạn."
            />
          )}
          {step === "graph" &&
            (hasResult ? (
              <TripleBrowser documentId={documentId} onPreview={(p) => setPreviewPage(p)} />
            ) : (
              stage.state !== "running" && <EmptyState title="Chưa trích quan hệ" hint="Làm sau khi đã xác nhận Chia đoạn." />
            ))}
          {step === "graph_index" && !hasResult && stage.state !== "running" && (
            <EmptyState title="Chưa lưu vào đồ thị" hint="Làm sau khi đã xác nhận Trích quan hệ." />
          )}
          {step === "chunks" &&
            (hasResult ? (
              <ChunkBrowser documentId={documentId} toc={toc.data} previewPage={page} onPreview={(p) => setPreviewPage(p)} />
            ) : (
              stage.state !== "running" && (
                <EmptyState title="Chưa có đoạn nội dung" hint="Làm sau khi đã xác nhận Đọc nội dung và Mục lục." />
              )
            ))}
        </div>

        {data.source_file &&
          (previewCollapsed ? (
            <button
              type="button"
              onClick={() => setPreviewCollapsed(false)}
              aria-label="Mở khung xem trang"
              title="Mở khung xem trang"
              className="flex h-12 w-full cursor-pointer items-center justify-center gap-2 rounded-2xl border border-border bg-card text-xs font-medium text-muted-foreground transition-colors hover:border-brand/40 hover:text-foreground xl:sticky xl:top-[4.5rem] xl:h-40 xl:w-12 xl:flex-col"
            >
              <PanelRightOpen className="size-4" />
              <span className="xl:[writing-mode:vertical-rl]">Xem trang</span>
            </button>
          ) : (
            <div className="h-[32rem] xl:sticky xl:top-[4.5rem] xl:h-[calc(100vh-6rem)]">
              <PagePreview
                documentId={documentId}
                page={page}
                total={data.pdf_pages}
                caption={caption}
                highlightLine={selected && selected.page === page && selected.anchored ? selected.anchor_line : null}
                onPage={setPreviewPage}
                onCollapse={() => setPreviewCollapsed(true)}
              />
            </div>
          ))}
      </div>

      <RunDialog
        key={`${step}-${runOpen}`}
        stage={stage}
        open={runOpen}
        onOpenChange={setRunOpen}
        pending={run.isPending}
        onRun={(options) => {
          setRunOpen(false);
          run.mutate({ stage: step, options });
        }}
      />
      <StageLogDialog documentId={documentId} stage={logStage} running={data.running_stage === logStage} onClose={() => setLogStage(null)} />
      <SettingsDialog documentId={documentId} open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
