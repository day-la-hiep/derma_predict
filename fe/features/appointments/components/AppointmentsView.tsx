"use client";

import { useState } from "react";
import { ArrowLeft, CalendarDays, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Hint } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { useActiveProfile } from "@/features/patient-profile/hooks";
import { cn, formatRelativeTime } from "@/lib/utils";
import { formatDateTime } from "../constants";
import { useBookAppointment, useCancelMyAppointment, useMyAppointments, usePatientEpisodes } from "../hooks";
import type { PatientEpisode } from "../types";
import { ReasonDialog } from "./ReasonDialog";
import { StatusBadge } from "./StatusBadge";

type Tab = "episodes" | "appointments";

function BookDialog({ episode, profileId, onClose }: { episode: PatientEpisode; profileId: string; onClose: () => void }) {
  const [when, setWhen] = useState("");
  const [reason, setReason] = useState("");
  const book = useBookAppointment();
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif">Đặt lịch · {episode.bodySiteLabel}</DialogTitle>
          <DialogDescription>Bác sĩ sẽ xem thông tin bạn đã mô tả trong chat trước khi khám.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} aria-label="Thời gian hẹn" />
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Lý do (tuỳ chọn)" maxLength={500} />
        </div>
        <DialogFooter>
          <Button
            variant="brand"
            disabled={!when || book.isPending}
            onClick={() =>
              book.mutate({ profileId, episodeId: episode.id, scheduledAt: new Date(when).toISOString(), reason }, { onSuccess: onClose })
            }
          >
            {book.isPending && <Loader2 className="size-4 animate-spin" />}
            Gửi yêu cầu
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-xs text-muted-foreground">{children}</p>;
}

// Màn riêng trong khu vực nội dung chính, cùng khung với `ProfileView` (sidebar chat vẫn giữ nguyên bên trái)
export function AppointmentsView({ onBack }: { onBack: () => void }) {
  const { activeProfile } = useActiveProfile();
  const profileId = activeProfile?.id ?? null;
  const { data: episodes = [], isLoading } = usePatientEpisodes(profileId);
  const { data: appointments = [] } = useMyAppointments();
  const cancel = useCancelMyAppointment();
  const [tab, setTab] = useState<Tab>("episodes");
  const [booking, setBooking] = useState<PatientEpisode | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);

  const mine = appointments.filter((a) => a.patientProfileId === profileId);

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col bg-background">
      <header className="flex shrink-0 items-center gap-3 border-b border-border/80 bg-background/80 px-4 py-3 backdrop-blur-md">
        <Button variant="ghost" size="iconSm" onClick={onBack} aria-label="Quay lại chat" className="rounded-lg text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" />
        </Button>
        <h1 className="font-serif text-sm font-semibold tracking-tight text-foreground">Lịch khám</h1>
        {activeProfile && <span className="truncate text-xs text-muted-foreground">· {activeProfile.full_name}</span>}
      </header>

      <div className="mx-auto flex w-full min-h-0 max-w-4xl flex-1 flex-col gap-5 overflow-y-auto p-6">
        <div className="flex gap-1 self-start rounded-lg bg-muted p-1">
          {(["episodes", "appointments"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                tab === t ? "bg-background text-foreground shadow-xs" : "text-muted-foreground"
              )}
            >
              {t === "episodes" ? "Đang theo dõi" : "Lịch hẹn"}
              <span className="ml-1.5 font-mono text-[10px] text-muted-foreground/80">{t === "episodes" ? episodes.length : mine.length}</span>
            </button>
          ))}
        </div>

        {tab === "episodes" ? (
          <ul className="flex flex-col gap-2">
            {isLoading && <p className="text-xs text-muted-foreground">Đang tải…</p>}
            {!isLoading && episodes.length === 0 && <Empty>Chưa có vấn đề nào. Hãy mô tả triệu chứng trong chat để AI thu thập thông tin trước khi đặt lịch.</Empty>}
            {episodes.map((e) => (
              <li key={e.id} className="space-y-2 rounded-xl border border-border bg-card p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-foreground">{e.bodySiteLabel}</p>
                    <p className="text-[11px] text-muted-foreground">Cập nhật {formatRelativeTime(e.updatedAt)}</p>
                  </div>
                  {e.appointment ? (
                    <StatusBadge status={e.appointment.status} />
                  ) : (
                    <Hint content={e.notBookableReason ?? "Gửi yêu cầu hẹn bác sĩ cho vấn đề này."}>
                      <span>
                        <Button size="sm" variant="brand" disabled={!e.bookable} onClick={() => setBooking(e)} className="rounded-xl">
                          <CalendarDays className="size-4" /> Đặt lịch
                        </Button>
                      </span>
                    </Hint>
                  )}
                </div>
                {e.facts.length > 0 && <p className="text-xs leading-relaxed text-muted-foreground">{e.facts.join(" · ")}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <ul className="flex flex-col gap-2">
            {mine.length === 0 && <Empty>Chưa có lịch hẹn.</Empty>}
            {mine.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-foreground">
                    {a.bodySiteLabel} <span className="font-normal text-muted-foreground">· {formatDateTime(a.scheduledAt)}</span>
                  </p>
                  <p className="truncate text-[11px] text-muted-foreground">
                    {a.doctorName ? `BS. ${a.doctorName}` : "Chờ bác sĩ nhận"}
                    {a.cancelReason ? ` · Lý do huỷ: ${a.cancelReason}` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <StatusBadge status={a.status} />
                  {(a.status === "requested" || a.status === "confirmed") && (
                    <Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={() => setCancelling(a.id)} className="text-muted-foreground">
                      Huỷ
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {cancelling && <ReasonDialog title="Huỷ lịch" onClose={() => setCancelling(null)} onSubmit={(reason) => cancel.mutate({ id: cancelling, reason })} />}
      {booking && profileId && <BookDialog episode={booking} profileId={profileId} onClose={() => setBooking(null)} />}
    </div>
  );
}
