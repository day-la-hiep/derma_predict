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
import { useFinalizeDraft, useFinalizeSession } from "../hooks";
import { useDoctorStore } from "../store";
import type { ConsultationSession, FinalizeDraft, FinalizeInput } from "../types";
import { patientSubtitle } from "./PatientProfileDetails";
import { EMPTY_FINALIZE, RecordForm } from "./RecordForm";

function FinalizeForm({ session, draft, onDone }: { session: ConsultationSession; draft: FinalizeDraft; onDone: () => void }) {
  const [value, setValue] = useState<FinalizeInput>({ ...EMPTY_FINALIZE, facts: draft.facts });
  const finalize = useFinalizeSession(session.id);
  const resolveSession = useDoctorStore((s) => s.resolveSession);
  const markResolved = useDoctorStore((s) => s.markSessionResolved);
  const [closingOnly, setClosingOnly] = useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    finalize.mutate(value, {
      onSuccess: () => {
        markResolved(session.id);
        toast.success("Đã chốt bệnh án và đóng ca");
        onDone();
      },
    });
  };

  const closeWithoutRecord = async () => {
    setClosingOnly(true);
    await resolveSession(session.id);
    setClosingOnly(false);
    onDone();
  };

  const busy = finalize.isPending || closingOnly;

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <RecordForm value={value} onChange={setValue} />
      </div>
      <DialogFooter className="flex-row items-center justify-between gap-2 border-t border-border px-6 py-3.5 sm:justify-between">
        <Hint side="top" content="Đóng ca mà không tạo phiếu bệnh án (vd bệnh nhân chỉ hỏi thông tin chung).">
          <Button type="button" variant="ghost" size="sm" onClick={closeWithoutRecord} disabled={busy} className="text-muted-foreground">
            {closingOnly && <Loader2 className="size-3.5 animate-spin" />}
            Đóng ca không ghi bệnh án
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
          <DialogTitle className="font-serif text-xl">Chốt bệnh án</DialogTitle>
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
