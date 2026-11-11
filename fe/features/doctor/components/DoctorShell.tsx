"use client";

import { CalendarDays, ClipboardList, MessageSquareText, Stethoscope } from "lucide-react";
import { AppShell, type ShellNavItem } from "@/components/layout/app-shell";
import { doctorPaths } from "../routes";

const NAV: ShellNavItem[] = [
  { href: doctorPaths.appointments, label: "Lịch khám", hint: "Lịch hẹn của bệnh nhân: xác nhận, bắt đầu khám và chốt kết luận", icon: CalendarDays },
  { href: doctorPaths.followups, label: "Theo dõi", hint: "Kênh trao đổi với bệnh nhân sau khi khám", icon: MessageSquareText },
  { href: doctorPaths.records, label: "Lịch sử khám", hint: "Các báo cáo kết luận bạn đã chốt sau mỗi lần khám", icon: ClipboardList },
];

// mọi màn bác sĩ nhiều cột cần khung cao bằng màn hình, tự cuộn từng cột
export function DoctorShell({ children }: { children: React.ReactNode }) {
  return (
    <AppShell brandLabel="Bác sĩ" brandIcon={Stethoscope} navTitle="Khu bác sĩ" nav={NAV} fullBleed>
      {children}
    </AppShell>
  );
}
