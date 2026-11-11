"use client";

import { useState } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EMPTY_FINALIZE, FinalizeReportForm, SuggestionPanel, isFinalizeComplete } from "@/features/doctor";
import type { FinalizeInput } from "@/features/doctor";
import { useEncounterDraft, useFinalizeEncounter } from "../hooks";
import type { EncounterDraft } from "../types";

function Form({ encounterId, draft, onDone }: { encounterId: string; draft: EncounterDraft; onDone: () => void }) {
  const [value, setValue] = useState<FinalizeInput>({ ...EMPTY_FINALIZE, facts: draft.facts });
  const [code, setCode] = useState("");
  const finalize = useFinalizeEncounter(encounterId);

  const toggleImage = (fileId: string) =>
    setValue((p) => ({
      ...p,
      images: p.images.some((i) => i.fileId === fileId)
        ? p.images.filter((i) => i.fileId !== fileId)
        : [...p.images, { fileId, bodySite: draft.episode.bodySiteLabel, description: "", confirmedLabel: null }],
    }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    finalize.mutate(
      { body: value, diagnosisCode: code },
      {
        onSuccess: () => {
          toast.success("Đã lưu kết luận");
          onDone();
        },
      }
    );
  };

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5">
        <SuggestionPanel suggestions={draft.suggestions} onPick={setValue} />
        <section className="space-y-1.5">
          <div className="text-xs font-semibold">Mã chẩn đoán</div>
          <Select value={code} onValueChange={setCode}>
            <SelectTrigger className="w-72" aria-label="Mã chẩn đoán">
              <SelectValue placeholder="Chọn mã" />
            </SelectTrigger>
            <SelectContent>
              {draft.diagnosisOptions.map((o) => (
                <SelectItem key={o.code} value={o.code}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </section>
        <FinalizeReportForm value={value} onChange={setValue} />
        {draft.images.length > 0 && (
          <section className="space-y-2">
            <div className="text-xs font-semibold">Ảnh bệnh (chọn để gắn vào kết luận)</div>
            <div className="flex flex-wrap gap-3">
              {draft.images.map((img) => {
                const picked = value.images.find((i) => i.fileId === img.fileId);
                return (
                  <div key={img.fileId} className="w-40 space-y-1">
                    <button
                      type="button"
                      onClick={() => toggleImage(img.fileId)}
                      className={`overflow-hidden rounded-lg border ${picked ? "border-brand ring-2 ring-brand" : "border-border"}`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {img.url && <img src={img.url} alt={img.fileName} className="size-40 object-cover" />}
                    </button>
                    <div className="text-[10px] text-muted-foreground">
                      CNN gợi ý: {img.topK[0] ? `${img.topK[0].labelName} (${Math.round(img.topK[0].score * 100)}%)` : "—"}
                    </div>
                    {picked && (
                      <Select
                        value={picked.confirmedLabel ?? ""}
                        onValueChange={(v) =>
                          setValue((p) => ({ ...p, images: p.images.map((i) => (i.fileId === img.fileId ? { ...i, confirmedLabel: v } : i)) }))
                        }
                      >
                        <SelectTrigger size="sm" className="h-7 text-[11px]" aria-label="Nhãn xác nhận">
                          <SelectValue placeholder="Nhãn xác nhận" />
                        </SelectTrigger>
                        <SelectContent>
                          {draft.diagnosisOptions.map((o) => (
                            <SelectItem key={o.code} value={o.code}>
                              {o.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>
      <DialogFooter className="border-t border-border px-6 py-3.5">
        <Button type="submit" variant="brand" disabled={!isFinalizeComplete(value) || !code || finalize.isPending}>
          {finalize.isPending ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
          Kết luận
        </Button>
      </DialogFooter>
    </form>
  );
}

export function EncounterFinalizeDialog({ encounterId, onClose }: { encounterId: string; onClose: () => void }) {
  const { data: draft, isLoading, isError } = useEncounterDraft(encounterId);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="flex max-h-[90vh] max-w-5xl flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="border-b border-border px-6 py-4 text-left">
          <DialogTitle className="font-serif text-xl">Kết luận</DialogTitle>
          <DialogDescription className="text-xs">
            Nhận định, cơ sở nhận định và mô tả là bắt buộc. Khi lưu, hệ thống đọc mô tả và chuyển thành dữ kiện; mọi dữ kiện (giữ nguyên và mới) đều ở trạng thái đã xác nhận, dữ kiện AI bị bỏ sẽ bị xoá. Phiếu đã lưu không sửa được.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="space-y-3 p-6">
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
          </div>
        ) : isError || !draft ? (
          <p className="p-6 text-sm text-muted-foreground">Không tải được dữ liệu lần khám.</p>
        ) : (
          <Form encounterId={encounterId} draft={draft} onDone={onClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}
