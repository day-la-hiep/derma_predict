"use client";

import { useState } from "react";
import { Brain, CalendarDays, CheckCircle2, Inbox, Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { FollowupButton } from "@/features/followup";
import { PatientInfoCard } from "@/features/doctor/components/PatientInfoCard";
import { AiSummaryView } from "@/features/doctor/components/AiSummaryView";
import { cn } from "@/lib/utils";
import { APPOINTMENT_STATUS, formatDateTime } from "../constants";
import { useAppointmentAction, useDoctorAppointment, useDoctorAppointments } from "../hooks";
import type { AppointmentStatus, DoctorAppointment, DoctorAppointmentDetail } from "../types";
import { EncounterFinalizeDialog } from "./EncounterFinalizeDialog";
import { ReasonDialog } from "./ReasonDialog";

const DOT: Record<AppointmentStatus, string> = {
  requested: "bg-amber-500 animate-pulse",
  confirmed: "bg-brand",
  in_progress: "bg-violet-500",
  done: "bg-emerald-500",
  cancelled: "bg-muted-foreground/40",
  no_show: "bg-red-500",
};

const FILTERS: { value: "all" | AppointmentStatus; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "requested", label: "Chờ" },
  { value: "confirmed", label: "Hẹn" },
  { value: "in_progress", label: "Khám" },
  { value: "done", label: "Xong" },
];

function SectionLabel({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <h4 className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
      {children} {count !== undefined && <span className="text-brand">{count}</span>}
    </h4>
  );
}

function Row({ a, active, onSelect }: { a: DoctorAppointment; active: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(a.id)}
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
        active ? "bg-brand/10" : "hover:bg-muted/60"
      )}
    >
      <Hint content={APPOINTMENT_STATUS[a.status].hint}>
        <span className={cn("size-2 shrink-0 rounded-full", DOT[a.status])} />
      </Hint>
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate text-sm", active ? "font-semibold text-brand" : "font-medium text-foreground")}>
          {a.patient.fullName}
        </span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {a.bodySiteLabel} · {formatDateTime(a.scheduledAt)}
        </span>
      </span>
    </button>
  );
}

function List({ items, loading, activeId, onSelect }: { items: DoctorAppointment[]; loading: boolean; activeId: string | null; onSelect: (id: string) => void }) {
  const [filter, setFilter] = useState<"all" | AppointmentStatus>("all");
  const shown = items.filter((a) => filter === "all" || a.status === filter);
  const count = (v: string) => (v === "all" ? items.length : items.filter((a) => a.status === v).length);

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-border px-4 py-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-serif text-lg font-bold tracking-tight text-foreground">Lịch khám</h2>
          <span className="font-mono text-xs text-muted-foreground">{shown.length}</span>
        </div>
        <div className="grid grid-cols-5 gap-0.5 rounded-xl bg-muted p-0.5" role="tablist" aria-label="Lọc lịch khám">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="tab"
              aria-selected={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "rounded-[10px] px-1 py-1 text-[11px] font-medium transition-all",
                filter === f.value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {f.label} <span className="text-muted-foreground/70">{count(f.value)}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {loading ? (
          <div className="space-y-1 p-1">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 px-2 py-2">
                <Skeleton className="size-2 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3.5 w-3/4 rounded" />
                  <Skeleton className="h-2.5 w-1/2 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : shown.length === 0 ? (
          <div className="flex flex-col items-center py-14 text-center text-muted-foreground">
            <Inbox className="mb-2 size-7 opacity-30" />
            <p className="text-xs">Chưa có lịch</p>
          </div>
        ) : (
          shown.map((a) => <Row key={a.id} a={a} active={a.id === activeId} onSelect={onSelect} />)
        )}
      </div>
    </div>
  );
}

function AiBody({ d }: { d: DoctorAppointmentDetail }) {
  const ep = d.episode;
  return (
    <div className="space-y-4 px-4 pb-4">
      <section className="space-y-2">
        <Hint side="left" content={ep.disclaimer}>
          <h4 className="w-fit font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
            Gợi ý AI <span className="text-brand">· gợi ý</span>
            {ep.hypothesesLocked && <span className="ml-1 normal-case tracking-normal">(đã khoá)</span>}
          </h4>
        </Hint>
        {ep.hypotheses.length === 0 && (
          <div className="py-6 text-center text-muted-foreground">
            <Brain className="mx-auto mb-2 size-7 opacity-30" />
            <p className="text-xs">Chưa có gợi ý</p>
          </div>
        )}
        {ep.hypotheses.map((h) => (
          <div key={h.rank} className="rounded-xl border border-brand/20 bg-brand/[0.03] p-3 text-xs">
            <p className="font-semibold text-foreground">
              {h.rank}. {h.disease}
            </p>
            <p className="text-[11px] text-muted-foreground">
              {h.diagnosisLabel} · độ tin cậy {h.confidence}
            </p>
            {h.missing.length > 0 && <p className="mt-1 text-[11px] text-muted-foreground">Còn thiếu: {h.missing.join("; ")}</p>}
          </div>
        ))}
      </section>
      {ep.imagePredictions.length > 0 && (
        <section className="space-y-2">
          <SectionLabel count={ep.imagePredictions.length}>Ảnh</SectionLabel>
          {ep.imagePredictions.map((p) => (
            <div key={p.fileId} className="flex items-center gap-3 rounded-xl border border-border bg-card p-2 text-xs">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {p.url && <img src={p.url} alt={p.fileName} className="size-14 rounded-lg object-cover" />}
              <span className="text-muted-foreground">{p.topK.slice(0, 3).map((t) => `${t.labelName} ${Math.round(t.score * 100)}%`).join(" · ")}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function Actions({ d }: { d: DoctorAppointmentDetail }) {
  const act = useAppointmentAction(d.id);
  const [cancelling, setCancelling] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const pre = d.status === "requested" || d.status === "confirmed";
  const swappable = d.otherEpisodes.filter((e) => e.bookable);
  const main = "h-10 w-full rounded-xl text-sm font-medium transition-all active:scale-[0.98]";

  return (
    <div className="space-y-2 border-t border-border p-3">
      {pre && swappable.length > 0 && (
        <Hint side="top" content="Bệnh nhân có vấn đề ở vùng khác: đổi lịch sang đợt đó trước khi bắt đầu khám.">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Đổi sang:</span>
            {swappable.map((e) => (
              <Button key={e.id} size="xs" variant="outline" disabled={act.isPending} onClick={() => act.mutate({ kind: "change", episodeId: e.id })}>
                {e.bodySiteLabel}
              </Button>
            ))}
          </div>
        </Hint>
      )}
      {d.status === "requested" && (
        <Button variant="brand" disabled={act.isPending} onClick={() => act.mutate({ kind: "confirm" })} className={main}>
          {act.isPending ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />} Xác nhận
        </Button>
      )}
      {d.status === "confirmed" && (
        <Button variant="brand" disabled={act.isPending} onClick={() => act.mutate({ kind: "start" })} className={main}>
          {act.isPending ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />} Bắt đầu khám
        </Button>
      )}
      {d.status === "in_progress" && d.encounterId && (
        <Button variant="brand" onClick={() => setFinalizing(true)} className={main}>
          <CheckCircle2 className="size-4" /> Chốt kết luận
        </Button>
      )}
      {d.encounterId && <FollowupButton encounterId={d.encounterId} role="doctor" className="h-10 w-full rounded-xl" />}
      {pre && (
        <div className="flex gap-2">
          {d.status === "confirmed" && (
            <Button variant="outline" size="sm" disabled={act.isPending} onClick={() => act.mutate({ kind: "no-show" })} className="flex-1 rounded-xl">
              Không đến
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => setCancelling(true)} className="flex-1 rounded-xl text-muted-foreground">
            Huỷ lịch
          </Button>
        </div>
      )}
      {!pre && d.status !== "in_progress" && (
        <p className="flex items-center justify-center gap-1.5 rounded-xl bg-muted/50 py-2.5 text-xs font-medium text-muted-foreground">
          {APPOINTMENT_STATUS[d.status].label}
          {d.cancelReason ? ` · ${d.cancelReason}` : ""}
        </p>
      )}
      {cancelling && <ReasonDialog title="Huỷ lịch" onClose={() => setCancelling(false)} onSubmit={(reason) => act.mutate({ kind: "cancel", reason })} />}
      {finalizing && d.encounterId && <EncounterFinalizeDialog encounterId={d.encounterId} onClose={() => setFinalizing(false)} />}
    </div>
  );
}

function Empty() {
  return (
    <div className="flex flex-1 items-center justify-center p-6 text-muted-foreground">
      <div className="text-center">
        <CalendarDays className="mx-auto mb-3 size-10 opacity-30" />
        <p className="text-sm">Chọn một lịch hẹn</p>
      </div>
    </div>
  );
}

function Center({ d }: { d: DoctorAppointmentDetail }) {
  const ep = d.episode;
  const facts = [...ep.facts, ...d.longTermFacts];
  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <h3 className="min-w-0 truncate font-serif text-lg font-bold tracking-tight text-foreground">{ep.bodySiteLabel}</h3>
          <span className="shrink-0 text-xs text-muted-foreground">· {formatDateTime(d.scheduledAt)}</span>
        </div>
        <PatientInfoCard patient={d.patient} reason={d.reason} />
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto pt-4">
        <section className="space-y-2 px-4">
          <SectionLabel count={facts.length}>Dữ kiện</SectionLabel>
          {facts.length === 0 && <p className="text-xs text-muted-foreground">Chưa có dữ kiện.</p>}
          <ul className="space-y-1.5">
            {facts.map((f) => (
              <li key={f.id} className="flex items-start gap-2 rounded-xl border border-border bg-card px-3 py-2 text-xs">
                <span className="mt-0.5 shrink-0 rounded-full bg-brand/10 px-1.5 py-0.5 font-mono text-[10px] text-brand">{f.factType}</span>
                <span className="min-w-0 flex-1 text-foreground">
                  {f.templateLabel}
                  {f.detail && <span className="text-muted-foreground">: {f.detail}</span>}
                </span>
                {f.verifiedAt && <span className="shrink-0 text-[10px] font-medium text-emerald-600">đã xác nhận</span>}
              </li>
            ))}
          </ul>
        </section>
        {ep.summary && <AiSummaryView summary={ep.summary} />}
        <div className="xl:hidden">
          <AiBody d={d} />
        </div>
      </div>
      <div className="xl:hidden">
        <Actions d={d} />
      </div>
    </div>
  );
}

export function DoctorSchedulePage() {
  const { data: list = [], isLoading } = useDoctorAppointments();
  const [selected, setSelected] = useState<string | null>(null);
  // chưa chọn thì mở lịch đầu tiên, giống màn Theo dõi
  const activeId = selected ?? list[0]?.id ?? null;
  const { data: d } = useDoctorAppointment(activeId);

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-sidebar/70 backdrop-blur-md 2xl:w-80">
        <List items={list} loading={isLoading} activeId={activeId} onSelect={setSelected} />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col border-r border-border bg-background xl:border-r">
        {d ? <Center key={d.id + d.status} d={d} /> : <Empty />}
      </div>

      <aside className="hidden w-80 shrink-0 flex-col bg-sidebar/50 backdrop-blur-md xl:flex 2xl:w-96">
        {d ? (
          <div className="flex h-full flex-col">
            <div className="border-b border-border px-4 py-3">
              <h3 className="font-serif text-lg font-bold tracking-tight text-foreground">Báo cáo</h3>
            </div>
            <div className="flex-1 overflow-y-auto pt-4">
              <AiBody d={d} />
            </div>
            <Actions key={d.id + d.status} d={d} />
          </div>
        ) : (
          <Empty />
        )}
      </aside>
    </div>
  );
}
