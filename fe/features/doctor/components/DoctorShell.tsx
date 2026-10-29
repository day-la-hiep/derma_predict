"use client";

import { ClipboardList, MessageSquareText, Stethoscope } from "lucide-react";
import { AppShell, type ShellNavItem } from "@/components/layout/app-shell";
import { doctorPaths } from "../routes";

const NAV: ShellNavItem[] = [
  {
    href: doctorPaths.entry,
    label: "Ca tư vấn",
    hint: "Xem báo cáo AI và hội thoại với bệnh nhân",
    icon: MessageSquareText,
    // /doctor và /doctor/<id> đều là ca tư vấn; chỉ /doctor/records là lịch sử
    match: (pathname) => !pathname.startsWith(doctorPaths.records),
  },
  { href: doctorPaths.records, label: "Lịch sử khám", hint: "Các báo cáo kết luận bạn đã chốt sau mỗi ca tư vấn", icon: ClipboardList },
];

// mọi màn bác sĩ nhiều cột cần khung cao bằng màn hình, tự cuộn từng cột
export function DoctorShell({ children }: { children: React.ReactNode }) {
  return (
    <AppShell brandLabel="Bác sĩ" brandIcon={Stethoscope} navTitle="Khu bác sĩ" nav={NAV} fullBleed>
      {children}
    </AppShell>
  );
}
