import { cn } from "@/lib/utils";
import type { FinalizeReport } from "../types";

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN");
}

export function ReferenceBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full border border-brand/30 bg-brand/10 px-1.5 py-0.5 text-[9px] font-medium text-brand",
        className
      )}
    >
      Tham khảo
    </span>
  );
}

export function FinalizeReportCard({ report }: { report: FinalizeReport }) {
  return (
    <li className="rounded-xl border border-border/60 px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-foreground">{report.diagnosis}</span>
        {report.isReferenceCase && <ReferenceBadge />}
      </div>
      {report.notes && <p className="mt-1 whitespace-pre-line text-xs text-muted-foreground">{report.notes}</p>}
      <p className="mt-1.5 text-[11px] text-muted-foreground/70">
        {report.doctorName ?? "Bác sĩ"} · {formatDate(report.createdAt)}
      </p>
    </li>
  );
}
