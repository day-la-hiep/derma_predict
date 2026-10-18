"use client";

import { useState } from "react";
import { Loader2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { GENDER_LABELS } from "@/features/patient-profile/constants";
import type { Gender } from "@/features/patient-profile/types";
import { cn } from "@/lib/utils";
import { errorMessage, updateAccount } from "../api";
import type { AuthenticatedUser } from "@/services/client";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-foreground">{label}</span>
      {children}
    </label>
  );
}

export function AccountSettingsDialog({
  account,
  open,
  onOpenChange,
}: {
  account: AuthenticatedUser;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [fullName, setFullName] = useState(account.full_name);
  const [dob, setDob] = useState(account.dob.slice(0, 10));
  const [gender, setGender] = useState<Gender>(account.gender);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await updateAccount({ full_name: fullName.trim(), dob, gender });
      toast.success("Đã cập nhật thông tin tài khoản");
      onOpenChange(false);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-162.5 max-h-[90vh] max-w-4xl gap-0 overflow-hidden rounded-2xl border border-border p-0 shadow-2xl sm:max-w-4xl">
        <DialogHeader className="border-b border-border/80 bg-background/60 px-6 py-4 text-left backdrop-blur-xs">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-brand" />
            <span className="font-mono text-xs font-medium uppercase tracking-wider text-brand">Cấu hình hệ thống</span>
          </div>
          <DialogTitle className="mt-0.5 font-serif text-lg font-normal tracking-tight text-foreground">
            Cài đặt
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Quản lý thông tin tài khoản bác sĩ
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <aside className="w-full shrink-0 border-b border-border bg-muted/30 md:w-64 md:border-r md:border-b-0">
            <nav className="flex gap-1 overflow-x-auto p-3 md:flex-col">
              <div className="md:flex md:flex-col">
                <div className="hidden px-3 pt-2 pb-1 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground md:block">
                  01 · CÀI ĐẶT CHUNG
                </div>
                <div
                  className={cn(
                    "flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-medium md:w-full",
                    "bg-brand/10 font-semibold text-brand shadow-xs"
                  )}
                >
                  <UserRound className="h-4 w-4 shrink-0 text-current" />
                  <span className="truncate">Tài khoản</span>
                </div>
              </div>
            </nav>
          </aside>

          <div className="min-w-0 flex-1 overflow-y-auto bg-background p-6">
            <div className="mb-4 border-b border-border/60 pb-3">
              <h2 className="text-base font-semibold text-foreground">Tài khoản</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">Thông tin định danh hiển thị với bệnh nhân và trong hệ thống</p>
            </div>
            <form onSubmit={submit} className="max-w-md space-y-6">
              <Field label="Họ và tên">
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} required maxLength={255} />
              </Field>
              <Field label="Ngày sinh">
                <Input type="date" value={dob} onChange={(e) => setDob(e.target.value)} required max={new Date().toISOString().slice(0, 10)} />
              </Field>
              <Field label="Giới tính">
                <Select value={gender} onValueChange={(v) => setGender(v as Gender)}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent position="popper" side="bottom" align="start">
                    {Object.entries(GENDER_LABELS).map(([v, l]) => (
                      <SelectItem key={v} value={v}>{l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Button type="submit" variant="brand" className="rounded-xl" disabled={!fullName.trim() || !dob || saving}>
                {saving && <Loader2 className="size-4 animate-spin" />}
                Lưu thay đổi
              </Button>
            </form>
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-border bg-card/60 px-6 py-3.5">
          <p className="text-xs text-muted-foreground">Thông tin được lưu vào hồ sơ tài khoản của bạn</p>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} className="rounded-xl">
            Đóng
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
