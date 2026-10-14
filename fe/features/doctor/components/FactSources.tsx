"use client";

import { Quote } from "lucide-react";
import { ImageThumbnail } from "@/features/chat/components/ImageThumbnail";
import { cn } from "@/lib/utils";
import type { SnapshotMessage } from "../types";

const SENDER_LABEL: Record<SnapshotMessage["sender"], string> = {
  patient: "Bệnh nhân",
  ai: "AI",
  doctor: "Bác sĩ",
};

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} ${d.toLocaleDateString("vi-VN")}`;
}

/** Trích tin gốc làm bằng chứng cho một dữ kiện (đã chép vào snapshot lúc chốt) */
export function FactSources({ sources, compact = false }: { sources: SnapshotMessage[]; compact?: boolean }) {
  if (!sources.length) return null;
  return (
    <ul className="space-y-1.5">
      {sources.map((m) => (
        <li key={m.id} className="rounded-lg border-l-2 border-brand/40 bg-muted/40 px-2.5 py-1.5">
          <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <Quote className="size-3" />
            <span className="font-medium">{SENDER_LABEL[m.sender]}</span>
            <span>· {formatTime(m.createdAt)}</span>
          </p>
          <p className={cn("mt-0.5 whitespace-pre-line text-xs text-foreground/90", compact && "line-clamp-2")}>
            {m.content}
          </p>
          {m.files.some((f) => f.url && f.contentType?.startsWith("image/")) && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {m.files
                .filter((f) => f.url && f.contentType?.startsWith("image/"))
                .map((f) => (
                  <ImageThumbnail key={f.url} url={f.url!} name={f.fileName} size={compact ? 40 : 56} />
                ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
