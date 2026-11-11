"use client";

import { useEffect, useRef, useState } from "react";
import { CornerDownLeft, Lock, PlusCircle } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { doctorApi } from "@/features/doctor";
import type { DoctorViewMessage } from "@/features/doctor";
import { CallButtons } from "@/features/video-call";
import { endpoints } from "@/services/endpoints";
import { subscribeSse } from "@/services/sse";
import { cn } from "@/lib/utils";
import { qk, useExtendFollowup, useFollowupMessages, useSendFollowupMessage } from "../hooks";
import type { FollowupChannel } from "../types";
import { ChatBubble } from "./ChatBubble";

const EXTEND_DAYS = 30;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN");
}

export function FollowupChat({ channel, role }: { channel: FollowupChannel; role: "patient" | "doctor" }) {
  const id = channel.conversationId;
  const qc = useQueryClient();
  const { data: messages = [], isLoading } = useFollowupMessages(id);
  const send = useSendFollowupMessage(id);
  const extend = useExtendFollowup(id);
  const [text, setText] = useState("");
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

  const submit = () => {
    const content = text.trim();
    if (!content || readOnly || send.isPending) return;
    setText("");
    send.mutate(content, { onError: () => setText(content) });
  };

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
            <Hint content={`Gia hạn kênh theo dõi thêm ${EXTEND_DAYS} ngày. Kênh đã hết hạn thì không gia hạn được.`}>
              <span>
                <Button variant="outline" size="sm" disabled={readOnly || extend.isPending} onClick={() => extend.mutate(EXTEND_DAYS)} className="gap-1.5">
                  <PlusCircle className="size-3.5" /> Gia hạn
                </Button>
              </span>
            </Hint>
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

      <div className="border-t border-border p-3">
        {readOnly ? (
          <Hint content="Kênh theo dõi đã hết hạn, chỉ xem lại được. Tái khám sẽ mở kênh mới.">
            <p className="rounded-xl bg-muted/40 p-3 text-center text-xs text-muted-foreground">Chỉ xem</p>
          </Hint>
        ) : (
          <div className="flex items-end gap-2 rounded-2xl border border-border bg-card p-2 transition-colors focus-within:border-brand/40 focus-within:ring-2 focus-within:ring-brand/10">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder={role === "doctor" ? "Phản hồi bệnh nhân..." : "Nhắn cho bác sĩ..."}
              aria-label="Tin nhắn"
              rows={2}
              className="flex-1 resize-none bg-transparent px-2 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
            <Hint content="Gửi (Enter). Xuống dòng: Shift + Enter.">
              <button
                type="button"
                onClick={submit}
                disabled={!text.trim() || send.isPending}
                aria-label="Gửi"
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-xl transition-all active:scale-95",
                  text.trim() ? "bg-brand text-brand-foreground shadow-sm hover:brightness-110" : "cursor-not-allowed bg-muted text-muted-foreground opacity-50"
                )}
              >
                <CornerDownLeft className="size-4" />
              </button>
            </Hint>
          </div>
        )}
      </div>
    </div>
  );
}
