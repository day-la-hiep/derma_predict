"use client";

import { useState } from "react";
import { Inbox, MessageSquareText } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime, cn } from "@/lib/utils";
import { useDoctorFollowups } from "../hooks";
import { FollowupChat } from "./FollowupChat";

export function FollowupPage() {
  const { data: list = [], isLoading } = useDoctorFollowups();
  const [selected, setSelected] = useState<string | null>(null);
  // chưa chọn thì mở kênh đầu tiên, giống màn Lịch khám
  const channel = list.find((c) => c.conversationId === selected) ?? list[0];

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-sidebar/70 backdrop-blur-md 2xl:w-80">
        <div className="flex items-baseline justify-between border-b border-border px-4 py-3">
          <h2 className="font-serif text-lg font-bold tracking-tight text-foreground">Theo dõi sau khám</h2>
          <span className="font-mono text-xs text-muted-foreground">{list.length}</span>
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {isLoading ? (
            <div className="space-y-2 p-1">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-10 w-full rounded-xl" />
              ))}
            </div>
          ) : list.length === 0 ? (
            <div className="flex flex-col items-center py-14 text-center text-muted-foreground">
              <Inbox className="mb-2 size-7 opacity-30" />
              <p className="text-xs">Chưa có kênh theo dõi</p>
            </div>
          ) : (
            list.map((c) => {
              const active = c.conversationId === channel?.conversationId;
              return (
                <button
                  key={c.conversationId}
                  type="button"
                  onClick={() => setSelected(c.conversationId)}
                  aria-current={active ? "true" : undefined}
                  className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors", active ? "bg-brand/10" : "hover:bg-muted/60")}
                >
                  <span className={cn("size-2 shrink-0 rounded-full", c.status === "open" ? "bg-emerald-500" : "bg-muted-foreground/40")} />
                  <span className="min-w-0 flex-1">
                    <span className={cn("block truncate text-sm", active ? "font-semibold text-brand" : "font-medium text-foreground")}>{c.patientName ?? "Bệnh nhân"}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {c.status === "open" ? "Đang mở" : "Chỉ đọc"}
                      {c.lastMessageAt ? ` · ${formatRelativeTime(c.lastMessageAt)}` : ""}
                    </span>
                  </span>
                </button>
              );
            })
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col bg-background">
        {channel ? (
          <FollowupChat key={channel.conversationId} channel={channel} role="doctor" />
        ) : (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <div className="text-center">
              <MessageSquareText className="mx-auto mb-3 size-10 opacity-30" />
              <p className="text-sm">Chọn một kênh</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
