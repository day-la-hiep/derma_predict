"use client";

import { useState } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Hint } from "@/components/ui/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversationMessages, useFinalizeDraft, useFinalizeSession } from "../hooks";
import { useDoctorStore } from "../store";
import type { ConsultationSession, FinalizeDraft, FinalizeInput } from "../types";
import { patientSubtitle } from "./PatientProfileDetails";
import { EMPTY_FINALIZE, FinalizeReportForm } from "./FinalizeReportForm";

function Chip({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-border bg-background px-2.5 py-1 text-left text-[11px] text-foreground hover:border-brand disabled:cursor-default"
      disabled={!onClick}
    >
      {children}
    </button>
  );
}

// Gợi ý từ đồ thị: bấm để đưa vào form, bác sĩ vẫn tự quyết nội dung kết luận
function SuggestionPanel({
  suggestions: s,
  onPick,
}: {
  suggestions: FinalizeDraft["suggestions"];
  onPick: (fn: (prev: FinalizeInput) => FinalizeInput) => void;
}) {
  const groups = [
    { title: "Nhận định ở các phiên trước (bấm để dùng làm nhận định)", items: s.previousConditions, pick: (t: string) => onPick((p) => ({ ...p, diagnosis: t })) },
    { title: "Lời khuyên đã dùng trước đây (bấm để thêm vào dặn dò)", items: s.previousAdvice, pick: (t: string) => onPick((p) => ({ ...p, instructions: p.instructions.includes(t) ? p.instructions : [...p.instructions, t] })) },
    { title: "Bệnh ứng viên theo đồ thị tri thức", items: s.candidateDiseases },
    { title: "Dấu hiệu cảnh báo (cờ đỏ) cần lưu ý", items: s.redFlags },
  ].filter((g) => g.items.length > 0);
  if (groups.length === 0 && s.notes.length === 0) return null;
  return (
    <section className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
      <div className="text-xs font-semibold text-foreground">Gợi ý tổng hợp từ đồ thị</div>
      {groups.map((g) => (
        <div key={g.title} className="space-y-1">
          <div className="text-[11px] text-muted-foreground">{g.title}</div>
          <div className="flex flex-wrap gap-1.5">
            {g.items.map((t) => (
              <Chip key={t} onClick={g.pick ? () => g.pick!(t) : undefined}>{t}</Chip>
            ))}
          </div>
        </div>
      ))}
      {s.notes.map((n) => (
        <div key={n} className="text-[11px] text-muted-foreground">{n}</div>
      ))}
      <div className="text-[11px] italic text-muted-foreground">Chỉ là gợi ý hỗ trợ, không phải chẩn đoán y khoa.</div>
    </section>
  );
}

function FinalizeForm({ session, draft, onDone }: { session: ConsultationSession; draft: FinalizeDraft; onDone: () => void }) {
  const [value, setValue] = useState<FinalizeInput>({ ...EMPTY_FINALIZE, facts: draft.facts });
  const finalize = useFinalizeSession(session.id);
  const resolveSession = useDoctorStore((s) => s.resolveSession);
  const markResolved = useDoctorStore((s) => s.markSessionResolved);
  const [closingOnly, setClosingOnly] = useState(false);
  const { data: messages } = useConversationMessages(session.conversationId);

  // Ảnh đính kèm trong đoạn chat để bác sĩ chọn gắn vào báo cáo kết luận
  const chatImages = (messages ?? []).flatMap((m) =>
    (m.attachments ?? [])
      .filter((a) => a.contentType?.startsWith("image/") && a.url)
      .map((a) => ({ messageId: m.id, id: a.id, name: a.name, url: a.url!, contentType: a.contentType }))
  );

  const toggleImage = (img: { id: string; url: string }) => {
    setValue((prev) => {
      const exists = prev.images.some((i) => i.fileId === img.id);
      if (exists) {
        return { ...prev, images: prev.images.filter((i) => i.fileId !== img.id) };
      }
      return {
        ...prev,
        images: [...prev.images, { fileId: img.id, bodySite: "", description: "", confirmedLabel: null }],
      };
    });
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    finalize.mutate(value, {
      onSuccess: () => {
        markResolved(session.id);
        toast.success("Đã chốt báo cáo kết luận và đóng ca");
        onDone();
      },
    });
  };

  const closeWithoutReport = async () => {
    setClosingOnly(true);
    await resolveSession(session.id);
    setClosingOnly(false);
    onDone();
  };

  const busy = finalize.isPending || closingOnly;

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 space-y-4">
        <SuggestionPanel suggestions={draft.suggestions} onPick={setValue} />
        <FinalizeReportForm value={value} onChange={setValue} />
        {chatImages.length > 0 && (
          <section className="space-y-2">
            <div className="text-xs font-semibold text-foreground">Ảnh bệnh từ đoạn chat (chọn để gắn vào báo cáo kết luận)</div>
            <div className="flex flex-wrap gap-2">
              {chatImages.map((img) => {
                const selected = value.images.some((i) => i.fileId === img.id);
                return (
                  <button
                    key={img.id}
                    type="button"
                    onClick={() => toggleImage(img)}
                    className={`relative rounded-lg border overflow-hidden ${selected ? "border-brand ring-2 ring-brand" : "border-border"}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={img.url} alt={img.name} className="size-20 object-cover" />
                    {selected && (
                      <span className="absolute top-1 right-1 rounded-full bg-brand text-white text-[10px] px-1.5 py-0.5">✓</span>
                    )}
                  </button>
                );
              })}
            </div>
            {value.images.length > 0 && (
              <div className="space-y-2">
                {value.images.map((img, idx) => (
                  <div key={img.fileId} className="flex gap-2 items-center">
                    <input
                      className="flex-1 rounded-md border border-border px-2 py-1 text-xs"
                      placeholder="Vị trí trên cơ thể (body site)"
                      value={img.bodySite}
                      onChange={(e) =>
                        setValue((prev) => ({
                          ...prev,
                          images: prev.images.map((x, j) => (j === idx ? { ...x, bodySite: e.target.value } : x)),
                        }))
                      }
                    />
                    <input
                      className="flex-1 rounded-md border border-border px-2 py-1 text-xs"
                      placeholder="Mô tả ảnh"
                      value={img.description}
                      onChange={(e) =>
                        setValue((prev) => ({
                          ...prev,
                          images: prev.images.map((x, j) => (j === idx ? { ...x, description: e.target.value } : x)),
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
      <DialogFooter className="flex-row items-center justify-between gap-2 border-t border-border px-6 py-3.5 sm:justify-between">
        <Hint side="top" content="Đóng ca mà không tạo báo cáo kết luận (vd bệnh nhân chỉ hỏi thông tin chung).">
          <Button type="button" variant="ghost" size="sm" onClick={closeWithoutReport} disabled={busy} className="text-muted-foreground">
            {closingOnly && <Loader2 className="size-3.5 animate-spin" />}
            Đóng ca không ghi báo cáo kết luận
          </Button>
        </Hint>
        <Button type="submit" variant="brand" disabled={!value.diagnosis.trim() || busy}>
          {finalize.isPending ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
          Chốt và đóng ca
        </Button>
      </DialogFooter>
    </form>
  );
}

export function FinalizeConsultationDialog({
  session,
  open,
  onOpenChange,
}: {
  session: ConsultationSession;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: draft, isLoading, isError } = useFinalizeDraft(open ? session.id : null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] max-w-5xl flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="border-b border-border px-6 py-4 text-left">
          <DialogTitle className="font-serif text-xl">Chốt báo cáo kết luận</DialogTitle>
          <DialogDescription className="text-xs">
            {session.patient.fullName} · {patientSubtitle(session.patient)}. Phiếu đã chốt không sửa được.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="space-y-3 p-6">
            <Skeleton className="h-9 w-1/2 rounded-lg" />
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
          </div>
        ) : isError || !draft ? (
          <p className="p-6 text-sm text-muted-foreground">Không tải được dữ kiện của ca này.</p>
        ) : (
          <FinalizeForm key={session.id} session={session} draft={draft} onDone={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}
