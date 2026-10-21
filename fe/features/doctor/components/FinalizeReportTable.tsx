"use client";

import { ClipboardList } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { FinalizeReportItem } from "../types";
import { ReferenceBadge } from "./FinalizeReportCard";
import { UrgencyBadge } from "./FinalizeReportBadges";

function age(dob: string): string {
  const d = new Date(dob);
  return Number.isNaN(d.getTime()) ? "?" : String(Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 3600 * 1000)));
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

const TH = "px-4 py-2.5 text-left font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground";

export function FinalizeReportTable({
  reports,
  total,
  loading,
  selectedId,
  onSelect,
}: {
  reports: FinalizeReportItem[];
  total: number;
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card/40">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <table className="w-full table-fixed border-collapse text-sm">
          <colgroup>
            <col className="w-20" />
            <col className="w-48" />
            <col />
            <col className="w-28" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-card/95 backdrop-blur">
            <tr className="border-b border-border">
              <th className={TH}>Ngày</th>
              <th className={TH}>Bệnh nhân</th>
              <th className={TH}>Nhận định của bác sĩ</th>
              <th className={TH}>Khẩn cấp</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              [0, 1, 2, 3, 4].map((i) => (
                <tr key={i} className="border-b border-border/60">
                  <td colSpan={4} className="px-4 py-3.5">
                    <Skeleton className="h-4 w-full rounded" />
                  </td>
                </tr>
              ))
            ) : reports.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-16 text-center text-muted-foreground">
                  <ClipboardList className="mx-auto mb-2 size-7 opacity-30" />
                  <p className="text-xs">Không có phiếu nào</p>
                </td>
              </tr>
            ) : (
              reports.map((r) => {
                const active = r.id === selectedId;
                const urgency = r.snapshot?.assessment.urgency;
                return (
                  <tr
                    key={r.id}
                    onClick={() => onSelect(r.id)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(r.id)}
                    tabIndex={0}
                    aria-selected={active}
                    className={cn(
                      "cursor-pointer border-b border-border/60 transition-colors focus-visible:bg-muted/60 focus-visible:outline-none",
                      active ? "bg-brand/10" : "hover:bg-muted/50"
                    )}
                  >
                    <td className="px-4 py-3.5 font-mono text-xs text-muted-foreground">{shortDate(r.createdAt)}</td>
                    <td className="px-4 py-3.5">
                      <p className={cn("truncate font-medium", active ? "text-brand" : "text-foreground")}>
                        {r.patient.fullName}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        {age(r.patient.dob)} · {r.patient.gender === "female" ? "Nữ" : "Nam"}
                      </p>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-foreground">{r.diagnosis}</span>
                        {r.isReferenceCase && <ReferenceBadge />}
                      </div>
                    </td>
                    <td className="px-4 py-3.5">{urgency ? <UrgencyBadge urgency={urgency} /> : <span className="text-xs text-muted-foreground">—</span>}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-border px-4 py-2.5 text-[11px] text-muted-foreground">
        <span>
          Hiển thị {reports.length} / {total} phiếu
        </span>
      </div>
    </div>
  );
}
