"use client";

import { ClipboardList, Stethoscope } from "lucide-react";
import { AppShell, type ShellNavItem } from "@/components/layout/app-shell";
import { doctorPaths } from "../routes";

const NAV: ShellNavItem[] = [
  { href: doctorPaths.home, label: "Ca khám", hint: "Lịch khám, hồ sơ nhận định và trao đổi với bệnh nhân sau khám", icon: ClipboardList, exact: true },
];

export function DoctorShell({ children }: { children: React.ReactNode }) {
  return (
    <AppShell sidebar brandLabel="Bác sĩ" brandIcon={Stethoscope} navTitle="Khu bác sĩ" nav={NAV}>
      {children}
    </AppShell>
  );
}
