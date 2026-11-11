"use client";

import { useState } from "react";
import { MessageSquareText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useFollowupChannel } from "../hooks";
import { FollowupChat } from "./FollowupChat";

function Body({ encounterId, role }: { encounterId: string; role: "patient" | "doctor" }) {
  const { data: channel, isLoading } = useFollowupChannel(encounterId);
  if (isLoading) return <p className="p-6 text-xs text-muted-foreground">Đang tải…</p>;
  if (!channel) return <p className="p-6 text-xs text-muted-foreground">Lần khám này chưa có kênh theo dõi.</p>;
  return <FollowupChat channel={channel} role={role} />;
}

// Nút + khung trượt mở kênh theo dõi của một lần khám; chỉ mount nội dung khi mở để khỏi nối SSE sớm
export function FollowupButton({ encounterId, role, className }: { encounterId: string; role: "patient" | "doctor"; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Hint content={role === "patient" ? "Nhắn tin hoặc nhận cuộc gọi từ bác sĩ đã khám cho bạn." : "Mở kênh trao đổi với bệnh nhân sau khám."}>
        <Button size="sm" variant="outline" onClick={() => setOpen(true)} className={className}>
          <MessageSquareText className="size-4" /> {role === "patient" ? "Trao đổi với bác sĩ" : "Theo dõi"}
        </Button>
      </Hint>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-lg">
          <SheetHeader className="sr-only">
            <SheetTitle>Kênh theo dõi sau khám</SheetTitle>
            <SheetDescription>Trao đổi giữa bệnh nhân và bác sĩ sau lần khám</SheetDescription>
          </SheetHeader>
          {open && <Body encounterId={encounterId} role={role} />}
        </SheetContent>
      </Sheet>
    </>
  );
}
