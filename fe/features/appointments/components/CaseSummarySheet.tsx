"use client";

import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { UrgencyBadge, type FinalizeReportItem } from "@/features/doctor";
import type { FollowupChannel } from "@/features/followup";
import { formatRelativeTime } from "@/lib/utils";
import { formatDateTime } from "../constants";
import type { DoctorAppointment } from "../types";
import { StatusBadge } from "./StatusBadge";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_1fr] items-start gap-3 py-2 text-sm">
      <dt className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-foreground">{children}</dd>
    </div>
  );
}

// xem nhanh một ca trong khung trượt bên phải, từ dữ liệu của bảng (không gọi thêm API); xem đầy đủ ở màn chi tiết
export function CaseSummarySheet({
  a,
  report,
  channel,
  onClose,
  onOpenDetail,
}: {
  a: DoctorAppointment;
  report: FinalizeReportItem | undefined;
  channel: FollowupChannel | undefined;
  onClose: () => void;
  onOpenDetail: () => void;
}) {
  const urgency = report?.snapshot?.assessment.urgency;
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="border-b border-border">
          <SheetTitle className="font-serif text-xl font-bold">{a.patient.fullName}</SheetTitle>
          <SheetDescription>
            {a.bodySiteLabel} · {formatDateTime(a.scheduledAt)}
          </SheetDescription>
        </SheetHeader>
        <dl className="flex-1 divide-y divide-border overflow-y-auto px-4">
          <Row label="Trạng thái">
            <StatusBadge status={a.status} />
            {a.cancelReason && <span className="ml-2 text-xs text-muted-foreground">{a.cancelReason}</span>}
          </Row>
          <Row label="Lý do khám">{a.reason || <span className="text-muted-foreground">Chưa ghi</span>}</Row>
          {a.patient.allergies && (
            <Row label="Dị ứng">
              <span className="flex items-center gap-1 font-medium text-amber-600 dark:text-amber-400">
                <TriangleAlert className="size-3.5 shrink-0" /> {a.patient.allergies}
              </span>
            </Row>
          )}
          <Row label="Kết luận">
            {report ? (
              <span className="flex flex-wrap items-center gap-2">
                {report.diagnosis}
                {urgency && <UrgencyBadge urgency={urgency} />}
              </span>
            ) : a.topHypothesis ? (
              <span className="text-muted-foreground">Chưa có. AI gợi ý: {a.topHypothesis} (không phải chẩn đoán y khoa)</span>
            ) : (
              <span className="text-muted-foreground">Chưa có</span>
            )}
          </Row>
          <Row label="Trao đổi">
            {channel ? (
              <span className="text-muted-foreground">
                {channel.status === "open" ? "Đang mở" : "Chỉ đọc"}
                {channel.lastMessageAt ? ` · tin gần nhất ${formatRelativeTime(channel.lastMessageAt)}` : " · chưa có tin"}
              </span>
            ) : (
              <span className="text-muted-foreground">Chưa có kênh (mở khi bắt đầu khám)</span>
            )}
          </Row>
        </dl>
        <SheetFooter className="border-t border-border">
          <Button variant="brand" onClick={onOpenDetail} className="w-full">
            Xem chi tiết
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
