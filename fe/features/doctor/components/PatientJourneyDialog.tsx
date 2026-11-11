"use client";

import { useState } from "react";
import { Network, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PatientJourneyView } from "./PatientJourneyView";

interface PatientJourneyDialogProps {
  patientId: string;
  patientName?: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: React.ReactNode;
}

export function PatientJourneyDialog({ patientId, patientName, open: controlledOpen, onOpenChange: setControlledOpen, trigger }: PatientJourneyDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen !== undefined ? controlledOpen : internalOpen;
  const setOpen = setControlledOpen !== undefined ? setControlledOpen : setInternalOpen;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {trigger ? (
        <DialogTrigger asChild>{trigger}</DialogTrigger>
      ) : (
        <DialogTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5 border-brand/30 text-brand hover:bg-brand/10">
            <Network className="size-3.5" /> Lịch sử khám
          </Button>
        </DialogTrigger>
      )}

      <DialogContent showCloseButton={false} className="flex h-[90vh] max-h-[900px] w-[95vw] max-w-6xl flex-col gap-0 overflow-hidden p-0 sm:rounded-2xl">
        <DialogHeader className="border-b border-border bg-card/60 px-6 py-4 backdrop-blur-md">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2.5">
              <div className="flex size-8 items-center justify-center rounded-xl bg-brand/10 text-brand">
                <Network className="size-4" />
              </div>
              <div>
                <DialogTitle className="font-serif text-lg font-bold text-foreground">Lịch sử khám {patientName ? `· ${patientName}` : ""}</DialogTitle>
                <DialogDescription className="text-xs text-muted-foreground">Đồ thị tri thức bệnh nhân (Personal Knowledge Graph) liên kết qua các lần khám</DialogDescription>
              </div>
            </div>
            <Button variant="ghost" size="icon-sm" onClick={() => setOpen(false)} className="rounded-lg text-muted-foreground hover:text-foreground">
              <X className="size-4" />
            </Button>
          </div>
        </DialogHeader>
        <div className="min-h-0 flex-1 bg-background">{open && <PatientJourneyView patientId={patientId} />}</div>
      </DialogContent>
    </Dialog>
  );
}
