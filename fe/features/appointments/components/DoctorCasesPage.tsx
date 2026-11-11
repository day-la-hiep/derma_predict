"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, ClipboardCheck, Eye, Inbox, Loader2, MoreHorizontal, Play, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Hint } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { UrgencyBadge, useMyFinalizeReports, type FinalizeReportItem } from "@/features/doctor";
import { doctorPaths } from "@/features/doctor/routes";
import { useDoctorFollowups, type FollowupChannel } from "@/features/followup";
import { cn, formatRelativeTime } from "@/lib/utils";
import { formatDateTime } from "../constants";
import { useAppointmentAction, useDoctorAppointments } from "../hooks";
import type { AppointmentStatus, DoctorAppointment } from "../types";
import { CaseSummarySheet } from "./CaseSummarySheet";
import { EncounterFinalizeDialog } from "./EncounterFinalizeDialog";
import { ReasonDialog } from "./ReasonDialog";
import { StatusBadge } from "./StatusBadge";

type Filter = "all" | AppointmentStatus;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "requested", label: "Chờ xác nhận" },
  { value: "confirmed", label: "Đã hẹn" },
  { value: "in_progress", label: "Đang khám" },
  { value: "done", label: "Đã khám" },
];

const TH = "px-4 py-2.5 text-left font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground";

function age(dob: string): string {
  const d = new Date(dob);
  return Number.isNaN(d.getTime()) ? "?" : String(Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 3600 * 1000)));
}

// thao tác nhanh của dòng: chỉ icon nhỏ có tooltip; bắt đầu khám xong thì mở luôn trang chi tiết
function RowActions({ a, onFinalize, onPreview, onOpenDetail }: { a: DoctorAppointment; onFinalize: () => void; onPreview: () => void; onOpenDetail: () => void }) {
  const act = useAppointmentAction(a.id);
  const [cancelling, setCancelling] = useState(false);
  const pre = a.status === "requested" || a.status === "confirmed";
  const icon = "h-8 w-8 rounded-lg p-0";
  const busy = act.isPending ? <Loader2 className="size-4 animate-spin" /> : null;
  return (
    <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
      {a.status === "requested" && (
        <Hint content="Xác nhận lịch">
          <Button size="sm" variant="ghost" disabled={act.isPending} onClick={() => act.mutate({ kind: "confirm" })} aria-label="Xác nhận lịch" className={cn(icon, "text-brand hover:bg-brand/10 hover:text-brand")}>
            {busy ?? <CheckCircle2 className="size-4" />}
          </Button>
        </Hint>
      )}
      {a.status === "confirmed" && (
        <Hint content="Bắt đầu khám">
          <Button
            size="sm"
            variant="ghost"
            disabled={act.isPending}
            onClick={() => act.mutate({ kind: "start" }, { onSuccess: onOpenDetail })}
            aria-label="Bắt đầu khám"
            className={cn(icon, "text-brand hover:bg-brand/10 hover:text-brand")}
          >
            {busy ?? <Play className="size-4" />}
          </Button>
        </Hint>
      )}
      {a.status === "in_progress" && a.encounterId && (
        <Hint content="Chốt kết luận">
          <Button size="sm" variant="ghost" onClick={onFinalize} aria-label="Chốt kết luận" className={cn(icon, "text-brand hover:bg-brand/10 hover:text-brand")}>
            <ClipboardCheck className="size-4" />
          </Button>
        </Hint>
      )}
      <Hint content="Xem nhanh">
        <Button size="sm" variant="ghost" onClick={onPreview} aria-label="Xem nhanh ca khám" className={cn(icon, "text-muted-foreground hover:text-foreground")}>
          <Eye className="size-4" />
        </Button>
      </Hint>
      {pre && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="ghost" aria-label="Thao tác khác" className={cn(icon, "text-muted-foreground")}>
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            {a.status === "confirmed" && (
              <DropdownMenuItem disabled={act.isPending} onClick={() => act.mutate({ kind: "no-show" })} className="text-xs">
                Bệnh nhân không đến
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => setCancelling(true)} className="text-xs text-destructive focus:text-destructive">
              Huỷ lịch
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      {cancelling && <ReasonDialog title="Huỷ lịch" onClose={() => setCancelling(false)} onSubmit={(reason) => act.mutate({ kind: "cancel", reason })} />}
    </div>
  );
}

function Conclusion({ a, report }: { a: DoctorAppointment; report: FinalizeReportItem | undefined }) {
  if (report) {
    const urgency = report.snapshot?.assessment.urgency;
    return (
      <div className="flex items-center gap-2">
        <span className="truncate text-foreground">{report.diagnosis}</span>
        {urgency && <UrgencyBadge urgency={urgency} />}
      </div>
    );
  }
  // chưa có kết luận thì chỉ có gợi ý AI, ghi rõ để không nhầm với chẩn đoán
  return a.topHypothesis ? <span className="truncate text-muted-foreground">AI gợi ý: {a.topHypothesis}</span> : <span className="text-xs text-muted-foreground">—</span>;
}

function Channel({ channel }: { channel: FollowupChannel | undefined }) {
  if (!channel) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <span className="text-[11px] text-muted-foreground">
      <span className={cn("mr-1.5 inline-block size-1.5 rounded-full", channel.status === "open" ? "bg-emerald-500" : "bg-muted-foreground/40")} />
      {channel.status === "open" ? "Đang mở" : "Chỉ đọc"}
      {channel.lastMessageAt ? ` · ${formatRelativeTime(channel.lastMessageAt)}` : ""}
    </span>
  );
}

export function DoctorCasesPage() {
  const { data: list = [], isLoading } = useDoctorAppointments();
  const { data: reports = [] } = useMyFinalizeReports("");
  const { data: channels = [] } = useDoctorFollowups();
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const router = useRouter();
  const [summaryId, setSummaryId] = useState<string | null>(null);
  const [finalizeEncounterId, setFinalizeEncounterId] = useState<string | null>(null);
  const openDetail = (id: string) => router.push(doctorPaths.caseDetail(id));

  // ghép ba nguồn theo lần khám: lịch hẹn, báo cáo kết luận, kênh theo dõi
  const reportByEncounter = useMemo(() => new Map(reports.filter((r) => r.encounterId).map((r) => [r.encounterId!, r])), [reports]);
  const channelByEncounter = useMemo(() => new Map(channels.map((c) => [c.encounterId, c])), [channels]);

  const summary = list.find((a) => a.id === summaryId);
  const q = query.trim().toLowerCase();
  const shown = list.filter((a) => (filter === "all" || a.status === filter) && (!q || a.patient.fullName.toLowerCase().includes(q)));
  const count = (v: Filter) => (v === "all" ? list.length : list.filter((a) => a.status === v).length);

  return (
    <div className="space-y-4">
      <h1 className="font-serif text-2xl font-bold tracking-tight text-foreground">Ca khám</h1>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1 rounded-xl bg-muted p-0.5" role="tablist" aria-label="Lọc ca khám">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="tab"
              aria-selected={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "rounded-[10px] px-3 py-1.5 text-xs font-medium transition-all",
                filter === f.value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {f.label} <span className="text-muted-foreground/70">{count(f.value)}</span>
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full max-w-64">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Tìm bệnh nhân" aria-label="Tìm theo tên bệnh nhân" className="h-8 rounded-full pl-8 text-xs" />
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-border bg-card/40">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[56rem] border-collapse text-sm">
            <thead className="bg-card/95">
              <tr className="border-b border-border">
                <th className={TH}>Bệnh nhân</th>
                <th className={TH}>Vùng da</th>
                <th className={TH}>Giờ hẹn</th>
                <th className={TH}>Trạng thái</th>
                <th className={TH}>Kết luận</th>
                <th className={TH}>Trao đổi</th>
                <th className={cn(TH, "text-right")}>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                [0, 1, 2, 3, 4].map((i) => (
                  <tr key={i} className="border-b border-border/60">
                    <td colSpan={7} className="px-4 py-3.5">
                      <Skeleton className="h-4 w-full rounded" />
                    </td>
                  </tr>
                ))
              ) : shown.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-muted-foreground">
                    <Inbox className="mx-auto mb-2 size-7 opacity-30" />
                    <p className="text-xs">Chưa có ca khám nào</p>
                  </td>
                </tr>
              ) : (
                shown.map((a) => {
                  const report = a.encounterId ? reportByEncounter.get(a.encounterId) : undefined;
                  return (
                    <tr
                      key={a.id}
                      onClick={() => openDetail(a.id)}
                      onKeyDown={(e) => e.target === e.currentTarget && (e.key === "Enter" || e.key === " ") && openDetail(a.id)}
                      tabIndex={0}
                      className="cursor-pointer border-b border-border/60 transition-colors hover:bg-muted/50 focus-visible:bg-muted/60 focus-visible:outline-none"
                    >
                      <td className="px-4 py-3.5">
                        <p className="truncate font-medium text-foreground">{a.patient.fullName}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {age(a.patient.dob)} tuổi · {a.patient.gender === "female" ? "Nữ" : "Nam"}
                        </p>
                      </td>
                      <td className="px-4 py-3.5">
                        <p className="text-foreground">{a.bodySiteLabel}</p>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3.5 font-mono text-xs text-muted-foreground">{formatDateTime(a.scheduledAt)}</td>
                      <td className="px-4 py-3.5">
                        <StatusBadge status={a.status} />
                      </td>
                      <td className="max-w-56 px-4 py-3.5">
                        <Conclusion a={a} report={report} />
                      </td>
                      <td className="px-4 py-3.5">
                        <Channel channel={a.encounterId ? channelByEncounter.get(a.encounterId) : undefined} />
                      </td>
                      <td className="px-4 py-3.5">
                        <RowActions a={a} onFinalize={() => setFinalizeEncounterId(a.encounterId)} onPreview={() => setSummaryId(a.id)} onOpenDetail={() => openDetail(a.id)} />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-border px-4 py-2.5 text-[11px] text-muted-foreground">
          Hiển thị {shown.length} / {list.length} ca
        </div>
      </div>

      {summary && (
        <CaseSummarySheet
          a={summary}
          report={summary.encounterId ? reportByEncounter.get(summary.encounterId) : undefined}
          channel={summary.encounterId ? channelByEncounter.get(summary.encounterId) : undefined}
          onClose={() => setSummaryId(null)}
          onOpenDetail={() => openDetail(summary.id)}
        />
      )}
      {finalizeEncounterId && <EncounterFinalizeDialog encounterId={finalizeEncounterId} onClose={() => setFinalizeEncounterId(null)} />}
    </div>
  );
}
