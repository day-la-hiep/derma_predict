"use client";

import { useEffect, useRef } from "react";
import { Lock } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Hint } from "@/components/ui/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { doctorApi } from "@/features/doctor";
import type { DoctorViewMessage } from "@/features/doctor";
import { CallButtons } from "@/features/video-call";
import { endpoints } from "@/services/endpoints";
import { subscribeSse } from "@/services/sse";
import { cn, formatDate } from "@/lib/utils";
import type { UploadedImage } from "../api";
import { qk, useFollowupMessages, useSendFollowupMessage } from "../hooks";
import type { FollowupChannel } from "../types";
import { ChatBubble } from "./ChatBubble";
import { Composer } from "./Composer";

export function FollowupChat({ channel, role }: { channel: FollowupChannel; role: "patient" | "doctor" }) {
  const id = channel.conversationId;
  const qc = useQueryClient();
  const { data: messages = [], isLoading } = useFollowupMessages(id);
  const send = useSendFollowupMessage(id);
  const bottomRef = useRef<HTMLDivElement>(null);
  const readOnly = channel.status === "read_only";

  // Pub/Sub không replay: nối lại thì tải lại lịch sử để khỏi lỡ tin
  useEffect(
    () =>
      subscribeSse(endpoints.streamMessage(id), {
        onData: (raw) => {
          if (raw.type !== "message.created") return;
          const msg = doctorApi.adaptRoomMessage(raw.message, id);
          qc.setQueryData<DoctorViewMessage[]>(qk.messages(id), (old = []) => (old.some((m) => m.id === msg.id) ? old : [...old, msg]));
        },
        onOpen: (reconnected) => {
          if (reconnected) void qc.invalidateQueries({ queryKey: qk.messages(id) });
        },
      }),
    [id, qc]
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const submit = (content: string, files: UploadedImage[]) =>
    new Promise<boolean>((resolve) => send.mutate({ content, files }, { onSuccess: () => resolve(true), onError: () => resolve(false) }));

  const title = role === "doctor" ? (channel.patientName ?? "Bệnh nhân") : channel.doctorName ? `BS. ${channel.doctorName}` : "Bác sĩ";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div className="min-w-0">
          <h3 className="truncate font-serif text-lg font-bold tracking-tight text-foreground">{title}</h3>
          <p className={cn("flex items-center gap-1 text-xs", readOnly ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")}>
            {readOnly ? (
              <>
                <Lock className="size-3" /> Chỉ đọc{channel.followupUntil ? ` · hết hạn ${formatDate(channel.followupUntil)}` : ""}
              </>
            ) : channel.followupUntil ? (
              `Mở đến ${formatDate(channel.followupUntil)}`
            ) : (
              "Đang mở"
            )}
          </p>
        </div>
        {role === "doctor" && (
          <div className="flex shrink-0 items-center gap-2">
            <CallButtons conversationId={id} disabled={readOnly} />
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {isLoading ? (
          <div className="space-y-3 p-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className={cn("h-12 rounded-xl", i % 2 === 0 ? "w-3/4" : "w-full")} />
            ))}
          </div>
        ) : messages.length === 0 ? (
          <p className="py-10 text-center text-xs text-muted-foreground">Chưa có tin nhắn. Kênh này chỉ có bệnh nhân và bác sĩ, không có AI trả lời.</p>
        ) : (
          messages.map((m) => <ChatBubble key={m.id} message={m} />)
        )}
        <div ref={bottomRef} />
      </div>

      {readOnly ? (
        <div className="shrink-0 border-t border-border p-3 pb-4">
          <Hint content="Kênh theo dõi đã hết hạn, chỉ xem lại được. Tái khám sẽ mở kênh mới.">
            <p className="rounded-xl bg-muted/40 p-3 text-center text-xs text-muted-foreground">Chỉ xem</p>
          </Hint>
        </div>
      ) : (
        <Composer role={role} sending={send.isPending} onSend={submit} />
      )}
    </div>
  );
}
