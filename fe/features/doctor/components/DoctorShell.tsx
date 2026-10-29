"use client";

import { ClipboardList, MessageSquareText, Stethoscope } from "lucide-react";
import { usePathname } from "next/navigation";
import { AppShell, type ShellNavItem } from "@/components/layout/app-shell";

const NAV: ShellNavItem[] = [
  { href: "/doctor", label: "Ca tư vấn", hint: "Xem báo cáo AI và hội thoại với bệnh nhân", icon: MessageSquareText, exact: true },
  { href: "/doctor/records", label: "Lịch sử khám", hint: "Các báo cáo kết luận bạn đã chốt sau mỗi ca tư vấn", icon: ClipboardList },
];

// màn nhiều cột cần khung cao bằng màn hình, tự cuộn từng cột
const FULL_BLEED = new Set(["/doctor", "/doctor/records"]);

export function DoctorShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <AppShell brandLabel="Bác sĩ" brandIcon={Stethoscope} navTitle="Khu bác sĩ" nav={NAV} fullBleed={FULL_BLEED.has(pathname)}>
      {children}
    </AppShell>
  );
}
