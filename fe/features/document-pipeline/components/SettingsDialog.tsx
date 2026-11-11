"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { HintIcon } from "@/components/ui/hint";
import { cn } from "@/lib/utils";
import { errorMessage, documentApi } from "../api";
import { useRefreshDocument } from "../hooks";
import type { Settings } from "../types";

const selectBox =
  "h-9 w-full cursor-pointer rounded-xl border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="flex items-center gap-1 text-xs font-medium text-foreground">
        {label}
        {hint && <HintIcon content={hint} />}
      </span>
      {children}
    </label>
  );
}

function Form({ documentId, initial, onClose }: { documentId: string; initial: Settings; onClose: () => void }) {
  const refresh = useRefreshDocument(documentId);
  const [s, setS] = useState<Settings>(initial);
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS((p) => ({ ...p, [k]: v }));

  const save = useMutation({
    mutationFn: () => documentApi.saveSettings(documentId, s),
    onSuccess: () => {
      refresh();
      toast.success("Đã lưu cài đặt.");
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
        <Field label="Tên sách">
          <Input value={s.title} onChange={(e) => set("title", e.target.value)} className="h-9 rounded-xl text-sm" />
        </Field>
        <Field label="Cách đọc" hint="Văn bản có sẵn: nhanh, dùng khi PDF có chữ tốt. Nhận dạng từ ảnh: chậm hơn, dùng cho sách scan hoặc khi chữ trong PDF bị vỡ, sai dấu.">
          <select value={s.engine} onChange={(e) => set("engine", e.target.value as Settings["engine"])} className={selectBox}>
            <option value="pdftotext">Văn bản có sẵn</option>
            <option value="docling">Nhận dạng từ ảnh</option>
          </select>
        </Field>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={save.isPending}>
          Hủy
        </Button>
        <Button
          onClick={() => save.mutate()}
          disabled={save.isPending || !s.title.trim()}
          className={cn(save.isPending && "opacity-80")}
        >
          {save.isPending && <Loader2 className="animate-spin" />} Lưu
        </Button>
      </DialogFooter>
    </>
  );
}

export function SettingsDialog({ documentId, open, onOpenChange }: { documentId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const q = useQuery({ queryKey: ["toc", documentId, "settings"], queryFn: () => documentApi.getSettings(documentId), enabled: open, staleTime: 0, gcTime: 0 });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Cài đặt sách</DialogTitle>
          <DialogDescription>Cần làm lại bước liên quan để áp dụng.</DialogDescription>
        </DialogHeader>
        {q.isLoading || !q.data ? (
          <p className="py-8 text-center text-xs text-muted-foreground">{q.isError ? errorMessage(q.error) : "Đang tải..."}</p>
        ) : (
          <Form documentId={documentId} initial={q.data} onClose={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}
