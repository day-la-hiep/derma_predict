"use client";

import { useState } from "react";
import { CheckCircle2, Loader2, Search, X } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { cn } from "@/lib/utils";
import { useCreateMedicalRecordForProfile, usePatientSearch } from "../hooks";
import type { DoctorMedicalRecordItem, FinalizeInput, PatientProfile } from "../types";
import { EMPTY_FINALIZE, RecordForm } from "./RecordForm";
import { patientSubtitle } from "./PatientProfileDetails";

function PatientPicker({
  selected,
  onSelect,
  enabled,
}: {
  selected: PatientProfile | null;
  onSelect: (p: PatientProfile | null) => void;
  enabled: boolean;
}) {
  const [query, setQuery] = useState("");
  const q = useDebouncedValue(query.trim());
  const { data: results, isFetching } = usePatientSearch(q, enabled && !selected);

  if (selected) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-xl border border-brand/40 bg-brand/5 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{selected.fullName}</p>
          <p className="truncate text-[11px] text-muted-foreground">
            {patientSubtitle(selected)}
            {selected.phone && ` · ${selected.phone}`}
          </p>
        </div>
        <Button type="button" variant="ghost" size="icon" aria-label="Chọn bệnh nhân khác" onClick={() => onSelect(null)}>
          <X className="size-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tên hoặc SĐT"
          aria-label="Tìm hồ sơ bệnh nhân theo tên hoặc số điện thoại"
          className="h-9 rounded-xl pl-8 text-sm"
          autoFocus
        />
        {isFetching && (
          <Loader2 className="absolute right-3 top-1/2 size-3.5 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
      </div>
      <ul className="max-h-52 space-y-0.5 overflow-y-auto rounded-xl border border-border p-1">
        {!results?.length ? (
          <li className="px-2 py-3 text-center text-xs text-muted-foreground">
            {isFetching ? "Đang tìm…" : "Không tìm thấy hồ sơ"}
          </li>
        ) : (
          results.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => onSelect(p)}
                className="flex w-full flex-col rounded-lg px-2.5 py-1.5 text-left transition-colors hover:bg-muted"
              >
                <span className="text-sm font-medium text-foreground">{p.fullName}</span>
                <span className="text-[11px] text-muted-foreground">
                  {patientSubtitle(p)}
                  {p.phone && ` · ${p.phone}`}
                </span>
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

export function CreateMedicalRecordDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (record: DoctorMedicalRecordItem) => void;
}) {
  const [patient, setPatient] = useState<PatientProfile | null>(null);
  const [value, setValue] = useState<FinalizeInput>(EMPTY_FINALIZE);
  const { mutate, isPending } = useCreateMedicalRecordForProfile();

  const close = (o: boolean) => {
    onOpenChange(o);
    if (!o) {
      setPatient(null);
      setValue(EMPTY_FINALIZE);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!patient) return;
    mutate(
      { patientProfileId: patient.id, body: value },
      {
        onSuccess: (record) => {
          toast.success("Đã chốt bệnh án");
          onCreated(record);
          close(false);
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="flex max-h-[90vh] max-w-5xl flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        <DialogHeader className="border-b border-border px-6 py-4 text-left">
          <DialogTitle className="font-serif text-xl">Ghi bệnh án</DialogTitle>
          <DialogDescription className="text-xs">
            Cho ca khám trực tiếp. Ca tư vấn online được chốt khi bấm Đóng ca. Phiếu đã chốt không sửa được.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5">
            <div className="max-w-md space-y-2">
              <p className="text-xs font-semibold text-foreground">Bệnh nhân</p>
              <PatientPicker selected={patient} onSelect={setPatient} enabled={open} />
            </div>
            <div className={cn(!patient && "pointer-events-none opacity-40")} aria-disabled={!patient}>
              <RecordForm value={value} onChange={setValue} />
            </div>
          </div>
          <DialogFooter className="border-t border-border px-6 py-3.5">
            <Button type="button" variant="outline" onClick={() => close(false)} disabled={isPending}>
              Huỷ
            </Button>
            <Button type="submit" variant="brand" disabled={!patient || !value.diagnosis.trim() || isPending}>
              {isPending ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
              Chốt bệnh án
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
