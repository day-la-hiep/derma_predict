"use client";

import { useState } from "react";
import { Stethoscope, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { useSessionFinalizeReports } from "../hooks";
import type { ConsultationSession } from "../types";
import { FinalizeReportCard } from "./FinalizeReportCard";
import { PatientProfileDetails, patientSubtitle } from "./PatientProfileDetails";
import { PatientJourneyDialog } from "./PatientJourneyDialog";

export function PatientProfileSheet({ session }: { session: ConsultationSession }) {
  const [open, setOpen] = useState(false);
  const { patient } = session;
  const { data: reports, isLoading } = useSessionFinalizeReports(open ? session.id : null);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <Hint side="bottom" content="Xem đầy đủ hồ sơ và toàn bộ lịch sử khám của bệnh nhân này">
        <Button variant="outline" size="sm" onClick={() => setOpen(true)} className="gap-1.5">
          <UserRound className="size-3.5" /> Hồ sơ
        </Button>
      </Hint>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle className="font-serif text-xl">{patient?.fullName ?? "Chưa rõ"}</SheetTitle>
          <SheetDescription>{patient ? patientSubtitle(patient) : ""}</SheetDescription>
        </SheetHeader>

        <div className="space-y-4 px-4 pb-4">
          {patient && <PatientProfileDetails patient={patient} />}

          {patient?.id && (
            <div className="pt-1">
              <PatientJourneyDialog
                patientId={patient.id}
                patientName={patient.fullName}
                trigger={
                  <Button variant="outline" className="w-full gap-2 border-brand/40 bg-brand/5 text-brand hover:bg-brand/10">
                    Xem đồ thị hành trình bệnh
                  </Button>
                }
              />
            </div>
          )}

          <div>
            <Hint side="left" content="Báo cáo kết luận được ghi khi bác sĩ chốt lúc đóng ca tư vấn.">
              <p className="mb-2 w-fit text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Lịch sử khám <span className="text-brand">{reports?.length ?? 0}</span>
              </p>
            </Hint>
            {isLoading && <p className="text-xs text-muted-foreground">Đang tải…</p>}
            {!isLoading && !reports?.length && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Stethoscope className="size-3.5 opacity-50" /> Chưa có lần khám nào
              </p>
            )}
            <ul className="space-y-2">
              {reports?.map((r) => <FinalizeReportCard key={r.id} report={r} />)}
            </ul>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
