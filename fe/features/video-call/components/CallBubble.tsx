"use client";

import { Phone, PhoneMissed, Stethoscope } from "lucide-react";
import { cn } from "@/lib/utils";

function formatTime(iso?: string): string {
  return iso ? new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) : "";
}

/** Tin trạng thái cuộc gọi (bắt đầu / kết thúc / nhỡ). Nút thao tác nằm ở CallOverlay. */
export function CallBubble({
  content,
  createdAt,
  variant = "line",
}: {
  content: string;
  createdAt?: string;
  /** `bubble`: bong bóng bên trái như tin của bác sĩ (màn bệnh nhân); `line`: dòng hệ thống kẻ ngang (màn bác sĩ) */
  variant?: "line" | "bubble";
}) {
  const failed = /nhỡ|từ chối|huỷ/i.test(content);
  const Icon = failed ? PhoneMissed : Phone;
  const time = formatTime(createdAt);

  if (variant === "bubble") {
    return (
      <div className="flex w-full items-end justify-start gap-2 py-1">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-sky-500 text-white shadow-xs" title="Bác sĩ">
          <Stethoscope className="size-3.5" />
        </span>
        <div
          className={cn(
            "flex items-center gap-3 rounded-2xl rounded-bl-xs border px-3.5 py-2.5 shadow-sm",
            failed
              ? "border-destructive/30 bg-destructive/5"
              : "border-sky-500/30 bg-sky-50/60 shadow-sky-500/5 dark:bg-sky-950/20"
          )}
        >
          <span
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-full",
              failed ? "bg-destructive/10 text-destructive" : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
            )}
          >
            <Icon className="size-4" />
          </span>
          <div className="min-w-0">
            <p className={cn("text-sm font-medium", failed ? "text-destructive" : "text-foreground")}>{content}</p>
            {time && <p className="font-mono text-[10px] text-muted-foreground">{time}</p>}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div role="separator" className="flex w-full items-center gap-3 py-2">
      <span className="h-px flex-1 bg-border" />
      <span
        className={cn(
          "flex shrink-0 items-center gap-1.5 text-xs font-medium",
          failed ? "text-destructive" : "text-emerald-700 dark:text-emerald-400"
        )}
      >
        <Icon className="size-3.5" />
        {content}
        {time && <span className="font-normal text-muted-foreground">· {time}</span>}
      </span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}
