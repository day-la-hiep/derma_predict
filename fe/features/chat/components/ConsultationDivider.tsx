import { cn } from "@/lib/utils";

const CONSULTATION_TYPES = [
  "consultation_requested",
  "consultation_accepted",
  "consultation_resolved",
] as const;

export function isConsultationMarker(messageType?: string): boolean {
  return CONSULTATION_TYPES.some((t) => t === messageType);
}

/** Đường chia trong luồng chat: bác sĩ vào / ra khỏi cuộc trò chuyện. */
export function ConsultationDivider({
  messageType,
  content,
}: {
  messageType?: string;
  content: string;
}) {
  const resolved = messageType === "consultation_resolved";
  const line = cn(
    "h-px flex-1",
    resolved ? "bg-border" : "bg-sky-500/30"
  );
  return (
    <div role="separator" className="flex w-full items-center gap-3 py-2">
      <span className={line} />
      <span
        className={cn(
          "shrink-0 text-center text-xs font-medium",
          resolved ? "text-muted-foreground" : "text-sky-700 dark:text-sky-300"
        )}
      >
        {content}
      </span>
      <span className={line} />
    </div>
  );
}
