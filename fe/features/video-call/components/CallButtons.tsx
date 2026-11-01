"use client";

import { Phone, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { useCallStore } from "../store";

/** Nút gọi của bác sĩ; chỉ bật khi ca đang `active` (server cũng kiểm tra lại). */
export function CallButtons({ conversationId, disabled }: { conversationId: string; disabled?: boolean }) {
  const phase = useCallStore((s) => s.phase);
  const startCall = useCallStore((s) => s.startCall);
  const off = disabled || phase !== "idle";

  return (
    <div className="flex items-center gap-1">
      <Hint content="Gọi thoại cho bệnh nhân. Chỉ gọi được khi bạn đang phụ trách ca.">
        <Button
          variant="outline"
          size="iconSm"
          aria-label="Gọi thoại"
          disabled={off}
          onClick={() => void startCall(conversationId, "audio")}
          className="border-emerald-500/30 text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300"
        >
          <Phone className="size-4" />
        </Button>
      </Hint>
      <Hint content="Gọi video cho bệnh nhân. Có thể bật/tắt camera trong cuộc gọi.">
        <Button
          variant="outline"
          size="iconSm"
          aria-label="Gọi video"
          disabled={off}
          onClick={() => void startCall(conversationId, "video")}
          className="border-emerald-500/30 text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-300"
        >
          <Video className="size-4" />
        </Button>
      </Hint>
    </div>
  );
}
