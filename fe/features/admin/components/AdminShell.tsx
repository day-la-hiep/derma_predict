"use client";

import { ListTree, Network, ShieldCheck } from "lucide-react";
import { AppShell, type ShellNavItem } from "@/components/layout/app-shell";

const NAV: ShellNavItem[] = [
  { href: "/admin/documents", label: "Sách giáo khoa", hint: "Số hóa sách, chuẩn bị tri thức cho trợ lý AI", icon: ListTree },
  { href: "/admin/graph-schema", label: "Quan hệ đồ thị", hint: "Chọn các loại quan hệ và thực thể được trích từ sách vào đồ thị tri thức", icon: Network },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <AppShell brandLabel="Quản trị" brandIcon={ShieldCheck} navTitle="Khu quản trị" nav={NAV} sidebar>
      {children}
    </AppShell>
  );
}
