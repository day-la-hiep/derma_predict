"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export function ReasonDialog({ title, onSubmit, onClose }: { title: string; onSubmit: (reason: string) => void; onClose: () => void }) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <Input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Lý do" maxLength={500} />
        <DialogFooter>
          <Button
            variant="brand"
            disabled={!reason.trim()}
            onClick={() => {
              onSubmit(reason.trim());
              onClose();
            }}
          >
            Xác nhận
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
