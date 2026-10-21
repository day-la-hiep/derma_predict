"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

const MAX_BRIEF = 200;

export function RequestConsultationDialog({
  open,
  submitting,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  submitting: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (brief: string) => void;
}) {
  const [brief, setBrief] = useState("");
  const trimmed = brief.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Bạn muốn bác sĩ giúp gì?</DialogTitle>
          <DialogDescription>
            Hãy cho bác sĩ biết ngắn gọn bạn đang gặp vấn đề gì để họ nắm nhanh trước khi nhận ca.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value.slice(0, MAX_BRIEF))}
          placeholder="Ví dụ: Tay nổi mẩn đỏ, ngứa từ 3 hôm nay sau khi uống kháng sinh"
          rows={3}
          autoFocus
        />
        <p className="text-right font-mono text-[11px] text-muted-foreground">
          {brief.length}/{MAX_BRIEF}
        </p>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={submitting}>
            Huỷ
          </Button>
          <Button onClick={() => onSubmit(trimmed)} disabled={!trimmed || submitting}>
            {submitting && <Loader2 className="size-4 animate-spin" />}
            Gửi cho bác sĩ
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
