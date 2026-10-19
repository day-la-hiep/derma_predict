"use client";

import { ClipboardList, ListTree, MessageSquareText, Network, Stethoscope } from "lucide-react";
import { usePathname } from "next/navigation";
import { AppShell, type ShellNavItem } from "@/components/layout/app-shell";

const NAV: ShellNavItem[] = [
  { href: "/doctor", label: "Ca tư vấn", hint: "Xem báo cáo AI và hội thoại với bệnh nhân", icon: MessageSquareText, exact: true },
  { href: "/doctor/records", label: "Lịch sử khám", hint: "Các bệnh án bạn đã chốt sau khám hoặc tư vấn; ghi bệnh án cho ca khám trực tiếp", icon: ClipboardList },
  { href: "/doctor/documents", label: "Sách giáo khoa", hint: "Số hóa sách, chuẩn bị tri thức cho trợ lý AI", icon: ListTree },
  { href: "/doctor/graph-schema", label: "Quan hệ đồ thị", hint: "Chọn các loại quan hệ và thực thể được trích từ sách vào đồ thị tri thức", icon: Network },
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
