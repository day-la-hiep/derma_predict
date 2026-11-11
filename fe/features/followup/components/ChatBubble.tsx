"use client";

import { Bot, FileText, Stethoscope, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DoctorViewMessage } from "@/features/doctor";
import { ImageThumbnail } from "@/features/chat/components/ImageThumbnail";
import { MarkdownMessage } from "@/features/chat/components/MarkdownMessage";
import { CallBubble } from "@/features/video-call";

const SENDER_CONFIG = {
  patient: {
    label: "Bệnh nhân",
    icon: User,
    bubbleClass:
      "bg-muted/80 dark:bg-muted/50 text-foreground border border-border/50",
    iconClass:
      "bg-blue-100 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400",
    align: "justify-start" as const,
  },
  ai: {
    label: "AI",
    icon: Bot,
    bubbleClass: "bg-brand/5 dark:bg-brand/10 text-foreground border border-brand/15",
    iconClass:
      "bg-brand/10 dark:bg-brand/20 text-brand",
    align: "justify-start" as const,
  },
  doctor: {
    label: "Bác sĩ",
    icon: Stethoscope,
    bubbleClass:
      "bg-emerald-50 dark:bg-emerald-950/30 text-foreground border border-emerald-200 dark:border-emerald-800/50",
    iconClass:
      "bg-emerald-100 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400",
    align: "justify-start" as const,
  },
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ChatBubble({ message }: { message: DoctorViewMessage }) {
  const cfg = SENDER_CONFIG[message.sender];
  const Icon = cfg.icon;

  if (message.messageType === "video_call") {
    return <CallBubble content={message.content} createdAt={message.createdAt} />;
  }

  return (
    <div className={cn("flex w-full gap-2.5 py-1", cfg.align)}>
      {/* Avatar */}
      <div
        className={cn(
          "flex items-center justify-center size-7 rounded-lg shrink-0 mt-0.5",
          cfg.iconClass
        )}
      >
        <Icon className="size-3.5" />
      </div>

      {/* Bubble */}
      <div className="max-w-[85%] min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {cfg.label}
          </span>
          <span className="text-[10px] text-muted-foreground/60 font-mono">
            {formatTime(message.createdAt)}
          </span>
        </div>
        <div
          className={cn("rounded-xl rounded-tl-sm px-3.5 py-2.5", cfg.bubbleClass)}
        >
          {/* File / ảnh đính kèm */}
          {message.attachments && message.attachments.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {message.attachments.map((file) => {
                const isImage = file.contentType?.startsWith("image/") && file.url;
                return isImage ? (
                  <div key={file.id} className="rounded-lg overflow-hidden border border-border/50">
                    <ImageThumbnail
                      url={file.url!}
                      name={file.name}
                      size={72}
                    />
                  </div>
                ) : (
                  <div
                    key={file.id}
                    className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-background/60 px-2.5 py-1.5 text-xs text-foreground"
                  >
                    <FileText className="size-3.5 shrink-0" />
                    <span className="truncate max-w-[120px]">{file.name}</span>
                  </div>
                );
              })}
            </div>
          )}
          <div className="text-[13px] leading-relaxed">
            <MarkdownMessage content={message.content} />
          </div>
        </div>
      </div>
    </div>
  );
}
