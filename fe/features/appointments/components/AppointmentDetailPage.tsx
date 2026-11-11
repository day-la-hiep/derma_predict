"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, CalendarDays, CheckCircle2, Inbox, Loader2, Play, MapPin, MessageSquareText, PanelRightClose, PanelRightOpen, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { FACT_TYPE_CONFIG, PatientJourneyView, UrgencyBadge, useMyFinalizeReports, type ClinicalFact, type ClinicalFactType, type FinalizeReportItem } from "@/features/doctor";
import { FactSources } from "@/features/doctor/components/FactSources";
import { doctorPaths } from "@/features/doctor/routes";
import { CitationButton } from "@/features/citation";
import { FollowupChat, useFollowupChannel } from "@/features/followup";
import { cn } from "@/lib/utils";
import { formatDateTime } from "../constants";
import { useAppointmentAction, useDoctorAppointment } from "../hooks";
import type { DoctorAppointmentDetail } from "../types";
import { useResizablePanel } from "../useResizablePanel";
import { EncounterFinalizeDialog } from "./EncounterFinalizeDialog";
import { ReasonDialog } from "./ReasonDialog";
import { StatusBadge } from "./StatusBadge";

const CHAT_DEFAULT_WIDTH = 416;

function age(dob: string): string {
  const d = new Date(dob);
  return Number.isNaN(d.getTime()) ? "?" : `${Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 3600 * 1000))} tuổi`;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-border pt-6">
      <div>
        <h2 className="font-serif text-xl font-bold tracking-tight text-foreground">{title}</h2>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

// nhãn nhỏ bên trái, nội dung mô tả bên phải: đọc như văn bản, không bọc card
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[7rem_1fr] sm:gap-4">
      <dt className="pt-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm leading-relaxed text-foreground">{children}</dd>
    </div>
  );
}

// cập nhật trạng thái theo vòng đời: Chờ → Đã hẹn → Đang khám → Đã khám (hoặc huỷ / không đến trước khi khám)
function StatusActions({ d, onFinalize }: { d: DoctorAppointmentDetail; onFinalize: () => void }) {
  const act = useAppointmentAction(d.id);
  const [cancelling, setCancelling] = useState(false);
  const btn = "h-9 gap-1.5 rounded-xl px-4";
  const spin = act.isPending ? <Loader2 className="size-4 animate-spin" /> : null;
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {d.status === "requested" && (
        <Button variant="brand" size="sm" disabled={act.isPending} onClick={() => act.mutate({ kind: "confirm" })} className={btn}>
          {spin ?? <CheckCircle2 className="size-4" />} Xác nhận lịch
        </Button>
      )}
      {d.status === "confirmed" && (
        <Button variant="brand" size="sm" disabled={act.isPending} onClick={() => act.mutate({ kind: "start" })} className={btn}>
          {spin ?? <Play className="size-4" />} Bắt đầu khám
        </Button>
      )}
      {d.status === "in_progress" && d.encounterId && (
        <Button variant="brand" size="sm" onClick={onFinalize} className={btn}>
          <CheckCircle2 className="size-4" /> Kết luận
        </Button>
      )}
      {d.status === "confirmed" && (
        <Button variant="outline" size="sm" disabled={act.isPending} onClick={() => act.mutate({ kind: "no-show" })} className={btn}>
          Bệnh nhân không đến
        </Button>
      )}
      {(d.status === "requested" || d.status === "confirmed") && (
        <Button variant="ghost" size="sm" onClick={() => setCancelling(true)} className={cn(btn, "text-muted-foreground")}>
          Huỷ lịch
        </Button>
      )}
      {cancelling && <ReasonDialog title="Huỷ lịch" onClose={() => setCancelling(false)} onSubmit={(reason) => act.mutate({ kind: "cancel", reason })} />}
    </div>
  );
}

function CaseHeader({ d, onFinalize }: { d: DoctorAppointmentDetail; onFinalize: () => void }) {
  const p = d.patient;
  return (
    <header className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-serif text-2xl font-bold tracking-tight text-foreground">{p.fullName}</h2>
            <StatusBadge status={d.status} />
          </div>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>
              {p.gender === "female" ? "Nữ" : "Nam"} · {age(p.dob)}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <MapPin className="size-3.5" /> {d.episode.bodySiteLabel}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays className="size-3.5" /> {formatDateTime(d.scheduledAt)}
            </span>
          </p>
        </div>
        <StatusActions d={d} onFinalize={onFinalize} />
      </div>
      <dl className="space-y-2 pt-1">
        {d.reason && <Field label="Lý do khám">{d.reason}</Field>}
        {p.allergies && (
          <Field label="Dị ứng">
            <span className="inline-flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
              <TriangleAlert className="size-3.5 shrink-0" /> {p.allergies}
            </span>
          </Field>
        )}
        {p.medicalHistory && <Field label="Tiền sử">{p.medicalHistory}</Field>}
      </dl>
      <SwapEpisode d={d} />
    </header>
  );
}

// đổi lịch sang đợt khác của cùng hồ sơ: chỉ trước khi bắt đầu khám
function SwapEpisode({ d }: { d: DoctorAppointmentDetail }) {
  const act = useAppointmentAction(d.id);
  const options = d.otherEpisodes.filter((e) => e.bookable);
  if (!(d.status === "requested" || d.status === "confirmed") || options.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">Bệnh nhân có vấn đề ở vùng khác, đổi lịch sang:</span>
      {options.map((e) => (
        <Button key={e.id} size="sm" variant="outline" disabled={act.isPending} onClick={() => act.mutate({ kind: "change", episodeId: e.id })} className="h-8 rounded-lg">
          {e.bodySiteLabel}
        </Button>
      ))}
    </div>
  );
}

function Conclusion({ d, report }: { d: DoctorAppointmentDetail; report: FinalizeReportItem | undefined }) {
  if (!report) {
    return <p className="text-sm text-muted-foreground">{d.status === "in_progress" ? "Đang khám, chưa chốt kết luận." : "Chưa có kết luận của bác sĩ."}</p>;
  }
  const a = report.snapshot?.assessment;
  return (
    <div className="space-y-4 border-l-2 border-brand/40 pl-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-lg font-semibold text-foreground">{report.diagnosis}</p>
        {a?.urgency && <UrgencyBadge urgency={a.urgency} />}
      </div>
      <p className="-mt-2 text-xs text-muted-foreground">
        Chốt {formatDateTime(report.createdAt)}
        {report.doctorName ? ` · ${report.doctorName}` : ""}
        {report.isReferenceCase ? " · ca tham khảo" : ""}
      </p>
      <dl className="space-y-3">
        {a?.reasoning && <Field label="Nhận định"><span className="whitespace-pre-line">{a.reasoning}</span></Field>}
        {a && a.instructions.length > 0 && (
          <Field label="Dặn dò">
            <ul className="list-disc space-y-0.5 pl-5">
              {a.instructions.map((i, idx) => (
                <li key={idx}>{i}</li>
              ))}
            </ul>
          </Field>
        )}
        {report.notes && <Field label="Ghi chú"><span className="whitespace-pre-line text-muted-foreground">{report.notes}</span></Field>}
        {report.images.length > 0 && (
          <Field label="Ảnh">
            <div className="flex flex-wrap gap-3">
              {report.images.map((img) => (
                <figure key={img.id} className="w-24 space-y-1">
                  {img.file.url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={img.file.url} alt={img.file.fileName} className="size-24 rounded-lg object-cover" />
                  )}
                  {img.confirmedLabel && <figcaption className="truncate text-[11px] text-muted-foreground">{img.confirmedLabel}</figcaption>}
                </figure>
              ))}
            </div>
          </Field>
        )}
      </dl>
    </div>
  );
}

function FactRows({ facts }: { facts: ClinicalFact[] }) {
  if (facts.length === 0) return <p className="text-sm text-muted-foreground">Chưa có dữ kiện nào cho ca này.</p>;
  const groups = new Map<ClinicalFactType, ClinicalFact[]>();
  for (const f of facts) groups.set(f.factType, [...(groups.get(f.factType) ?? []), f]);
  return (
    <div className="space-y-5">
      {[...groups].map(([type, items]) => {
        const cfg = FACT_TYPE_CONFIG[type];
        return (
          <div key={type} className="space-y-1">
            <h3 className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-brand">
              {cfg?.label ?? type} <span className="text-muted-foreground">{items.length}</span>
            </h3>
            <ul className="divide-y divide-border">
              {items.map((f) => {
                const sources = f.sourceMessages ?? [];
                return (
                  <li key={f.id} className="py-2.5">
                    <div className="flex items-baseline justify-between gap-3">
                      <p className="text-sm text-foreground">
                        <span className="font-medium">{f.templateLabel}</span>
                        {f.detail && <span className="text-muted-foreground">: {f.detail}</span>}
                      </p>
                      <span className={cn("shrink-0 text-[11px]", f.verifiedAt ? "font-medium text-emerald-600" : "text-muted-foreground")}>
                        {f.verifiedAt ? "Đã xác nhận" : "Chưa xác nhận"}
                      </span>
                    </div>
                    {sources.length > 0 && (
                      <details className="mt-1 text-xs">
                        <summary className="w-fit cursor-pointer text-muted-foreground transition-colors hover:text-foreground">Tin nhắn gốc ({sources.length})</summary>
                        <div className="mt-2">
                          <FactSources sources={sources} compact />
                        </div>
                      </details>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

// bằng chứng từ tool tra cứu là JSON thô (có khi bị cắt giữa chừng nên không parse được): lấy mục sách + trang bằng regex
function evidenceLabel(text: string): string {
  if (!text.trim().startsWith("{")) return text;
  const pick = (key: string) => new RegExp(`"${key}"\\s*:\\s*"([^"]*)"`).exec(text)?.[1];
  const label = [pick("section") ?? pick("title"), pick("pages")].filter(Boolean).join(" · ");
  return label || `${text.slice(0, 120)}…`;
}

function AiSuggestions({ d }: { d: DoctorAppointmentDetail }) {
  const ep = d.episode;
  return (
    <Section title="Gợi ý của AI" hint={ep.disclaimer || "Chỉ là gợi ý hỗ trợ, không phải chẩn đoán y khoa."}>
      {ep.hypotheses.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa có gợi ý.</p>
      ) : (
        <ol className="divide-y divide-border">
          {ep.hypotheses.map((h) => (
            <li key={h.rank} className="space-y-1 py-3 first:pt-0">
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-sm font-medium text-foreground">
                  {h.rank}. {h.disease}
                  <span className="ml-2 font-normal text-muted-foreground">{h.diagnosisLabel}</span>
                </p>
                <span className="shrink-0 text-xs text-muted-foreground">độ tin cậy {h.confidence}</span>
              </div>
              {h.evidence.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                  {h.evidence.map((e, i) => (
                    <li key={i}>
                      <CitationButton label={evidenceLabel(e.text)} citation={e.ref} />
                    </li>
                  ))}
                </ul>
              )}
              {h.missing.length > 0 && <p className="text-xs text-muted-foreground">Còn thiếu: {h.missing.join("; ")}</p>}
            </li>
          ))}
        </ol>
      )}
      {ep.imagePredictions.length > 0 && (
        <div className="grid gap-3 pt-2 sm:grid-cols-2">
          {ep.imagePredictions.map((p) => (
            <div key={p.fileId} className="flex items-center gap-3 text-xs">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {p.url && <img src={p.url} alt={p.fileName} className="size-16 rounded-lg object-cover" />}
              <span className="text-muted-foreground">{p.topK.slice(0, 3).map((t) => `${t.labelName} ${Math.round(t.score * 100)}%`).join(" · ")}</span>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

export function AppointmentDetailPage({ appointmentId }: { appointmentId: string }) {
  const { data: d, isLoading, isError } = useDoctorAppointment(appointmentId);
  const { data: channel, isLoading: channelLoading } = useFollowupChannel(d?.encounterId ?? null);
  const { data: reports = [] } = useMyFinalizeReports("");
  const [finalizing, setFinalizing] = useState(false);
  const panel = useResizablePanel(CHAT_DEFAULT_WIDTH);
  const report = d?.encounterId ? reports.find((r) => r.encounterId === d.encounterId) : undefined;

  // lg trở lên: khung cao bằng màn hình (bù padding của main), hai bên cuộn riêng; nhỏ hơn thì xếp dọc
  return (
    // relative z-40: nổi trên dải nền đặc sát đáy của khung (z-30) để không che mất ô nhập
    <div className={cn("-mx-4 -my-6 sm:-mx-6 lg:relative lg:z-40 lg:-mx-8 lg:flex lg:h-dvh lg:overflow-hidden", panel.dragging && "select-none")}>
      <div className="flex min-w-0 flex-1 flex-col lg:min-h-0">
        <div className="z-10 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/95 px-4 backdrop-blur sm:px-6 lg:px-8">
          <Hint content="Về danh sách ca khám">
            <Link href={doctorPaths.home} aria-label="Về danh sách ca khám" className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
              <ArrowLeft className="size-4" />
            </Link>
          </Hint>
          <h1 className="font-serif text-lg font-bold tracking-tight text-foreground">Chi tiết ca khám</h1>
        </div>
        <div className="flex-1 space-y-6 px-4 py-6 sm:px-6 lg:overflow-y-auto lg:px-8">
          {isLoading ? (
            <div className="space-y-4">
              <Skeleton className="h-10 w-72 rounded" />
              <Skeleton className="h-40 w-full rounded-2xl" />
            </div>
          ) : isError || !d ? (
            <div className="flex flex-col items-center py-20 text-center text-muted-foreground">
              <Inbox className="mb-2 size-8 opacity-30" />
              <p className="text-sm">Không tìm thấy ca khám.</p>
            </div>
          ) : (
            <div className="space-y-6">
              <CaseHeader d={d} onFinalize={() => setFinalizing(true)} />
              <Section title="Kết luận của bác sĩ">
                <Conclusion d={d} report={report} />
              </Section>
              <Section title="Dữ kiện">
                <FactRows facts={[...d.episode.facts, ...d.longTermFacts]} />
              </Section>
              <AiSuggestions d={d} />
              <Section title="Lịch sử khám">
                <div className="h-[36rem] overflow-hidden rounded-xl border border-border">
                  <PatientJourneyView patientId={d.patient.id} />
                </div>
              </Section>
            </div>
          )}
        </div>
      </div>

      {d && (
        <>
          {!panel.collapsed && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Kéo để đổi độ rộng khung trao đổi (phím mũi tên, nhấp đúp để đặt lại)"
              tabIndex={0}
              onPointerDown={panel.startDrag}
              onDoubleClick={panel.reset}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft") panel.nudge(24);
                if (e.key === "ArrowRight") panel.nudge(-24);
              }}
              className={cn(
                "group relative hidden w-1.5 shrink-0 cursor-col-resize touch-none bg-border transition-colors hover:bg-brand/60 focus-visible:bg-brand focus-visible:outline-none lg:block",
                panel.dragging && "bg-brand"
              )}
            >
              <span className="absolute inset-y-0 -inset-x-1.5" />
            </div>
          )}
          <aside
            style={{ "--chat-w": panel.collapsed ? "3rem" : `${panel.width}px` } as React.CSSProperties}
            className={cn(
              "flex min-w-0 flex-col bg-background lg:h-full lg:w-[var(--chat-w)] lg:shrink-0",
              panel.collapsed ? "lg:border-l lg:border-border" : "min-h-[32rem] w-full border-t border-border lg:border-t-0",
              !panel.dragging && "lg:transition-[width] lg:duration-200"
            )}
          >
            {panel.collapsed && (
              <div className="hidden h-full flex-col items-center gap-4 py-4 lg:flex">
                <Hint side="left" content="Mở khung trao đổi">
                  <Button variant="ghost" size="iconSm" onClick={panel.toggle} aria-label="Mở khung trao đổi" className="rounded-lg text-muted-foreground hover:text-foreground">
                    <PanelRightOpen className="size-4" />
                  </Button>
                </Hint>
                <MessageSquareText className="size-4 text-muted-foreground" />
                <span className="text-xs font-medium text-muted-foreground [writing-mode:vertical-rl]">Trao đổi với bệnh nhân</span>
              </div>
            )}
            <div className={cn("flex min-h-0 flex-1 flex-col", panel.collapsed && "lg:hidden")}>
              <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-5">
                <h2 className="font-serif text-lg font-bold tracking-tight text-foreground">Trao đổi với bệnh nhân</h2>
                <Hint content="Thu gọn khung trao đổi">
                  <Button variant="ghost" size="iconSm" onClick={panel.toggle} aria-label="Thu gọn khung trao đổi" className="hidden rounded-lg text-muted-foreground hover:text-foreground lg:inline-flex">
                    <PanelRightClose className="size-4" />
                  </Button>
                </Hint>
              </div>
              <div className="flex min-h-0 flex-1 flex-col">
                {channel ? (
                  <FollowupChat key={channel.conversationId} channel={channel} role="doctor" />
                ) : (
                  <p className="px-5 py-6 text-xs text-muted-foreground">
                    {!d.encounterId ? "Kênh trao đổi mở khi bắt đầu khám." : channelLoading ? "Đang tải…" : "Lần khám này chưa có kênh theo dõi."}
                  </p>
                )}
              </div>
            </div>
          </aside>
        </>
      )}
      {finalizing && d?.encounterId && <EncounterFinalizeDialog encounterId={d.encounterId} onClose={() => setFinalizing(false)} />}
    </div>
  );
}
