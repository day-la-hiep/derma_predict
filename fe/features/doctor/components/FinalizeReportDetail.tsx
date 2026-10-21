"use client";

import { useState } from "react";
import Link from "next/link";
import { ClipboardList, ExternalLink, History, Printer, TriangleAlert, Network } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { ImageThumbnail } from "@/features/chat/components/ImageThumbnail";
import { cn } from "@/lib/utils";
import { FACT_TYPE_CONFIG } from "../constants";
import { useConversationMessages, useProfileFinalizeReports } from "../hooks";
import type { FinalizeReportItem, PatientProfile } from "../types";
import { ChatBubble } from "./ChatViewer";
import { FactSources } from "./FactSources";
import { FinalizeReportCard, ReferenceBadge, formatDate } from "./FinalizeReportCard";
import { PatientProfileDetails, patientSubtitle } from "./PatientProfileDetails";
import { OriginBadge, UrgencyBadge } from "./FinalizeReportBadges";
import { PatientJourneyDialog } from "./PatientJourneyDialog";

type Tab = "summary" | "facts" | "conversation";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mb-2 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-brand">{children}</h4>
  );
}

function SummaryTab({ report }: { report: FinalizeReportItem }) {
  const snap = report.snapshot;
  const { data: history, isLoading } = useProfileFinalizeReports(report.patient.id);
  const others = (history ?? []).filter((r) => r.id !== report.id);

  return (
    <div className="space-y-6">
      <section>
        <SectionTitle>Nhận định của bác sĩ</SectionTitle>
        <div className="space-y-2 rounded-xl border border-border bg-card/60 p-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-base font-semibold text-foreground">{report.diagnosis}</p>
            {snap && <UrgencyBadge urgency={snap.assessment.urgency} />}
          </div>
          {snap?.assessment.reasoning && (
            <p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">{snap.assessment.reasoning}</p>
          )}
        </div>
      </section>

      {report.notes && (
        <section>
          <SectionTitle>Ghi chú</SectionTitle>
          <p className="whitespace-pre-line rounded-xl border border-border p-4 text-sm leading-relaxed text-foreground">
            {report.notes}
          </p>
        </section>
      )}

      {report.images && report.images.length > 0 && (
        <section>
          <SectionTitle>Ảnh bệnh đã lưu</SectionTitle>
          <div className="flex flex-wrap gap-2 rounded-xl border border-border p-4">
            {report.images.map((img) => (
              <div key={img.id} className="space-y-1">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={img.file.url ?? ""} alt={img.file.fileName} className="size-24 rounded-lg object-cover" />
                {img.confirmedLabel && (
                  <p className="text-[10px] text-muted-foreground">{img.confirmedLabel}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {!!snap?.assessment.instructions.length && (
        <section>
          <SectionTitle>Dặn dò bệnh nhân</SectionTitle>
          <ul className="space-y-1.5 rounded-xl border border-border p-4 text-sm text-foreground">
            {snap.assessment.instructions.map((ins, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-muted-foreground">•</span>
                {ins}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="print:hidden">
        <SectionTitle>
          <Hint side="right" content="Toàn bộ báo cáo kết luận khác của bệnh nhân này, kể cả do bác sĩ khác ghi.">
            <span className="inline-flex w-fit items-center gap-1.5">
              <History className="size-3" /> Các lần khám khác <span>{others.length}</span>
            </span>
          </Hint>
        </SectionTitle>
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Đang tải…</p>
        ) : others.length === 0 ? (
          <p className="text-xs text-muted-foreground">Chưa có lần khám nào khác</p>
        ) : (
          <ul className="space-y-2">
            {others.map((r) => (
              <FinalizeReportCard key={r.id} report={r} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function FactsTab({ report }: { report: FinalizeReportItem }) {
  const facts = report.snapshot?.clinicalFacts ?? [];
  if (!report.snapshot) {
    return <p className="text-sm text-muted-foreground">Phiếu ghi trước khi có bản chốt dữ kiện.</p>;
  }
  if (!facts.length) return <p className="text-sm text-muted-foreground">Phiếu không có dữ kiện.</p>;
  return (
    <ul className="space-y-3">
      {facts.map((f, i) => (
        <li key={i} className="space-y-2 rounded-xl border border-border p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">{f.label}</p>
              <p className="text-[11px] text-muted-foreground">{FACT_TYPE_CONFIG[f.factType]?.label ?? f.factType}</p>
            </div>
            <OriginBadge origin={f.origin} />
          </div>
          {f.detail && <p className="text-sm text-foreground/90">{f.detail}</p>}
          {f.sources.length > 0 ? (
            <FactSources sources={f.sources} />
          ) : (
            <p className="text-[11px] text-muted-foreground/80">Không có tin nhắn gốc</p>
          )}
        </li>
      ))}
    </ul>
  );
}

function ConversationTab({ conversationId }: { conversationId: string }) {
  const { data: messages, isLoading } = useConversationMessages(conversationId);
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-14 w-3/4 rounded-xl" />
        ))}
      </div>
    );
  }
  const images = (messages ?? []).flatMap((m) =>
    (m.attachments ?? []).filter((a) => a.url && a.contentType?.startsWith("image/"))
  );
  return (
    <div className="space-y-5">
      {images.length > 0 && (
        <section>
          <SectionTitle>Ảnh trong hội thoại · {images.length}</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {images.map((a) => (
              <ImageThumbnail key={a.id} url={a.url!} name={a.name} size={72} />
            ))}
          </div>
        </section>
      )}
      <section className="space-y-3">
        <SectionTitle>Hội thoại</SectionTitle>
        {(messages ?? []).map((m) => (
          <ChatBubble key={m.id} message={m} />
        ))}
      </section>
    </div>
  );
}

export function FinalizeReportDetail({ report }: { report: FinalizeReportItem | null }) {
  const [tab, setTab] = useState<Tab>("summary");

  if (!report) {
    return (
      <div className="flex h-full items-center justify-center rounded-2xl border border-border text-muted-foreground">
        <div className="text-center">
          <ClipboardList className="mx-auto mb-3 size-10 opacity-30" />
          <p className="text-sm">Chọn một phiếu</p>
        </div>
      </div>
    );
  }

  // hiển thị theo bản chụp lúc chốt; phiếu cũ không có snapshot thì dùng hồ sơ hiện tại
  const patient: Omit<PatientProfile, "id"> = report.snapshot?.patientProfile ?? report.patient;
  const hasSource = !!report.consultationSessionId;
  const activeTab: Tab = tab === "conversation" && !report.conversationId ? "summary" : tab;
  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: "summary", label: "Tóm tắt", show: true },
    { id: "facts", label: "Dữ kiện", show: true },
    { id: "conversation", label: "Hội thoại và ảnh", show: !!report.conversationId },
  ];
  const finalizedAt = new Date(report.createdAt);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card/40 print:h-auto print:overflow-visible print:border-0">
      <header className="space-y-3 border-b border-border px-6 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate font-serif text-2xl font-bold tracking-tight text-foreground">{patient.fullName}</h2>
            <p className="text-xs text-muted-foreground">{patientSubtitle({ id: "", ...patient })}</p>
          </div>
          <div className="flex shrink-0 gap-2 print:hidden">
            <Hint side="bottom" content="In phiếu hoặc lưu thành PDF bằng hộp thoại in của trình duyệt.">
              <Button variant="outline" size="sm" onClick={() => window.print()} className="gap-1.5">
                <Printer className="size-3.5" /> Xuất PDF
              </Button>
            </Hint>
            {report.patient?.id && (
              <PatientJourneyDialog
                patientId={report.patient.id}
                patientName={patient.fullName}
                trigger={
                  <Button variant="outline" size="sm" className="gap-1.5 border-brand/30 text-brand hover:bg-brand/10">
                    <Network className="size-3.5" /> Hành trình bệnh
                  </Button>
                }
              />
            )}
            {hasSource && (
              <Hint side="bottom" content="Mở ca tư vấn gốc ở màn Ca tư vấn.">
                <Button variant="outline" size="sm" asChild className="gap-1.5">
                  <Link href={`/doctor?session=${encodeURIComponent(report.consultationSessionId!)}`}>
                    <ExternalLink className="size-3.5" /> Mở ca gốc
                  </Link>
                </Button>
              </Hint>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {patient.allergies && (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/50 dark:text-amber-400">
              <TriangleAlert className="size-3" /> Dị ứng: {patient.allergies}
            </span>
          )}
          {report.isReferenceCase && <ReferenceBadge className="text-[10px]" />}
        </div>
        <p className="text-xs text-muted-foreground">
          Chốt {formatDate(report.createdAt)}{" "}
          {finalizedAt.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} · {report.doctorName ?? "Bác sĩ"}
          {!hasSource && " · Khám trực tiếp"}
        </p>
        <nav className="-mb-px flex gap-1 print:hidden" role="tablist" aria-label="Nội dung phiếu">
          {tabs
            .filter((t) => t.show)
            .map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={activeTab === t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "border-b-2 px-3 py-2 text-xs font-medium transition-colors",
                  activeTab === t.id
                    ? "border-brand text-brand"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                {t.label}
              </button>
            ))}
        </nav>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 print:overflow-visible">
        {/* khi in: luôn có Tóm tắt + Dữ kiện, không phụ thuộc tab đang mở */}
        <div className={cn(activeTab !== "summary" && "hidden print:block")}>
          <SummaryTab report={report} />
        </div>
        <div className={cn(activeTab !== "facts" && "hidden print:mt-6 print:block")}>
          <FactsTab report={report} />
        </div>
        {activeTab === "conversation" && report.conversationId && (
          <div className="print:hidden">
            <ConversationTab conversationId={report.conversationId} />
          </div>
        )}
      </div>
    </div>
  );
}
